import gzip
import logging
import time
import datetime
import re
from pathlib import Path
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from lxml import etree as LET  # type: ignore
from typing import Dict, Tuple, List, Any
from neo4j import GraphDatabase, exceptions as neo4j_exceptions  # type: ignore[attr-defined]

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR        = Path(r"D:/Данные/PubMed")
LOG_FILE        = Path("./logs/article_to_neo4j.log")
CHECKPOINT_FILE = Path("./logs/parse_checkpoint.txt")

NEO4J_URI       = "bolt://127.0.0.1:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = "password"

MAX_WORKERS       = 2        # потоки парсинга файлов
WRITER_COUNT      = 3        # число потоков-писателей
MAX_WRITE_RETRIES = 3
WRITE_BACKOFF     = 2
BATCH_SIZE        = 500      # увеличен для сокращения оверхеда транзакций
POOL_SIZE         = 3
QUEUE_SIZE        = MAX_WORKERS * 2
# ==================================

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

# ========== ЧЕКПОИНТЫ ==========
def load_checkpoint() -> set[str]:
    if not CHECKPOINT_FILE.exists():
        return set()
    return set(line.strip() for line in CHECKPOINT_FILE.read_text().splitlines() if line.strip())

def append_checkpoint(fname: str):
    with CHECKPOINT_FILE.open("a", encoding="utf-8") as f:
        f.write(fname + "\n")

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
            tx.run("""
                UNWIND $nodes AS row
                  MERGE (n:Article {uid: row.pmid})
                  ON CREATE SET n = row,
                      n.uid = row.pmid,
                      n.layout_status = 'unprocessed',
                      n.layer = null,
                      n.level = null,
                      n.sublevel_id = null,
                      n.x = 0.0,
                      n.y = 0.0,
                      n.is_pinned = false
                  ON MATCH SET n = row,
                      n.uid = row.pmid,
                      n.layout_status = 'unprocessed'
            """, nodes=nodes)
        if rels:
            tx.run("""
                UNWIND $rels AS r
                  MERGE (target:Article {uid: r.pmid})
                    ON CREATE SET
                      target.title = coalesce(r.pmid_title, target.title)
                  MERGE (cited:Article {uid: r.cpmid})
                    ON CREATE SET
                      cited.title = coalesce(r.cpmid_title, cited.title)
                    ON MATCH SET
                      cited.title = coalesce(cited.title, r.cpmid_title)
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
            # Увеличенная пауза для освобождения памяти
            time.sleep(0.2)
            return True
        except (neo4j_exceptions.ServiceUnavailable,
                neo4j_exceptions.SessionExpired,
                neo4j_exceptions.TransientError,
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

def writer_loop(id: int):
    logger.info(f"Writer-{id} started")
    while True:
        item = write_queue.get()
        if item is None:
            write_queue.task_done()
            logger.info(f"Writer-{id} stopping")
            break
        path_name, nodes, rels = item
        if write_to_neo4j(path_name, nodes, rels):
            append_checkpoint(path_name)
            logger.info(f"[CHKPT] {path_name}")
        write_queue.task_done()

# запускаем WRITER_COUNT потоков
for i in range(WRITER_COUNT):
    t = Thread(target=writer_loop, args=(i+1,), daemon=True)
    t.start()

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
                # Логируем каждую ссылку и добавляем в пакет (с заголовками, если есть)
                for cited in cited_list:
                    link_pmid = cited['pmid']
                    link_title = cited.get('title')
                    rels.append({'pmid': pmid, 'pmid_title': title, 'cpmid': link_pmid, 'cpmid_title': link_title})
                
                total_rels_found += len(cited_list)
                elem.clear()

                if count % BATCH_SIZE == 0:
                    logger.info(f"{path.name}: enqueue batch #{count//BATCH_SIZE}")
                    write_queue.put((path.name, nodes.copy(), rels.copy()))
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
    ensure_schema()

    # проверка соединения
    try:
        with driver.session() as s:
            s.run("RETURN 1")
        logger.info("Neo4j connection OK")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        return

    files = sorted(DATA_DIR.glob("*.xml.gz"))
    if not files:
        logger.error("Не найдено файлов для обработки")
        return
    
    # Показываем все доступные файлы
    logger.info(f"Найдено файлов: {len(files)}")
    for i, file in enumerate(files):
        logger.info(f"  {i+1}. {file.name}")
    
    # Берём последние 3 файла
    latest_files = files[-3:]  # Последние 3 файла
    logger.info(f"Обрабатываем последние 3 файла:")
    for i, file in enumerate(latest_files, 1):
        logger.info(f"  {i}. {file.name}")
    
    # Показываем информацию о файлах
    total_size = 0
    for file in latest_files:
        mod_time = datetime.datetime.fromtimestamp(file.stat().st_mtime)
        file_size_mb = file.stat().st_size / (1024 * 1024)
        total_size += file_size_mb
        logger.info(f"  {file.name}: {file_size_mb:.1f} MB, модифицирован: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    logger.info(f"Общий размер файлов: {total_size:.1f} MB")
    
    # Временная настройка: обрабатываем только один предпоследний файл (или последний, если файлов < 2)
    files_to_process = files[-2:-1] if len(files) >= 2 else files[-1:]
    logger.info(f"Временная настройка: обрабатываем файл: {[f.name for f in files_to_process]}")
    
    # Очищаем базу данных перед загрузкой нового файла
    reset_database_full()

    try:
        # Параллельная обработка файлов парсером
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {executor.submit(parse_one_file, f): f for f in files_to_process}
            for future in as_completed(future_to_file):
                file_to_process = future_to_file[future]
                try:
                    res = future.result()
                    logger.info(f"[OK] {res} обработан успешно")
                except Exception as e:
                    logger.error(f"[PARSE-ERR] {file_to_process.name}: {e}")
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
    start = time.time()
    process_all()
    logger.info(f"Finished in {time.time() - start:.1f}s")
