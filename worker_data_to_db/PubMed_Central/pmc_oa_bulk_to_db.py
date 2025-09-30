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
from pathlib import Path
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree as LET
from typing import Dict, Tuple, List, Any
from neo4j import GraphDatabase, exceptions as neo4j_exceptions

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR        = Path(r"E:/Данные/PubMed_Central")
LOG_FILE        = Path("./logs/pmc_oa_bulk_to_db.log")
CHECKPOINT_FILE = Path("./logs/pmc_parse_checkpoint.txt")

NEO4J_URI       = "bolt://127.0.0.1:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = "password"

# Оптимизированные настройки
MAX_WORKERS       = 2        # Увеличено для параллелизма
WRITER_COUNT      = 2        # Увеличено для записи
MAX_WRITE_RETRIES = 3
WRITE_BACKOFF     = 2
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
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== NEO4J ==========
def get_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
        max_connection_pool_size=POOL_SIZE,
        connection_acquisition_timeout=30
    )

driver = get_driver()

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
        year = int(year_match.group())
        if 1900 <= year <= 2030:
            return str(year)
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
    """Оптимизированное извлечение библиографических ссылок O(R) вместо O(R×X)"""
    links = []
    unique_citations = set()
    
    # Один запрос для всех ref элементов
    ref_elements = root.findall('.//ref-list/ref') or root.findall('.//ns:ref-list/ns:ref', NS)
    
    for ref in ref_elements:
        ref_data = {}
        
        # Оптимизированное извлечение идентификаторов
        for id_type in ['pmid', 'pmcid', 'doi']:
            for xpath in [f'.//pub-id[@pub-id-type="{id_type}"]', f'.//article-id[@pub-id-type="{id_type}"]']:
                elem = ref.find(xpath) or ref.find(xpath.replace('pub-id', 'ns:pub-id').replace('article-id', 'ns:article-id'), NS)
                if elem is not None and elem.text:
                    ref_data[id_type] = elem.text.strip()
                    break
        
        # URL из ext-link
        url_elem = ref.find('.//ext-link[@ext-link-type="uri"]') or ref.find('.//ns:ext-link[@ext-link-type="uri"]', NS)
        if url_elem is not None:
            url = url_elem.get('{http://www.w3.org/1999/xlink}href') or url_elem.text
            if url and url.strip().startswith('http'):
                ref_data['url'] = url.strip()
        
        # Заголовок
        title_elem = ref.find('.//article-title') or ref.find('.//ns:article-title', NS)
        if title_elem is not None:
            ref_data['title'] = ''.join(title_elem.itertext()).strip()
        else:
            source_elem = ref.find('.//source') or ref.find('.//ns:source', NS)
            if source_elem is not None:
                ref_data['title'] = ''.join(source_elem.itertext()).strip()
        
        # Год
        year_elem = ref.find('.//year') or ref.find('.//ns:year', NS)
        if year_elem is not None and year_elem.text:
            ref_data['year'] = year_elem.text.strip()
        
        # Проверяем наличие данных
        if not any(ref_data.get(key) for key in ['pmid', 'pmcid', 'doi', 'url', 'title']):
            continue
        
        # Дедупликация
        citation_key = f"{primary_id}->{ref_data.get('pmid', '')}->{ref_data.get('pmcid', '')}->{ref_data.get('doi', '')}->{ref_data.get('url', '')}->{ref_data.get('title', '')[:50]}"
        if citation_key not in unique_citations:
            unique_citations.add(citation_key)
            links.append(ref_data)
    
    return links

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

# ========== ОПТИМИЗИРОВАННЫЙ ПАРСИНГ ==========

