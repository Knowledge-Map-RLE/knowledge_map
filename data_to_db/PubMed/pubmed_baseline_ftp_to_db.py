import gzip
import time
import datetime
import re
import json
from pathlib import Path
from queue import Queue
from threading import Thread
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree as LET  # type: ignore
from typing import Callable, Dict, Tuple, List, Any, Optional
from neo4j import exceptions as neo4j_exceptions  # type: ignore[attr-defined]
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import get_driver, load_checkpoint, append_checkpoint, setup_logging
from s3_client import get_s3_client

# ========== LOADER DISABLED ==========
# PubMed loader enabled for processing downloaded archives
LOADER_DISABLED = False

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR        = Path("..") / "data" / "PubMed"
LOG_FILE        = Path("./logs/article_to_neo4j.log")
CHECKPOINT_FILE = Path("./logs/parse_checkpoint.txt")

MAX_WORKERS       = 2        # потоки парсинга файлов
WRITER_COUNT      = 3        # число потоков-писателей
MAX_WRITE_RETRIES = 3
WRITE_BACKOFF     = 2
BATCH_SIZE        = 500      # увеличен для сокращения оверхеда транзакций
POOL_SIZE         = 3
QUEUE_SIZE        = MAX_WORKERS * 2
DEFAULT_ARTICLES_PER_FILE = 30000  # стартовая оценка статей в одном файле baseline
# ==================================

# ========== ЛОГИРОВАНИЕ ==========
logger = setup_logging(LOG_FILE)

# ========== NEO4J ==========
driver = get_driver(pool_size=POOL_SIZE)

# ========== ПРОГРЕСС ОБРАБОТКИ ==========
class _ProgressTracker:
    """Совокупный прогресс обработки в статьях (общий для всех файлов).

    Парсеры сообщают кол-во принятых статей через batch(); процессор
    сообщает о завершении файла через file_done() для калибровки оценки.
    Единицы измерения — статьи, поэтому полоса движется плавно.
    """

    def __init__(self, total_files: int, on_progress: Optional[Callable[[int, int, str], None]]):
        self.total_files = total_files
        self.on_progress = on_progress
        self.lock = threading.Lock()
        self.articles_done = 0          # суммарно принято статей (записано в очередь)
        self.last_count: Dict[str, int] = {}  # файл -> принято статей на текущий момент
        self.file_counts: List[int] = []      # финальные счётчики завершённых файлов
        self.estimate = DEFAULT_ARTICLES_PER_FILE

    def batch(self, path_name: str, count: int):
        """Вызывается из потока парсинга после каждой порции (батча) статей."""
        with self.lock:
            prev = self.last_count.get(path_name, 0)
            self.articles_done += count - prev
            self.last_count[path_name] = count
            processed = self.articles_done
            total = self._estimated_total()
        self._report(processed, total, path_name, count)

    def file_done(self, path_name: str, count: int):
        """Вызывается из главного потока, когда файл полностью распарсен."""
        with self.lock:
            self.last_count.pop(path_name, None)
            self.file_counts.append(count)
            self.estimate = round(sum(self.file_counts) / len(self.file_counts))
            processed = self.articles_done
            total = self._estimated_total()
        self._report(processed, total, path_name, count)

    def _estimated_total(self) -> int:
        return max(self.estimate * self.total_files, self.articles_done)

    def _report(self, processed: int, total: int, path_name: str, count: int):
        if self.on_progress is None:
            return
        try:
            self.on_progress(processed, total, f"{path_name} ({count} статей)")
        except Exception:
            logger.exception(f"Не удалось сообщить прогресс по {path_name}")

_progress_tracker: Optional[_ProgressTracker] = None

# ========== СХЕМА ==========
def check_existing_constraints():
    """Проверяем существующие ограничения в базе данных"""
    with driver.session() as session:
        result = session.run("SHOW CONSTRAINTS")
        constraints = []
        for record in result:
            constraints.append(dict(record))
        return constraints

