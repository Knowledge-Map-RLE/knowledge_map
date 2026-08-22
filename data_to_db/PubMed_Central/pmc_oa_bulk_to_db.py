#!/usr/bin/env python3
"""
Оптимизированная версия парсера PMC с улучшенной сложностью O(F × A × log(R))
"""

import gzip
import logging
import time
import datetime
import re
import json
import tarfile
import hashlib
from pathlib import Path
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree as LET
from typing import Any, Callable, Dict, List, Optional, Tuple
from neo4j import GraphDatabase, exceptions as neo4j_exceptions
from tqdm import tqdm
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import get_driver, load_checkpoint, append_checkpoint, setup_logging
from xml_to_md_grpc_client import get_xml_to_md_client
from s3_client import get_s3_client, S3_BUCKET_NAME

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR        = Path("..") / "data" / "PubMed_Central"
LOG_FILE        = Path("./logs/pmc_oa_bulk_to_db.log")
CHECKPOINT_FILE = Path("./logs/pmc_parse_checkpoint.txt")

# Оптимизированные настройки
MAX_WORKERS       = 2        # Увеличено для параллелизма
WRITER_COUNT      = 1        # Один writer чтобы избежать deadlock
MAX_WRITE_RETRIES = 5        # Увеличено для retry при deadlock
WRITE_BACKOFF     = 3        # Увеличен backoff
BATCH_SIZE        = 50       # Увеличено для эффективности
POOL_SIZE         = 2
QUEUE_SIZE        = MAX_WORKERS * 4

# Предкомпилированные regex и XPath
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
NS = {'ns': 'http://www.ncbi.nlm.nih.gov/JATS1', 'xlink': 'http://www.w3.org/1999/xlink'}

# Предкомпилированные XPath запросы
XPATH_CACHE = {
    'pmid': ['.//article-id[@pub-id-type="pmid"]', './/ns:article-id[@pub-id-type="pmid"]'],
    'pmcid': ['.//article-id[@pub-id-type="pmc"]', './/ns:article-id[@pub-id-type="pmc"]'],
    'doi': ['.//article-id[@pub-id-type="doi"]', './/ns:article-id[@pub-id-type="doi"]'],
    'title': ['.//article-title', './/ns:article-title'],
    'journal': ['.//journal-title', './/ns:journal-title'],
    'year': ['.//pub-date/year', './/ns:pub-date/ns:year'],
    'abstract': ['.//abstract', './/ns:abstract'],
    'authors': ['.//contrib[@contrib-type="author"]', './/ns:contrib[@contrib-type="author"]'],
    'keywords': ['.//kwd-group/kwd', './/ns:kwd-group/ns:kwd'],
    'refs': ['.//ref-list/ref', './/ns:ref-list/ns:ref']
}

# ========== ЛОГИРОВАНИЕ ==========
logger = setup_logging(LOG_FILE)

# ========== NEO4J ==========
driver = get_driver(pool_size=POOL_SIZE)

# ========== ОПТИМИЗИРОВАННЫЕ ФУНКЦИИ ==========

def extract_element_optimized(root, xpath_list, namespaces=None):
    """Оптимизированное извлечение элементов с кэшированием XPath"""
    for xpath in xpath_list:
        elem = root.find(xpath, namespaces=namespaces)
        if elem is not None:
            return elem
    return None

def extract_text_optimized(root, xpath_list, namespaces=None):
    """Оптимизированное извлечение текста"""
    elem = extract_element_optimized(root, xpath_list, namespaces)
    if elem is not None:
        if elem.text:
            return elem.text.strip()
        else:
            return ''.join(elem.itertext()).strip()
    return None

def extract_year_from_date_optimized(date_text):
    """Оптимизированное извлечение года"""
    if not date_text:
        return None
    year_match = YEAR_RE.search(str(date_text))
    if year_match:
        year = str(int(year_match.group()))
        return year
    return None

def extract_authors_optimized(root):
    """Оптимизированное извлечение авторов"""
    authors = []
    author_elements = extract_element_optimized(root, XPATH_CACHE['authors'], NS)
    if author_elements is not None:
        for au in author_elements.findall('.//contrib[@contrib-type="author"]') or author_elements.findall('.//ns:contrib[@contrib-type="author"]', NS):
            surname_elem = au.find('.//surname') or au.find('.//ns:surname', NS)
            given_elem = au.find('.//given-names') or au.find('.//ns:given-names', NS)
            
            surname = surname_elem.text.strip() if surname_elem is not None and surname_elem.text else None
            given = given_elem.text.strip() if given_elem is not None and given_elem.text else None
            
            if surname or given:
                author_name = f"{given} {surname}".strip() if given and surname else (surname or given)
                authors.append(author_name)
    return authors

def extract_keywords_optimized(root):
    """Оптимизированное извлечение ключевых слов"""
    keywords = []
    kwd_elements = root.findall('.//kwd-group/kwd') or root.findall('.//ns:kwd-group/ns:kwd', NS)
    for kwd in kwd_elements:
        if kwd.text and kwd.text.strip():
            keyword = kwd.text.strip()
            if len(keyword) <= 200:
                keywords.append(keyword)
    return keywords