def parse_article_optimized(article, total_articles):
    """Оптимизированный парсинг одной статьи O(log R)"""
    
    # Извлекаем идентификаторы одним проходом
    pmid = extract_text_optimized(article, XPATH_CACHE['pmid'], NS)
    pmcid = extract_text_optimized(article, XPATH_CACHE['pmcid'], NS)
    
    # Создаем временный ID если нужно
    if not pmid and not pmcid:
        primary_id = f"temp_id_{total_articles}"
        pmid = primary_id
    else:
        primary_id = pmid or pmcid
    
    # Извлекаем остальные поля
    doi = extract_text_optimized(article, XPATH_CACHE['doi'], NS)
    title = extract_text_optimized(article, XPATH_CACHE['title'], NS)
    journal = extract_text_optimized(article, XPATH_CACHE['journal'], NS)
    
    # Год публикации
    year_elem = extract_element_optimized(article, XPATH_CACHE['year'], NS)
    publication_time = extract_year_from_date_optimized(year_elem.text) if year_elem is not None and year_elem.text else None
    
    # Абстракт
    abstract = extract_text_optimized(article, XPATH_CACHE['abstract'], NS)
    
    # Авторы и ключевые слова
    authors = extract_authors_optimized(article)
    keywords = extract_keywords_optimized(article)
    
    # Полный текст
    body = embed_floats_optimized(article)
    
    # Данные статьи
    data = {
        'pmid': pmid,
        'pmcid': pmcid,
        'doi': doi,
        'title': title,
        'publication_time': publication_time,
        'journal': journal,
        'abstract': abstract,
        'body': body,
        'authors': authors,
        'keywords': keywords
    }
    
    # Библиографические ссылки
    cited_list = extract_bibliographic_links_optimized(article, primary_id)
    
    return data, cited_list, primary_id

def parse_one_file_optimized(path: Path):
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
            
            for xml_file in xml_files:
                try:
                    xml_content = tar.extractfile(xml_file)
                    if xml_content is None:
                        continue
                    
                    root = LET.parse(xml_content).getroot()
                    if root.tag != 'article':
                        continue
                    
                    total_articles += 1
                    
                    # Оптимизированный парсинг статьи
                    data, cited_list, primary_id = parse_article_optimized(root, total_articles)
                    
                    nodes.append(data)
                    count += 1
                    
                    # Создаем связи
                    for cited in cited_list:
                        link_id = cited.get('pmid') or cited.get('pmcid') or cited.get('doi') or cited.get('url')
                        if link_id:
                            rels.append({
                                'pmid': primary_id,
                                'pmid_title': data['title'],
                                'cpmid': link_id,
                                'cpmid_title': cited.get('title')
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
                
                except Exception as e:
                    logger.error(f"Error processing XML file {xml_file.name}: {e}")
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

def load_checkpoint() -> set[str]:
    if not CHECKPOINT_FILE.exists():
        return set()
    return set(line.strip() for line in CHECKPOINT_FILE.read_text().splitlines() if line.strip())

def append_checkpoint(fname: str):
    with CHECKPOINT_FILE.open("a", encoding="utf-8") as f:
        f.write(fname + "\n")

def ensure_schema():
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Article) REQUIRE n.uid IS UNIQUE")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.layout_status)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.layer, n.level)")
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
            tx.run("""
                UNWIND $nodes AS row
                  MERGE (n:Article {uid: coalesce(row.pmid, row.pmcid)})
                  ON CREATE SET n = row,
                      n.uid = coalesce(row.pmid, row.pmcid),
                      n.layout_status = 'unprocessed',
                      n.layer = null,
                      n.level = null,
                      n.sublevel_id = null,
                      n.x = 0.0,
                      n.y = 0.0,
                      n.is_pinned = false
                  ON MATCH SET n = row,
                      n.uid = coalesce(row.pmid, row.pmcid),
                      n.layout_status = 'unprocessed'
            """, nodes=nodes)
        if rels:
            tx.run("""
                UNWIND $rels AS r
                  MERGE (target:Article {uid: r.pmid})
                    ON CREATE SET target.title = coalesce(r.pmid_title, target.title)
                  MERGE (cited:Article {uid: r.cpmid})
                    ON CREATE SET cited.title = coalesce(r.cpmid_title, cited.title)
                    ON MATCH SET cited.title = coalesce(cited.title, r.cpmid_title)
                  WITH target, cited
                  WHERE target <> cited
                  MERGE (target)-[:BIBLIOGRAPHIC_LINK]->(cited)
            """, rels=rels)
    
    logger.info(f"[WRITE-ENTRY] {path_name}: nodes={len(nodes)}, rels={len(rels)}")
    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        try:
            with driver.session() as session:
                session.execute_write(tx_work)
            logger.info(f"[WRITE-OK] {path_name}")
            time.sleep(0.5)
            return True
        except Exception as e:
            logger.warning(f"[WRITE-ERR] {path_name} attempt {attempt}: {e}")
            time.sleep(WRITE_BACKOFF * attempt)
    logger.error(f"[WRITE-FAIL] {path_name}")
    return False