def ensure_schema():
    with driver.session() as session:
        # Проверяем существующие ограничения
        constraints = check_existing_constraints()
        logger.info(f"Existing constraints: {len(constraints)}")
        for constraint in constraints:
            logger.info(f"  - {constraint.get('name', 'unnamed')}: {constraint.get('description', 'no description')}")
        
        # Удаляем проблемные constraint'ы на layer/level, если есть
        drop_problematic_layer_constraints(session)
        
        # Создаём схему для нашего алгоритма укладки
        session.run("""
            CREATE CONSTRAINT IF NOT EXISTS
            FOR (n:Article) REQUIRE n.uid IS UNIQUE
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Article) ON (n.layout_status)
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Article) ON (n.layer, n.level)
        """)
        # Индексы для быстрого поиска существующих документов при дедупликации по pmid/doi
        # и быстрого MERGE по uid (без них каждый батч сканирует все Document)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Document) ON (n.uid)
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Document) ON (n.pubmed_id)
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Document) ON (n.doi)
        """)
    logger.info("Schema constraints and indexes ensured")

# ========== ОЧИСТКА/СБРОС БАЗЫ ДАННЫХ ==========

def drop_problematic_layer_constraints(session):
    """Удаляет constraint'ы, связанные с layer/level, если они существуют."""
    try:
        # Явно пробуем известное имя (на случай если оно есть)
        session.run("DROP CONSTRAINT node_layer_level_unique IF EXISTS")
    except Exception:
        pass
    try:
        constraints = session.run("SHOW CONSTRAINTS").data()
        for constraint in constraints:
            constraint_name = constraint.get('name')
            description = constraint.get('description', '')
            if constraint_name and ('layer' in constraint_name.lower() or 'level' in constraint_name.lower()):
                try:
                    session.run(f"DROP CONSTRAINT {constraint_name}")
                    logger.info(f"Удалено проблемное ограничение: {constraint_name}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить ограничение {constraint_name}: {e}")
            elif 'layer' in description.lower() or 'level' in description.lower():
                # В некоторых версиях Neo4j имя может отсутствовать, ориентируемся по описанию
                logger.warning(f"Обнаружено потенциально проблемное ограничение без имени: {description}")
    except Exception as e:
        logger.info(f"Не удалось проверить/удалить проблемные ограничения: {e}")

def apoc_purge_database(session):
    """Очищает БД с использованием APOC периодических коммитов."""
    logger.info("APOC: очистка связей...")
    session.run(
        """
        CALL apoc.periodic.iterate(
          'MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN r',
          'DELETE r',
          {batchSize: 50000, parallel: false}
        )
        """
    )
    logger.info("APOC: очистка узлов...")
    session.run(
        """
        CALL apoc.periodic.iterate(
          'MATCH (n:Article) RETURN n',
          'DELETE n',
          {batchSize: 50000, parallel: false}
        )
        """
    )

def reset_database_full():
    """Полная очистка БД от данных статей и проблемных ограничений."""
    try:
        logger.info("Начинаем очистку базы данных...")
        with driver.session() as s:
            apoc_purge_database(s)
            drop_problematic_layer_constraints(s)
        logger.info("База данных полностью очищена")
    except Exception as e:
        logger.error(f"Ошибка при очистке базы: {e}")
        raise

# ========== УЛУЧШЕННЫЕ ФУНКЦИИ ПАРСИНГА ==========

# Предкомпилированный regex года
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

def extract_year_from_date(date_text):
    """Извлекает год из текста даты"""
    if not date_text:
        return None
    
    # Ищем 4-значный год (предкомпилированный шаблон)
    year_match = YEAR_RE.search(str(date_text))
    if year_match:
        year = int(year_match.group())
        # Валидация: год должен быть разумным
        if 1900 <= year <= 2030:
            return str(year)
    
    return None