def extract_bibliographic_links_optimized(root, primary_id):
    """
    Улучшенное извлечение библиографических ссылок с полным покрытием различных форматов XML

    Поддерживает:
    - Файлы с namespace и без
    - Различные типы идентификаторов: PMID, PMCID, DOI, URL
    - Извлечение заголовков ссылок
    - Дедупликацию
    """
    links = []
    unique_citations = set()

    # Ищем ref элементы - сначала без namespace, потом с namespace
    ref_elements = root.findall('.//ref-list/ref')
    if not ref_elements:
        ref_elements = root.findall('.//ns:ref-list/ns:ref', NS)

    # Логируем количество найденных ссылок
    logger.debug(f"[{primary_id}] Found {len(ref_elements)} reference elements in XML")

    for ref_idx, ref in enumerate(ref_elements, 1):
        ref_data = {}

        # Извлечение PMID - пробуем разные XPath варианты
        pmid_elem = ref.find('.//pub-id[@pub-id-type="pmid"]')
        if pmid_elem is None:
            pmid_elem = ref.find('.//ns:pub-id[@pub-id-type="pmid"]', NS)
        if pmid_elem is None:
            pmid_elem = ref.find('.//article-id[@pub-id-type="pmid"]')
        if pmid_elem is None:
            pmid_elem = ref.find('.//ns:article-id[@pub-id-type="pmid"]', NS)
        if pmid_elem is not None and pmid_elem.text:
            ref_data['pmid'] = pmid_elem.text.strip()

        # Извлечение PMCID
        pmcid_elem = ref.find('.//pub-id[@pub-id-type="pmc"]')
        if pmcid_elem is None:
            pmcid_elem = ref.find('.//ns:pub-id[@pub-id-type="pmc"]', NS)
        if pmcid_elem is None:
            pmcid_elem = ref.find('.//pub-id[@pub-id-type="pmcid"]')
        if pmcid_elem is None:
            pmcid_elem = ref.find('.//ns:pub-id[@pub-id-type="pmcid"]', NS)
        if pmcid_elem is None:
            pmcid_elem = ref.find('.//article-id[@pub-id-type="pmc"]')
        if pmcid_elem is None:
            pmcid_elem = ref.find('.//ns:article-id[@pub-id-type="pmc"]', NS)
        if pmcid_elem is not None and pmcid_elem.text:
            # Нормализуем PMCID - убираем префикс PMC если есть
            pmcid = pmcid_elem.text.strip()
            if pmcid.startswith('PMC'):
                pmcid = pmcid[3:]
            ref_data['pmcid'] = pmcid

        # Извлечение DOI
        doi_elem = ref.find('.//pub-id[@pub-id-type="doi"]')
        if doi_elem is None:
            doi_elem = ref.find('.//ns:pub-id[@pub-id-type="doi"]', NS)
        if doi_elem is None:
            doi_elem = ref.find('.//article-id[@pub-id-type="doi"]')
        if doi_elem is None:
            doi_elem = ref.find('.//ns:article-id[@pub-id-type="doi"]', NS)
        if doi_elem is not None and doi_elem.text:
            ref_data['doi'] = doi_elem.text.strip()

        # URL из ext-link
        url_elem = ref.find('.//ext-link[@ext-link-type="uri"]')
        if url_elem is None:
            url_elem = ref.find('.//ns:ext-link[@ext-link-type="uri"]', NS)
        if url_elem is not None:
            # Пробуем получить URL из атрибута xlink:href
            url = url_elem.get('{http://www.w3.org/1999/xlink}href')
            if not url:
                url = url_elem.text
            if url and url.strip().startswith('http'):
                ref_data['url'] = url.strip()

        # Заголовок - пробуем article-title, потом source как fallback
        title_elem = ref.find('.//article-title')
        if title_elem is None:
            title_elem = ref.find('.//ns:article-title', NS)
        if title_elem is not None:
            ref_data['title'] = ''.join(title_elem.itertext()).strip()
        else:
            # Fallback на source если нет article-title
            source_elem = ref.find('.//source')
            if source_elem is None:
                source_elem = ref.find('.//ns:source', NS)
            if source_elem is not None:
                ref_data['title'] = ''.join(source_elem.itertext()).strip()

        # Год публикации
        year_elem = ref.find('.//year')
        if year_elem is None:
            year_elem = ref.find('.//ns:year', NS)
        if year_elem is not None and year_elem.text:
            ref_data['year'] = year_elem.text.strip()

        # Проверяем что хотя бы один идентификатор или заголовок есть
        has_identifier = any(ref_data.get(key) for key in ['pmid', 'pmcid', 'doi', 'url'])
        has_title = bool(ref_data.get('title'))

        if not has_identifier and not has_title:
            logger.debug(f"[{primary_id}] Ref #{ref_idx}: Skipping - no identifiers or title")
            continue

        # Дедупликация по ключу из всех идентификаторов
        citation_key = (
            f"{primary_id}->"
            f"{ref_data.get('pmid', '')}->"
            f"{ref_data.get('pmcid', '')}->"
            f"{ref_data.get('doi', '')}->"
            f"{ref_data.get('url', '')}->"
            f"{ref_data.get('title', '')[:50]}"
        )

        if citation_key in unique_citations:
            logger.debug(f"[{primary_id}] Ref #{ref_idx}: Skipping duplicate")
            continue

        unique_citations.add(citation_key)
        links.append(ref_data)

        # Детальное логирование для отладки
        id_types = []
        if ref_data.get('pmid'):
            id_types.append(f"PMID:{ref_data['pmid']}")
        if ref_data.get('pmcid'):
            id_types.append(f"PMCID:{ref_data['pmcid']}")
        if ref_data.get('doi'):
            id_types.append(f"DOI:{ref_data['doi'][:20]}...")
        if ref_data.get('url'):
            id_types.append(f"URL:{ref_data['url'][:30]}...")

        logger.debug(f"[{primary_id}] Ref #{ref_idx}: Extracted - {', '.join(id_types) if id_types else 'TITLE_ONLY'}")

    logger.info(f"[{primary_id}] Extracted {len(links)} unique bibliographic links from {len(ref_elements)} references")

    # Предупреждение о подозрительно большом количестве ссылок
    if len(links) > 500:
        logger.warning(f"[{primary_id}] Suspiciously high number of references: {len(links)} (expected 20-100)")

    return links