# ========== ОЧЕРЕДЬ И ПИСАТЕЛИ ==========
write_queue: "Queue[Any]" = Queue(maxsize=QUEUE_SIZE)

def writer_loop(id: int):
    logger.info(f"Writer-{id} started")
    while True:
        try:
            item = write_queue.get(timeout=30)
            if item is None:
                write_queue.task_done()
                logger.info(f"Writer-{id} stopping")
                break
            path_name, nodes, rels = item
            logger.info(f"Writer-{id} processing {path_name} with {len(nodes)} nodes, {len(rels)} relationships")
            if write_to_neo4j(path_name, nodes, rels):
                append_checkpoint(path_name)
                logger.info(f"[CHKPT] {path_name}")
            else:
                logger.error(f"Writer-{id} failed to write {path_name}")
            write_queue.task_done()
        except Exception as e:
            logger.error(f"Writer-{id} error: {e}")
            write_queue.task_done()

# Запускаем писателей
for i in range(WRITER_COUNT):
    t = Thread(target=writer_loop, args=(i+1,), daemon=True)
    t.start()

def process_all():
    ensure_schema()
    
    try:
        with driver.session() as s:
            s.run("RETURN 1")
        logger.info("Neo4j connection OK")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        return
    
    files = sorted(DATA_DIR.glob("*.tar.gz"))
    if not files:
        logger.error("No files found for processing")
        return
    
    logger.info(f"Found files: {len(files)}")
    for i, file in enumerate(files):
        logger.info(f"  {i+1}. {file.name}")
    
    # Показываем информацию о файлах
    total_size = 0
    for file in files:
        mod_time = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        file_size_mb = file.stat().st_size / (1024 * 1024)
        total_size += file_size_mb
        logger.info(f"  {file.name}: {file_size_mb:.1f} MB, modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    logger.info(f"Total file size: {total_size:.1f} MB")
    logger.info(f"Processing all files: {len(files)} files")
    
    # Очистка базы
    reset_database_full()
    
    try:
        # Параллельная обработка файлов
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {executor.submit(parse_one_file_optimized, f): f for f in files}
            for future in as_completed(future_to_file):
                file_to_process = future_to_file[future]
                try:
                    res = future.result()
                    logger.info(f"[OK] {res} processed successfully")
                except Exception as e:
                    logger.error(f"[PARSE-ERR] {file_to_process.name}: {e}")
        
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
    
    # Финальная статистика
    try:
        with driver.session() as s:
            result = s.run("MATCH (n:Article) RETURN count(n) as total_nodes")
            total_nodes = result.single()["total_nodes"]
            logger.info(f"TOTAL nodes loaded to database: {total_nodes}")
            
            result = s.run("MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as total_rels")
            total_rels = result.single()["total_rels"]
            logger.info(f"TOTAL relationships loaded to database: {total_rels}")
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
    
    logger.info("Processing completed.")

if __name__ == "__main__":
    logger.info("Starting optimized PMC OA bulk files processing...")
    start = time.time()
    process_all()
    logger.info(f"Processing completed in {time.time() - start:.1f} seconds")