def clean_author_name(forename, lastname):
    """Очищает имя автора"""
    if not forename and not lastname:
        return None
    
    # Объединяем имя и фамилию
    name_parts = []
    if forename:
        name_parts.append(forename.strip())
    if lastname:
        name_parts.append(lastname.strip())
    
    full_name = " ".join(name_parts).strip()
    
    # Проверяем на разумную длину
    if len(full_name) > 200:  # Слишком длинное имя
        return None
    
    return full_name if full_name else None

def extract_bibliographic_links_improved(elem, pmid):
    """Извлечение библиографических ссылок с возможными заголовками цитируемых статей.
    Возвращает список словарей: {'pmid': <cited_pmid>, 'title': <optional_title>}.
    """
    links = []
    unique_citations = set()

    # Проходим по Reference элементам, чтобы вместе с PMID попытаться достать заголовок
    for reference in elem.findall('.//ReferenceList/Reference'):
        # PMID цитируемой статьи
        cited_pmid_elem = reference.find('.//ArticleId[@IdType="pubmed"]')
        cited_pmid = cited_pmid_elem.text.strip() if cited_pmid_elem is not None and cited_pmid_elem.text else None
        if not cited_pmid or not cited_pmid.isdigit():
            continue

        # Пытаемся извлечь заголовок цитируемой статьи, если он есть в Reference
        # В PubMed это может быть Reference/Article/ArticleTitle или Reference/ArticleTitle
        title_elem = reference.find('.//Article/ArticleTitle') or reference.find('.//ArticleTitle')
        cited_title = None
        if title_elem is not None:
            try:
                cited_title = ''.join(title_elem.itertext()).strip()
            except Exception:
                # на всякий случай деградация к .text
                cited_title = (title_elem.text or '').strip()
        if cited_title and len(cited_title) > 1000:
            cited_title = cited_title[:1000] + '...'

        citation_key = f"{pmid}->{cited_pmid}"
        if citation_key in unique_citations:
            continue
        unique_citations.add(citation_key)
        links.append({'pmid': cited_pmid, 'title': cited_title})

    return links

# ========== ЗАПИСЬ ==========