def _build_pmc_markdown(metadata: dict) -> str:
    """Генерирует markdown-представление PMC-статьи из метаданных.

    Используется как fallback, когда gRPC-конвертация全文 недоступна.
    """
    parts: list[str] = []

    title = metadata.get('title', '')
    if title:
        parts.append(f"# {title}\n")

    authors = metadata.get('authors', [])
    if authors:
        if isinstance(authors, list):
            parts.append(f"**Authors:** {', '.join(authors)}\n")
        else:
            parts.append(f"**Authors:** {authors}\n")

    meta_parts: list[str] = []
    journal = metadata.get('journal', '')
    if journal:
        meta_parts.append(f"**Journal:** {journal}")
    doi = metadata.get('doi', '')
    if doi:
        meta_parts.append(f"**DOI:** {doi}")
    pmid = metadata.get('pmid', '')
    if pmid:
        meta_parts.append(f"**PMID:** {pmid}")
    pmcid = metadata.get('pmcid', '')
    if pmcid:
        meta_parts.append(f"**PMCID:** {pmcid}")
    if meta_parts:
        parts.append(" | ".join(meta_parts) + "\n")

    abstract = metadata.get('abstract', '')
    if abstract:
        parts.append(f"## Abstract\n\n{abstract}\n")

    keywords = metadata.get('keywords', [])
    if keywords:
        if isinstance(keywords, list):
            parts.append(f"**Keywords:** {', '.join(keywords)}\n")
        else:
            parts.append(f"**Keywords:** {keywords}\n")

    return "\n".join(parts) if parts else ""


def parse_article_optimized(article, total_articles):
    """Оптимизированный парсинг статьи O(log R)"""
    
    pmid = None
    pmcid = None
    doi = None
    
    pmid_el = article.find('.//article-id[@pub-id-type="pmid"]')
    if pmid_el is not None and pmid_el.text:
        pmid = pmid_el.text.strip()
    
    pmcid_el = article.find('.//article-id[@pub-id-type="pmcid"]')
    if pmcid_el is None:
        pmcid_el = article.find('.//article-id[@pub-id-type="pmc"]')
    if pmcid_el is not None and pmcid_el.text:
        pmcid = pmcid_el.text.strip()
    
    if not pmid and not pmcid:
        # Нет устойчивых идентификаторов — генерируем детерминированный UID
        # из содержимого статьи, чтобы он не менялся от имени архива/файла.
        fingerprint = LET.tostring(article, encoding='unicode')
        primary_id = "id_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:20]
        pmid = primary_id
    else:
        primary_id = pmcid or pmid
    
    doi_el = article.find('.//article-id[@pub-id-type="doi"]')
    if doi_el is not None and doi_el.text:
        doi = doi_el.text.strip()
    
    title = ''
    title_el = article.find('.//article-title')
    if title_el is not None:
        title = ''.join(title_el.itertext()).strip()
    
    journal = ''
    journal_el = article.find('.//journal-title')
    if journal_el is not None:
        journal = journal_el.text.strip()
    
    year_elem = article.find('.//pub-date/year')
    publication_time = year_elem.text.strip() if year_elem is not None and year_elem.text else None
    
    abstract = ''
    abstract_el = article.find('.//abstract')
    if abstract_el is not None:
        abstract = ''.join(abstract_el.itertext()).strip()
    
    authors = []
    for author in article.findall('.//contrib[@contrib-type="author"]')[:20]:
        surname = author.find('.//surname')
        if surname is not None:
            given = author.find('.//given-names')
            name = surname.text or ''
            if given is not None and given.text:
                name = given.text + ' ' + name
            authors.append(name.strip())
    
    keywords = []
    for kw in article.findall('.//kwd')[:15]:
        if kw.text:
            keywords.append(kw.text.strip())

    metadata = {
        'title': title,
        'authors': authors,
        'abstract': abstract,
        'keywords': keywords,
        'journal': journal,
        'doi': doi,
        'pmid': pmid,
        'pmcid': pmcid,
    }
    
    body_s3_key = None
    try:
        from s3_client import get_s3_client
        s3 = get_s3_client()
        if not s3.article_exists(primary_id):
            try:
                from xml_to_md_grpc_client import get_xml_to_md_client
                xml_client = get_xml_to_md_client()
                if xml_client:
                    article_xml = LET.tostring(article, encoding='unicode')
                    xml_bytes = article_xml.encode('utf-8')
                    result = xml_client.convert_pmc_xml(xml_bytes)
                    if result and result.get('success'):
                        markdown_content = result.get('markdown_content', '')
                        if markdown_content and s3.save_markdown(primary_id, markdown_content):
                            body_s3_key = f"documents/{primary_id}/{primary_id}.md"
            except Exception as grpc_err:
                logger.warning(f"[{primary_id}] gRPC conversion failed: {grpc_err}")

            if not body_s3_key:
                md_content = _build_pmc_markdown(metadata)
                if md_content and s3.save_markdown(primary_id, md_content):
                    body_s3_key = f"documents/{primary_id}/{primary_id}.md"
                    logger.info(f"[{primary_id}] Fallback: uploaded abstract-based markdown to S3")
        else:
            body_s3_key = f"documents/{primary_id}/{primary_id}.md"
    except Exception as e:
        logger.warning(f"[{primary_id}] Error in S3/markdown pipeline: {e}")
    
    data = {
        'uid': primary_id,
        'pmid': pmid,
        'pmcid': pmcid,
        'doi': doi,
        'title': title,
        'publication_time': publication_time,
        'journal': journal,
        'abstract': abstract,
        'body': body_s3_key,
        'authors': authors,
        'keywords': keywords
    }
    
    cited_list = extract_bibliographic_links_optimized(article, primary_id)
    
    return data, cited_list, primary_id


def embed_floats_optimized(root):
    """Оптимизированное встраивание floats-group"""
    body_elem = root.find('.//body') or root.find('.//ns:body', NS)
    if body_elem is None:
        return None
    
    # Один запрос для floats-group
    floats_group = root.find('.//floats-group') or root.find('.//ns:floats-group', NS)
    if floats_group is None:
        return LET.tostring(body_elem, encoding='unicode')
    
    body_xml = LET.tostring(body_elem, encoding='unicode')
    
    # Обрабатываем fig и table-wrap за один проход
    for element_type in ['fig', 'table-wrap']:
        for elem in floats_group.findall(f'.//{element_type}'):
            elem_id = elem.get('id')
            if elem_id:
                content = LET.tostring(elem, encoding='unicode')
                body_xml = body_xml.replace(f'<xref rid="{elem_id}"/>', content)
                body_xml = body_xml.replace(f'<xref rid="{elem_id}"></xref>', content)
    
    return body_xml

# ========== S3 ЗАГРУЗКА ==========

def load_archive_from_s3(s3_key: str):
    """Загружает архив из S3 и возвращает file-like объект."""
    ARCHIVE_BUCKET = "knowledge-map-data"
    s3 = get_s3_client()
    response = s3.s3.get_object(Bucket=ARCHIVE_BUCKET, Key=s3_key)
    return response['Body']

def parse_archive_from_s3(file_path: str):
    """Парсит архив из S3 или локального пути."""
    import gzip
    import tarfile
    import io
    from pathlib import Path
    
    nodes, rels = [], []
    count = 0
    total_articles = 0
    
    s3 = get_s3_client()
    archive_name = Path(file_path).name
    
    try:
        # Проверяем - локальный файл или S3 ключ
        if Path(file_path).exists():
            # Локальный файл
            with open(file_path, 'rb') as f:
                body_bytes = f.read()
            body = io.BytesIO(body_bytes)
        else:
            # S3 ключ
            body = s3.s3.get_object(Bucket="knowledge-map-data", Key=file_path)['Body']
        with tarfile.open(fileobj=io.BytesIO(body.read()), mode='r:gz') as tar:
            xml_files = [member for member in tar.getmembers() if member.name.endswith('.xml')]
            
            if not xml_files:
                logger.error(f"Archive {archive_name} does not contain XML files")
                return archive_name
            
            logger.info(f"Found {len(xml_files)} XML files in {archive_name}")
            
            pbar_desc = f"{archive_name[:30]}"
            with tqdm(total=len(xml_files), desc=pbar_desc, unit="xml", leave=False, position=2) as xml_pbar:
                for xml_file in xml_files:
                    try:
                        xml_content = tar.extractfile(xml_file)
                        if xml_content is None:
                            xml_pbar.update(1)
                            continue
                        
                        root = LET.parse(xml_content).getroot()
                        if root.tag != 'article':
                            xml_pbar.update(1)
                            continue
                        
                        total_articles += 1
                        
                        data, cited_list, primary_id = parse_article_optimized(root, total_articles)
                        
                        nodes.append(data)
                        count += 1
                        
                        for cited in cited_list:
                            link_id = cited.get('pmcid') or cited.get('pmid')
                            if link_id:
                                rels.append({
                                    'source_pmid': link_id,
                                    'source_title': cited.get('title'),
                                    'target_pmid': primary_id,
                                    'target_title': data['title']
                                })
                        
                        if count % BATCH_SIZE == 0:
                            logger.info(f"{archive_name}: enqueue batch #{count//BATCH_SIZE}")
                            write_queue.put((archive_name, nodes.copy(), rels.copy()))
                            nodes.clear()
                            rels.clear()
                            
                            if count % (BATCH_SIZE * 5) == 0:
                                import gc
                                gc.collect()
                                time.sleep(0.1)
                        
                        xml_pbar.update(1)
                        xml_pbar.set_postfix_str(f"articles: {count}")
                    
                    except Exception as e:
                        logger.error(f"Error processing XML {xml_file.name}: {e}")
                        xml_pbar.update(1)
                        continue
        
        if nodes or rels:
            logger.info(f"{archive_name}: enqueue final batch")
            write_queue.put((archive_name, nodes, rels))
        
        logger.info(f"{archive_name}: Articles processed: {total_articles}, Accepted: {count}")
        return archive_name
    
    except Exception as e:
        logger.error(f"Error opening archive {archive_name}: {e}")
        return archive_name