def write_to_neo4j(path_name: str, nodes: list[dict], rels: list[dict]) -> bool:
    global driver

    def tx_work(tx):
        if nodes:
            doc_nodes = []
            for node in nodes:
                pmid = node.get('pmid')
                doc_nodes.append({
                    'uid': pmid,
                    'original_filename': f"{pmid}.xml",
                    'md5_hash': f"pubmed_{pmid}",
                    's3_key': f"documents/{pmid}/{pmid}.md",
                    'docling_raw_md_s3_key': f"documents/{pmid}/{pmid}.md",
                    'formatted_md_s3_key': f"documents/{pmid}/{pmid}.md",
                    'title': node.get('title', ''),
                    'authors': json.dumps(node.get('authors', [])),
                    'abstract': node.get('abstract', ''),
                    'keywords': json.dumps(node.get('keywords', [])),
                    'journal': node.get('journal', ''),
                    'doi': node.get('doi', ''),
                    'pubmed_id': pmid,
                    'pmc_id': None,
                    'source': 'pubmed',
                    'is_open_access': True,
                    'is_processed': True,
                    'processing_status': 'processed',
                })
            tx.run("""
                UNWIND $nodes AS row
                  WITH row
                  OPTIONAL MATCH (existing1:Document)
                    WHERE existing1.pubmed_id = row.pmid
                      AND row.pmid IS NOT NULL AND row.pmid <> ''
                  WITH row, existing1
                  OPTIONAL MATCH (existing2:Document)
                    WHERE existing1 IS NULL
                      AND existing2.doi = row.doi
                      AND row.doi IS NOT NULL AND row.doi <> ''
                  WITH row,
                       CASE
                         WHEN existing1 IS NOT NULL THEN existing1
                         WHEN existing2 IS NOT NULL THEN existing2
                         ELSE null
                       END AS existing
                  WITH row, CASE WHEN existing IS NOT NULL THEN existing.uid ELSE row.uid END AS uid
                  MERGE (n:Document {uid: uid})
                  ON CREATE SET 
                      n.original_filename = row.original_filename,
                      n.md5_hash = row.md5_hash,
                      n.s3_key = row.s3_key,
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
                      n.processing_status = row.processing_status
                  ON MATCH SET 
                      n.original_filename = coalesce(n.original_filename, row.original_filename),
                      n.md5_hash = coalesce(n.md5_hash, row.md5_hash),
                      n.s3_key = coalesce(n.s3_key, row.s3_key),
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
                      n.processing_status = row.processing_status
            """, nodes=doc_nodes)
        if rels:
            # УНИФИЦИРОВАННАЯ СЕМАНТИКА SOURCE/TARGET:
            # Направление: SOURCE (cited, старая) -> TARGET (citing, новая)
            tx.run("""
                UNWIND $rels AS r
                  MERGE (source:Article {uid: r.source_pmid})
                    ON CREATE SET
                      source.title = coalesce(r.source_title, source.title)
                    ON MATCH SET
                      source.title = coalesce(source.title, r.source_title)
                  MERGE (target:Article {uid: r.target_pmid})
                    ON CREATE SET
                      target.title = coalesce(r.target_title, target.title)
                    ON MATCH SET
                      target.title = coalesce(target.title, r.target_title)
                  WITH source, target
                  WHERE source <> target
                  MERGE (source)-[:BIBLIOGRAPHIC_LINK]->(target)
            """, rels=rels)

    logger.info(f"[WRITE-ENTRY] {path_name}: nodes={len(nodes)}, rels={len(rels)}")
    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        try:
            with driver.session() as session:
                session.execute_write(tx_work, timeout=120_000)
            logger.info(f"[WRITE-OK] {path_name}")
            # Увеличенная пауза для освобождения памяти
            time.sleep(0.2)
            return True
        except (neo4j_exceptions.ServiceUnavailable,
                neo4j_exceptions.SessionExpired,
                neo4j_exceptions.TransientError,
                neo4j_exceptions.ClientError,
                neo4j_exceptions.ConstraintError,
                neo4j_exceptions.CypherSyntaxError,
                OSError) as e:
            logger.warning(f"[WRITE-ERR] {path_name} attempt {attempt}: {e}")
            try:
                driver.close()
            except:
                pass
            time.sleep(WRITE_BACKOFF * attempt)
            driver = get_driver()
    logger.error(f"[WRITE-FAIL] {path_name}")
    return False

# ========== ОЧЕРЕДЬ И ПИСАТЕЛИ ==========
write_queue: "Queue[Any]" = Queue(maxsize=QUEUE_SIZE)
writer_threads: list = []
failed_write_files: set = set()  # файлы, у которых не удалось записать хотя бы один батч

def ensure_writers():
    """Проверяет и перезапускает пул потоков-писателей."""
    global writer_threads
    writer_threads = [t for t in writer_threads if t.is_alive()]
    for i in range(len(writer_threads), WRITER_COUNT):
        t = Thread(target=writer_loop, args=(i + 1,), daemon=True)
        t.start()
        writer_threads.append(t)

def writer_loop(id: int):
    logger.info(f"Writer-{id} started")
    while True:
        item = write_queue.get()
        if item is None:
            write_queue.task_done()
            logger.info(f"Writer-{id} stopping")
            break
        path_name, nodes, rels = item
        try:
            if not write_to_neo4j(path_name, nodes, rels):
                failed_write_files.add(path_name)
        except Exception as e:
            logger.error(f"Writer-{id} unexpected error for {path_name}: {e}")
            failed_write_files.add(path_name)
        write_queue.task_done()

# ========== ПАРСИНГ ОДНОГО ФАЙЛА ==========
MANDATORY_FIELDS = ['pmid', 'title', 'journal']  # publication_time сделано необязательным