# ========== ОПТИМИЗИРОВАННЫЙ ПАРСИНГ ==========

def parse_one_file_optimized(path_or_key):
    """Оптимизированный парсинг файла O(A × log R)"""
    nodes, rels = [], []
    count = 0
    total_articles = 0

    try:
        with tarfile.open(path, 'r:gz') as tar:
            xml_files = [member for member in tar.getmembers() if member.name.endswith('.xml')]

            if not xml_files:
                logger.error(f"Archive {path.name} does not contain XML files")
                return path.name

            logger.info(f"Found {len(xml_files)} XML files in archive {path.name}")

            # Добавляем прогресс-бар для XML файлов внутри архива
            pbar_desc = f"{path.name[:30]}"
            with tqdm(total=len(xml_files), desc=pbar_desc, unit="xml", leave=False, position=2) as xml_pbar:
                for xml_file in xml_files:
                    try:
                        xml_content = tar.extractfile(xml_file)
                        if xml_content is None:
                            xml_pbar.update(1)
                            continue

                        root = LET.parse(xml_content).getroot()
                        if root.tag != 'article':
                            xml_pbar.update(1)
                            continue

                        total_articles += 1

                        # Оптимизированный парсинг статьи
                        data, cited_list, primary_id = parse_article_optimized(root, total_articles)

                        nodes.append(data)
                        count += 1

                        # Создаем связи
                        # ВАЖНО: Приоритизируем PMCID и PMID, игнорируем DOI и URL
                        # так как они не являются вершинами графа статей
                        #
                        # УНИФИЦИРОВАННАЯ СЕМАНТИКА SOURCE/TARGET:
                        # - SOURCE (left): cited reference (старая статья) - низкие слои
                        # - TARGET (right): citing article (новая статья) - высокие слои
                        # - Направление: SOURCE -> TARGET (старая -> новая)
                        for cited in cited_list:
                            # Приоритет: PMCID > PMID (игнорируем DOI и URL)
                            link_id = cited.get('pmcid') or cited.get('pmid')
                            if link_id:
                                rels.append({
                                    'source_pmid': link_id,              # SOURCE: cited reference (старая)
                                    'source_title': cited.get('title'),
                                    'target_pmid': primary_id,           # TARGET: citing article (новая)
                                    'target_title': data['title']
                                })

                        # Батчинг
                        if count % BATCH_SIZE == 0:
                            logger.info(f"{path.name}: enqueue batch #{count//BATCH_SIZE}")
                            write_queue.put((path.name, nodes.copy(), rels.copy()))
                            nodes.clear()
                            rels.clear()

                            # Периодическая очистка памяти
                            if count % (BATCH_SIZE * 5) == 0:
                                import gc
                                gc.collect()
                                time.sleep(0.1)

                        # Обновляем прогресс-бар после обработки каждого XML
                        xml_pbar.update(1)
                        xml_pbar.set_postfix_str(f"articles: {count}")

                    except Exception as e:
                        logger.error(f"Error processing XML file {xml_file.name}: {e}")
                        xml_pbar.update(1)
                        continue
    
    except Exception as e:
        logger.error(f"Error opening archive {path.name}: {e}")
        return path.name
    
    # Финальный батч
    if nodes or rels:
        logger.info(f"{path.name}: enqueue final batch")
        write_queue.put((path.name, nodes, rels))
    
    logger.info(f"{path.name}: Articles processed: {total_articles}, Accepted: {count}")
    return path.name

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ (без изменений) ==========

# load_checkpoint и append_checkpoint импортированы из common.py

def ensure_schema():
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Document) REQUIRE n.uid IS UNIQUE")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.layout_status)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.layer, n.level)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.uid)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.pubmed_id)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.doi)")
    logger.info("Schema constraints and indexes ensured")

def reset_database_full():
    try:
        logger.info("Starting database cleanup...")
        with driver.session() as s:
            s.run("MATCH ()-[r]->() DELETE r")
            s.run("MATCH (n) DELETE n")
        logger.info("Database completely cleaned")
    except Exception as e:
        logger.error(f"Error cleaning database: {e}")

def write_to_neo4j(path_name: str, nodes: list[dict], rels: list[dict]) -> bool:
    global driver
    
    def tx_work(tx):
        if nodes:
            doc_nodes = []
            for node in nodes:
                body_s3_key = node.get('body')
                doc_id = node.get('uid') or node.get('pmcid') or node.get('pmid')
                doc_nodes.append({
                    'uid': doc_id,
                    'original_filename': f"{doc_id}.xml",
                    'md5_hash': f"pmc_{node.get('pmcid') or node.get('pmid', 'unknown')}",
                    's3_key': f"documents/{doc_id}/{doc_id}.md",
                    'docling_raw_md_s3_key': body_s3_key,
                    'formatted_md_s3_key': body_s3_key,
                    'title': node.get('title', ''),
                    'authors': json.dumps(node.get('authors', [])),
                    'abstract': node.get('abstract', ''),
                    'keywords': json.dumps(node.get('keywords', [])),
                    'journal': node.get('journal', ''),
                    'doi': node.get('doi', ''),
                    'pubmed_id': node.get('pmid'),
                    'pmc_id': node.get('pmcid'),
                    'source': 'pmc',
                    'is_open_access': True,
                    'is_processed': bool(body_s3_key),
                    'processing_status': 'processed' if body_s3_key else 'pending',
                    'has_full_text': bool(body_s3_key),
                })
            tx.run("""
                UNWIND $nodes AS row
                  WITH row
                  OPTIONAL MATCH (existing:Document)
                    WHERE (row.pmid IS NOT NULL AND row.pmid <> '' AND existing.pubmed_id = row.pmid)
                       OR (row.pmcid IS NOT NULL AND row.pmcid <> '' AND existing.pmc_id = row.pmcid)
                       OR (row.doi IS NOT NULL AND row.doi <> '' AND existing.doi = row.doi)
                  WITH row, collect(existing)[0] AS existing
                  WITH row, CASE WHEN existing IS NOT NULL THEN existing.uid ELSE row.uid END AS uid
                  MERGE (n:Document {uid: uid})
                  ON CREATE SET
                      n.original_filename = row.original_filename,
                      n.md5_hash = row.md5_hash,
                      n.s3_key = row.s3_key,
                      n.docling_raw_md_s3_key = row.docling_raw_md_s3_key,
                      n.formatted_md_s3_key = row.formatted_md_s3_key,
                      n.title = row.title,
                      n.authors = row.authors,
                      n.abstract = row.abstract,
                      n.keywords = row.keywords,
                      n.journal = row.journal,
                      n.doi = row.doi,
                      n.pubmed_id = row.pubmed_id,
                      n.pmc_id = row.pmc_id,
                      n.source = row.source,
                      n.is_open_access = row.is_open_access,
                      n.is_processed = row.is_processed,
                      n.processing_status = row.processing_status,
                      n.has_full_text = row.has_full_text
                  ON MATCH SET
                      n.original_filename = coalesce(n.original_filename, row.original_filename),
                      n.md5_hash = coalesce(n.md5_hash, row.md5_hash),
                      n.s3_key = coalesce(n.s3_key, row.s3_key),
                      n.docling_raw_md_s3_key = coalesce(n.docling_raw_md_s3_key, row.docling_raw_md_s3_key),
                      n.formatted_md_s3_key = coalesce(n.formatted_md_s3_key, row.formatted_md_s3_key),
                      n.title = coalesce(n.title, row.title),
                      n.authors = coalesce(n.authors, row.authors),
                      n.abstract = coalesce(n.abstract, row.abstract),
                      n.keywords = coalesce(n.keywords, row.keywords),
                      n.journal = coalesce(n.journal, row.journal),
                      n.doi = coalesce(n.doi, row.doi),
                      n.pubmed_id = coalesce(n.pubmed_id, row.pubmed_id),
                      n.pmc_id = coalesce(n.pmc_id, row.pmc_id),
                      n.source = coalesce(n.source, row.source),
                      n.is_open_access = coalesce(n.is_open_access, row.is_open_access),
                      n.is_processed = row.is_processed,
                      n.processing_status = row.processing_status,
                      n.has_full_text = (row.has_full_text OR coalesce(n.has_full_text, false))
            """, nodes=doc_nodes)
        if rels:
            # УНИФИЦИРОВАННАЯ СЕМАНТИКА SOURCE/TARGET:
            # Направление: SOURCE (cited, старая) -> TARGET (citing, новая)
            tx.run("""
                UNWIND $rels AS r
                  MERGE (source:Document {uid: r.source_pmid})
                    ON CREATE SET source.title = coalesce(r.source_title, source.title)
                    ON MATCH SET source.title = coalesce(source.title, r.source_title)
                  MERGE (target:Document {uid: r.target_pmid})
                    ON CREATE SET target.title = coalesce(r.target_title, target.title)
                    ON MATCH SET target.title = coalesce(target.title, r.target_title)
                  WITH source, target
                  WHERE source <> target
                  MERGE (source)-[:BIBLIOGRAPHIC_LINK]->(target)
            """, rels=rels)
    
    logger.info(f"[WRITE-ENTRY] {path_name}: nodes={len(nodes)}, rels={len(rels)}")
    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        try:
            with driver.session() as session:
                session.execute_write(tx_work)
            logger.info(f"[WRITE-OK] {path_name}")
            time.sleep(0.1)  # Уменьшен sleep
            return True
        except Exception as e:
            error_msg = str(e)
            # Проверяем, является ли это deadlock или transient error
            is_retryable = any(keyword in error_msg.lower() for keyword in
                             ['deadlock', 'lock', 'transient', 'timeout', 'concurrent'])

            if is_retryable:
                backoff = WRITE_BACKOFF * attempt * (1 + attempt * 0.5)  # Экспоненциальный backoff
                logger.warning(f"[WRITE-ERR] {path_name} attempt {attempt}/{MAX_WRITE_RETRIES}: {error_msg[:100]}... Retrying in {backoff:.1f}s")
                time.sleep(backoff)
            else:
                logger.error(f"[WRITE-ERR] {path_name} non-retryable error: {e}")
                return False

    logger.error(f"[WRITE-FAIL] {path_name} after {MAX_WRITE_RETRIES} attempts")
    return False

# ========== ОЧЕРЕДЬ И ПИСАТЕЛИ ==========
write_queue: "Queue[Any]" = Queue(maxsize=QUEUE_SIZE)
write_progress_bar = None  # Глобальный прогресс-бар для записи