def parse_one_file(path: Path):
    nodes, rels = [], []
    count = 0
    total_articles = 0
    rejected_articles = 0
    rejection_reasons: Dict[str, int] = {}
    total_rels_found = 0
    
    with gzip.open(path, 'rb') as gf:
        context = LET.iterparse(gf, events=("end",))
        for _, elem in context:
            if elem.tag == "PubmedArticle":
                total_articles += 1
                
                # Извлекаем PMID
                pmid = elem.findtext('.//PMID')
                if not pmid or not pmid.strip():
                    rejected_articles += 1
                    rejection_reasons["missing: pmid"] = rejection_reasons.get("missing: pmid", 0) + 1
                    elem.clear()
                    continue
                
                pmid = pmid.strip()
                
                # Извлекаем заголовок
                title_elem = elem.find('.//ArticleTitle')
                title = None
                if title_elem is not None:
                    title = ''.join(title_elem.itertext()).strip()
                    if len(title) > 1000:  # Слишком длинный заголовок
                        title = title[:1000] + "..."
                
                # Извлекаем журнал
                journal = elem.findtext('.//Journal/Title')
                if journal and len(journal) > 500:  # Слишком длинное название журнала
                    journal = journal[:500] + "..."
                
                # Извлекаем год публикации
                year_text = (elem.findtext('.//Journal/JournalIssue/PubDate/Year')
                           or elem.findtext('.//Journal/JournalIssue/PubDate/MedlineDate') or '')
                publication_time = extract_year_from_date(year_text)
                
                # Извлекаем DOI
                doi = elem.findtext('.//ArticleIdList/ArticleId[@IdType="doi"]') or None
                if doi and len(doi) > 200:  # Слишком длинный DOI
                    doi = doi[:200]
                
                # Извлекаем абстракт
                abstract_elem = elem.find('.//Abstract/AbstractText')
                abstract = None
                if abstract_elem is not None:
                    abstract = ''.join(abstract_elem.itertext()).strip()
                    if len(abstract) > 5000:  # Слишком длинный абстракт
                        abstract = abstract[:5000] + "..."
                
                # Извлекаем авторов (ограничиваем количество)
                authors = []
                author_elements = elem.findall('.//AuthorList/Author')
                for au in author_elements[:50]:  # Максимум 50 авторов
                    forename = au.findtext('ForeName')
                    lastname = au.findtext('LastName')
                    author_name = clean_author_name(forename, lastname)
                    if author_name:
                        authors.append(author_name)
                
                # Извлекаем ключевые слова (ограничиваем количество)
                keywords = []
                keyword_elements = elem.findall('.//MeshHeadingList/MeshHeading/DescriptorName')
                for dn in keyword_elements[:30]:  # Максимум 30 ключевых слов
                    if dn.text and dn.text.strip():
                        keyword = dn.text.strip()
                        if len(keyword) <= 200:  # Разумная длина ключевого слова
                            keywords.append(keyword)
                
                data = {
                    'pmid': pmid,
                    'doi': doi,
                    'title': title,
                    'publication_time': publication_time,
                    'journal': journal,
                    'abstract': abstract,
                    'authors': authors,
                    'keywords': keywords
                }
                
                # Проверяем обязательные поля
                missing_fields = []
                for field in MANDATORY_FIELDS:
                    if not data[field]:
                        missing_fields.append(field)
                
                if missing_fields:
                    rejected_articles += 1
                    reason = f"missing: {', '.join(missing_fields)}"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                else:
                    nodes.append(data)
                    count += 1
                
                # Логируем PMID статьи
                logger.info(f"[PMID] {pmid}")
                # Извлекаем библиографические ссылки (с возможными заголовками)
                cited_list = extract_bibliographic_links_improved(elem, pmid)
                # Логируем количество ссылок
                logger.info(f"[PMID {pmid}] links_count={len(cited_list)}")
                # УНИФИЦИРОВАННАЯ СЕМАНТИКА SOURCE/TARGET:
                # - SOURCE (left): cited reference (старая статья) - низкие слои
                # - TARGET (right): citing article (новая статья) - высокие слои
                # - Направление: SOURCE -> TARGET (старая -> новая)
                # Логируем каждую ссылку и добавляем в пакет (с заголовками, если есть)
                for cited in cited_list:
                    link_pmid = cited['pmid']
                    link_title = cited.get('title')
                    rels.append({
                        'source_pmid': link_pmid,      # SOURCE: cited reference (старая)
                        'source_title': link_title,
                        'target_pmid': pmid,           # TARGET: citing article (новая)
                        'target_title': title
                    })
                
                total_rels_found += len(cited_list)
                elem.clear()

                if count % BATCH_SIZE == 0:
                    logger.info(f"{path.name}: enqueue batch #{count//BATCH_SIZE}")
                    write_queue.put((path.name, nodes.copy(), rels.copy()))
                    if _progress_tracker is not None:
                        _progress_tracker.batch(path.name, count)
                    nodes.clear()
                    rels.clear()
                    # Принудительная очистка памяти каждые 5 батчей
                    if count % (BATCH_SIZE * 5) == 0:
                        import gc
                        gc.collect()
                        time.sleep(0.5)

    # остаток
    if nodes or rels:
        logger.info(f"{path.name}: enqueue final batch")
        write_queue.put((path.name, nodes, rels))
        if _progress_tracker is not None:
            _progress_tracker.batch(path.name, count)

    # Выводим статистику
    logger.info(f"{path.name}: Обработано статей: {total_articles}")
    logger.info(f"{path.name}: Принято статей: {count}")
    logger.info(f"{path.name}: Отклонено статей: {rejected_articles}")
    logger.info(f"{path.name}: Найдено связей цитирования: {total_rels_found}")
    if rejection_reasons:
        logger.info(f"{path.name}: Причины отклонения:")
        for reason, count_reason in rejection_reasons.items():
            logger.info(f"  - {reason}: {count_reason} статей")

    return path.name