def writer_loop(id: int):
    global write_progress_bar
    logger.info(f"Writer-{id} started")
    while True:
        item = None
        try:
            item = write_queue.get(timeout=30)
        except:
            # Timeout - no items in queue, continue waiting
            continue

        try:
            if item is None:
                write_queue.task_done()
                logger.info(f"Writer-{id} stopping")
                break

            path_name, nodes, rels = item
            logger.info(f"Writer-{id} processing {path_name} with {len(nodes)} nodes, {len(rels)} relationships")
            if write_to_neo4j(path_name, nodes, rels):
                append_checkpoint(CHECKPOINT_FILE, path_name)
                logger.info(f"[CHKPT] {path_name}")
                # Обновляем прогресс-бар записи
                if write_progress_bar:
                    write_progress_bar.update(1)
                    write_progress_bar.set_postfix_str(f"✓ {path_name[:40]}")
            else:
                logger.error(f"Writer-{id} failed to write {path_name}")
                if write_progress_bar:
                    write_progress_bar.set_postfix_str(f"✗ {path_name[:40]}")
        except Exception as e:
            logger.error(f"Writer-{id} error: {e}")
        finally:
            # Only call task_done if we actually got an item
            if item is not None:
                write_queue.task_done()

# Запускаем писателей лениво (только при вызове функции обработки),
# чтобы импорт модуля не порождал потоки в долгоживущих процессах (worker.py).
writer_threads: list = []


def ensure_writers():
    """Проверяет и перезапускает пул потоков-писателей."""
    global writer_threads
    writer_threads = [t for t in writer_threads if t.is_alive()]
    for i in range(len(writer_threads), WRITER_COUNT):
        t = Thread(target=writer_loop, args=(i + 1,), daemon=True)
        t.start()
        writer_threads.append(t)

def run_pre_load_tests() -> bool:
    """
    Run tests before data loading to ensure extraction logic works correctly

    Returns:
        True if all tests pass, False otherwise
    """
    import subprocess
    import sys
    from pathlib import Path

    logger.info("="*70)
    logger.info("RUNNING PRE-LOAD TESTS")
    logger.info("="*70)

    test_file = Path(__file__).parent.parent / "tests" / "test_reference_extraction.py"

    if not test_file.exists():
        logger.warning(f"Test file not found: {test_file}")
        logger.warning("Skipping pre-load tests")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Print test output
        if result.stdout:
            for line in result.stdout.split('\n'):
                if line.strip():
                    logger.info(f"  {line}")

        if result.returncode == 0:
            logger.info("="*70)
            logger.info("ALL TESTS PASSED - Proceeding with data load")
            logger.info("="*70)
            return True
        else:
            logger.error("="*70)
            logger.error("TESTS FAILED - Aborting data load")
            logger.error("="*70)
            if result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        logger.error(f"  {line}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Tests timed out after 30 seconds")
        return False
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return False


def process_all():
    # Run tests before processing
    if not run_pre_load_tests():
        logger.error("Pre-load tests failed. Aborting data loading.")
        logger.error("Please fix test failures before loading data.")
        return

    ensure_schema()

    try:
        with driver.session() as s:
            s.run("RETURN 1")
        logger.info("Neo4j connection OK")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        return
    
    # FULL PRODUCTION MODE - читаем из S3
    s3 = get_s3_client()
    ARCHIVE_BUCKET = "knowledge-map-data"
    ARCHIVE_PREFIX = "archives/pmc/"
    
    archives = s3.s3.list_objects(Bucket=ARCHIVE_BUCKET, Prefix=ARCHIVE_PREFIX)
    files = []
    for obj in archives.get('Contents', []):
        key = obj['Key']
        if key.endswith('.tar.gz'):
            files.append(key)
    files = sorted(files)
    logger.info(f"Found {len(files)} archives in S3")
    
    if not files:
        logger.warning("No PMC archives in S3 (legacy ftp source is removed). "
                       "Use new source pmc-oa-opendata via worker.py")
        return
    
    if not files:
        logger.error("No archives found in S3")
        return

    logger.info(f"Found archives: {len(files)}")
    for i, f in enumerate(files[:10]):
        logger.info(f"  {i+1}. {f}")
    if len(files) > 10:
        logger.info(f"  ... and {len(files) - 10} more archives")

    # ========== FULL PRODUCTION MODE ==========
    # Test mode disabled - processing all files
    # files = files[:1]  # Uncomment for testing

    # Показываем информацию об архивах
    logger.info(f"Processing archives from S3:")
    for i, f in enumerate(files):
        archive_name = f.split('/')[-1]
        logger.info(f"  {i+1}. {archive_name}")
    logger.info(f"Processing files: {len(files)} file(s)")
    
    # Очистка базы
    reset_database_full()

    # Создаём глобальный прогресс-бар для записи
    global write_progress_bar
    write_progress_bar = tqdm(total=len(files), desc="Writing to Neo4j", unit="file", position=1, leave=True)
    ensure_writers()

    try:
        # Параллельная обработка архивов из S3
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {executor.submit(parse_archive_from_s3, f): f for f in files}

            # Создаём прогресс-бар для парсинга
            with tqdm(total=len(files), desc="Parsing S3 archives", unit="archive", position=0, leave=True) as pbar:
                for future in as_completed(future_to_file):
                    file_key = future_to_file[future]
                    try:
                        res = future.result()
                        pbar.set_postfix_str(f"✓ {res[:40]}")
                        logger.info(f"[OK] {res} processed successfully")
                    except Exception as e:
                        pbar.set_postfix_str(f"✗ {file_key[:40]}")
                        logger.error(f"[PARSE-ERR] {file_key}: {e}")
                    finally:
                        pbar.update(1)
        
        # Очистка памяти
        import gc
        gc.collect()
        time.sleep(1)
        logger.info("Memory cleaned after file processing")
    except Exception as e:
        logger.error(f"[PARSE-ERR] Global processing error: {e}")
    
    # Ожидание завершения записи
    write_queue.join()
    for _ in range(WRITER_COUNT):
        write_queue.put(None)

    # Закрываем прогресс-бар записи
    if write_progress_bar:
        write_progress_bar.close()

    # Финальная статистика
    try:
        with driver.session() as s:
            result = s.run("MATCH (n:Document) RETURN count(n) as total_nodes")
            total_nodes = result.single()["total_nodes"]
            logger.info(f"TOTAL nodes loaded to database: {total_nodes}")
            
            result = s.run("MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as total_rels")
            total_rels = result.single()["total_rels"]
            logger.info(f"TOTAL relationships loaded to database: {total_rels}")
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
    
    logger.info("Processing completed.")

def _parse_local_xml(path: Path):
    """Парсит один локальный XML статьи PMC, возвращает (data, rels) или None."""
    try:
        with open(path, 'rb') as f:
            root = LET.parse(f).getroot()
        if LET.QName(root).localname != 'article':
            return None

        data, cited_list, _ = parse_article_optimized(root, 1)

        rels = []
        for cited in cited_list:
            link_id = cited.get('pmcid') or cited.get('pmid')
            if link_id:
                rels.append({
                    'source_pmid': link_id,
                    'source_title': cited.get('title'),
                    'target_pmid': data['uid'],
                    'target_title': data['title']
                })
        return data, rels
    except Exception as e:
        logger.error(f"Error processing XML {path.name}: {e}")
        return None


def process_all_local_articles(max_articles: int = 0, on_progress: Optional[Callable[[int, int, str], None]] = None):
    """Обрабатывает локально скачанные статьи PMC (XML из pmc-oa-opendata) в Neo4j."""
    global write_progress_bar

    ensure_schema()

    try:
        with driver.session() as s:
            s.run("RETURN 1")
        logger.info("Neo4j connection OK")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        return

    articles_dir = DATA_DIR
    if not articles_dir.exists():
        logger.error(f"Articles dir not found: {articles_dir}")
        return

    # Из локальных папок обрабатываем только самую свежую версию статьи.
    # Имя папки вида PMCxxxx.N, где N — версия пакета; версии могут накапливаться на диске.
    latest_version_dirs: Dict[str, str] = {}
    for d in articles_dir.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if "." in name:
            base, ver = name.rsplit(".", 1)
            if ver.isdigit():
                cur = latest_version_dirs.get(base)
                if cur is None or int(ver) > int(cur.rsplit(".", 1)[1]):
                    latest_version_dirs[base] = name
        else:
            latest_version_dirs[name] = name

    latest_dirs = set(latest_version_dirs.values())
    xml_files = sorted(
        f for f in articles_dir.glob("*/*.xml") if f.parent.name in latest_dirs
    )
    if max_articles > 0:
        xml_files = xml_files[:max_articles]
    if not xml_files:
        logger.warning(f"No XML files found in {articles_dir}")
        return

    logger.info(f"Found {len(xml_files)} article XML files")

    write_progress_bar = tqdm(total=len(xml_files), desc="Writing to Neo4j", unit="file", position=1, leave=True)
    ensure_writers()

    nodes, rels = [], []
    count = 0
    done = 0
    total_files = len(xml_files)
    if on_progress is not None:
        on_progress(0, total_files, "")

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {executor.submit(_parse_local_xml, f): f for f in xml_files}
            with tqdm(total=total_files, desc="Parsing article XML", unit="article", position=0, leave=True) as pbar:
                for future in as_completed(future_to_file):
                    file_key = future_to_file[future]
                    try:
                        res = future.result()
                        if res is not None:
                            data, article_rels = res
                            nodes.append(data)
                            rels.extend(article_rels)
                            count += 1

                            if count % BATCH_SIZE == 0 and (nodes or rels):
                                write_queue.put(("local_articles", nodes.copy(), rels.copy()))
                                nodes.clear()
                                rels.clear()
                                import gc
                                gc.collect()
                                time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"[PARSE-ERR] {file_key}: {e}")
                    finally:
                        pbar.update(1)
                        done += 1
                        if on_progress is not None:
                            on_progress(done, total_files, file_key.name)
    except Exception as e:
        logger.error(f"[PARSE-ERR] Global processing error: {e}")

    if nodes or rels:
        write_queue.put(("local_articles", nodes, rels))

    import gc
    gc.collect()
    time.sleep(1)

    write_queue.join()
    for _ in range(WRITER_COUNT):
        write_queue.put(None)

    if write_progress_bar:
        write_progress_bar.close()

    try:
        with driver.session() as s:
            result = s.run("MATCH (n:Document) RETURN count(n) as total_nodes")
            logger.info(f"TOTAL nodes loaded to database: {result.single()['total_nodes']}")
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")

    logger.info("Processing completed.")


if __name__ == "__main__":
    logger.info("Starting optimized PMC OA bulk files processing...")
    start = time.time()
    process_all()
    logger.info(f"Processing completed in {time.time() - start:.1f} seconds")