# ========== ГЛАВНЫЙ ПРОЦЕСС ==========

def process_all():
    """Для совместимости с __main__."""
    return process_all_files()


def process_xml_gz(s3_key: str) -> bool:
    """Обрабатывает один XML.gz архив из S3.
    
    Args:
        s3_key: S3 ключ, например 'archives/pubmed/pubmed24n0001.xml.gz'
    
    Returns:
        True при успехе
    """
    from pathlib import Path
    from .s3_client import get_s3_client
    
    ensure_schema()
    
    # Скачиваем из S3 во временный файл
    s3 = get_s3_client()
    filename = s3_key.split('/')[-1]
    temp_dir = Path("./temp_pubmed")
    temp_dir.mkdir(exist_ok=True)
    local_path = temp_dir / filename
    
    logger.info(f"Downloading {s3_key} to {local_path}")
    s3.s3.download_file("knowledge-map-data", s3_key, str(local_path))
    
    # Обрабатываем локальный файл
    try:
        parse_one_file(local_path)
        return True
    finally:
        # Удаляем временный файл
        if local_path.exists():
            local_path.unlink()


def process_all_files(
    data_dir: Optional[Path] = None,
    max_files: int = 0,
    reset_db: bool = False,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    checkpoint_file: Optional[Path] = None,
):
    """Главная функция обработки - вызывается из worker.py.

    Аргументы:
        data_dir: папка с .xml.gz архивами (по умолчанию DATA_DIR).
        max_files: ограничение количества обрабатываемых файлов (0 — все).
        reset_db: очистить базу данных перед загрузкой.
        on_progress: колбэк (обработано, всего, текущий файл) для прогресса обработки.
        checkpoint_file: путь к файлу чекпоинта (по умолчанию CHECKPOINT_FILE).
    """
    if LOADER_DISABLED:
        logger.info("PubMed loader is disabled by config, skipping")
        return

    ckpt = checkpoint_file if checkpoint_file else CHECKPOINT_FILE

    ensure_schema()

    # проверка соединения
    try:
        with driver.session() as s:
            s.run("RETURN 1")
        logger.info("Neo4j connection OK")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        return

    data_dir = Path(data_dir) if data_dir else DATA_DIR
    files = sorted(data_dir.rglob("*.xml.gz"))
    if not files:
        logger.error(f"Не найдено файлов для обработки в {data_dir}")
        return

    processed = load_checkpoint(ckpt)
    if processed:
        files = [f for f in files if f.name not in processed]
        logger.info(
            f"Пропуск уже обработанных файлов, осталось к обработке: {len(files)}"
        )

    if max_files > 0:
        files = files[:max_files]

    logger.info(f"Найдено файлов: {len(files)} в {data_dir}")
    for i, file in enumerate(files, 1):
        logger.info(f"  {i}. {file.name}")

    if reset_db:
        logger.info("Очистка базы данных перед загрузкой")
        reset_database_full()

    try:
        # Параллельная обработка файлов парсером
        ensure_writers()
        total_files = len(files)
        tracker = _ProgressTracker(total_files, on_progress)
        global _progress_tracker
        _progress_tracker = tracker
        if on_progress is not None:
            on_progress(0, tracker._estimated_total(), "Начало обработки")
        completed = 0
        completed_files: List[str] = []
        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_file = {executor.submit(parse_one_file, f): f for f in files}
                for future in as_completed(future_to_file):
                    file_to_process = future_to_file[future]
                    try:
                        res = future.result()
                        logger.info(f"[OK] {res} обработан успешно")
                        completed_files.append(file_to_process.name)
                    except Exception as e:
                        logger.error(f"[PARSE-ERR] {file_to_process.name}: {e}")
                    finally:
                        completed += 1
                        count = tracker.last_count.get(file_to_process.name, 0)
                        tracker.file_done(file_to_process.name, count)
        finally:
            _progress_tracker = None
        # Принудительная очистка памяти после партии файлов
        import gc
        gc.collect()
        time.sleep(1)
        logger.info("Память очищена после обработки файлов")
    except Exception as e:
        logger.error(f"[PARSE-ERR] Глобальная ошибка обработки: {e}")

    # ждём пока писатели обработают всё
    write_queue.join()
    for _ in range(WRITER_COUNT):
        write_queue.put(None)

    # Помечаем чекпойнтом только файлы, чьи батчи полностью записаны успешно
    for fname in completed_files:
        if fname not in failed_write_files:
            append_checkpoint(ckpt, fname)
            logger.info(f"[CHKPT] {fname}")

    # Показываем итоговую статистику
    try:
        with driver.session() as s:
            result = s.run("MATCH (n:Article) RETURN count(n) as total_nodes")
            total_nodes = result.single()["total_nodes"]
            logger.info(f"ИТОГО загружено узлов в базу: {total_nodes}")

            result = s.run("MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as total_rels")
            total_rels = result.single()["total_rels"]
            logger.info(f"ИТОГО загружено связей в базу: {total_rels}")
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")

    logger.info("Обработка завершена.")

if __name__ == "__main__":
    if LOADER_DISABLED:
        print("="*70)
        print("PUBMED LOADER IS DISABLED")
        print("="*70)
        print()
        print("This data loader has been disabled as per project requirements.")
        print()
        print("Reason:")
        print("  - PubMed XML files have limited bibliographic reference data")
        print("  - PubMed Central provides more comprehensive reference sections")
        print("  - To avoid data quality issues, only PMC loader should be used")
        print()
        print("To load data, please use:")
        print("  python worker_data_to_db/PubMed_Central/pmc_oa_bulk_to_db.py")
        print()
        print("="*70)
        exit(0)

    start = time.time()
    process_all()
    logger.info(f"Finished in {time.time() - start:.1f}s")
