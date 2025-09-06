import gzip
import logging
import time
import datetime
from pathlib import Path
from queue import Queue
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from neo4j import GraphDatabase, exceptions as neo4j_exceptions

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR        = Path(r"D:/Данные/PubMed")
LOG_FILE        = Path("./logs/article_to_neo4j.log")
CHECKPOINT_FILE = Path("./logs/parse_checkpoint.txt")

NEO4J_URI       = "bolt://127.0.0.1:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = "password"

MAX_WORKERS       = 2        # потоки парсинга (уменьшено)
WRITER_COUNT      = 1        # число потоков-писателей (уменьшено до 1)
MAX_WRITE_RETRIES = 3
WRITE_BACKOFF     = 2        # уменьшена задержка
BATCH_SIZE        = 1000     # увеличен размер батча
POOL_SIZE         = 3        # уменьшен размер пула
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
        
        # Удаляем проблемное ограничение на layer и level, если оно существует
        try:
            session.run("DROP CONSTRAINT node_layer_level_unique IF EXISTS")
            logger.info("Removed problematic layer+level constraint")
        except Exception as e:
            logger.info(f"No layer+level constraint to remove: {e}")
        
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
                      n.uid = row.pmid
            """, nodes=nodes)
        if rels:
            tx.run("""
                UNWIND $rels AS r
                  MERGE (source:Article {uid: r.pmid})
                  MERGE (target:Article {uid: r.cpmid})
                  WITH source, target, r
                  WHERE source <> target
                  MERGE (source)-[:CITES]->(target)
            """, rels=rels)

    logger.info(f"[WRITE-ENTRY] {path_name}: nodes={len(nodes)}, rels={len(rels)}")
    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        try:
            with driver.session() as session:
                session.execute_write(tx_work)
            logger.info(f"[WRITE-OK] {path_name}")
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
write_queue = Queue(maxsize=QUEUE_SIZE)

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
    rejection_reasons = {}
    total_rels_found = 0
    
    with gzip.open(path, 'rb') as gf:
        for _, elem in ET.iterparse(gf, events=("end",)):
            if elem.tag == "PubmedArticle":
                total_articles += 1
                data = {
                    'pmid': elem.findtext('.//PMID'),
                    'doi': elem.findtext('.//ArticleIdList/ArticleId[@IdType="doi"]') or None,
                    'title': ''.join(elem.find('.//ArticleTitle').itertext()).strip()
                              if elem.find('.//ArticleTitle') is not None else None,
                    'publication_time': (
                        (elem.findtext('.//Journal/JournalIssue/PubDate/Year')
                         or elem.findtext('.//Journal/JournalIssue/PubDate/MedlineDate') or '').strip()
                    ) or None,
                    'journal': elem.findtext('.//Journal/Title'),
                    'abstract': ''.join(elem.find('.//Abstract/AbstractText').itertext()).strip()
                                if elem.find('.//Abstract/AbstractText') is not None else None,
                    'authors': [
                        " ".join([au.findtext('ForeName') or "", au.findtext('LastName') or ""]).strip()
                        for au in elem.findall('.//AuthorList/Author')
                        if au.findtext('ForeName') or au.findtext('LastName')
                    ],
                    'keywords': [
                        dn.text.strip()
                        for dn in elem.findall('.//MeshHeadingList/MeshHeading/DescriptorName')
                        if dn.text
                    ]
                }
                
                # Проверяем обязательные поля и записываем причины отклонения
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
                    article_rels = 0
                    reference_list = elem.find('.//ReferenceList')
                    if reference_list is not None:
                        for aid in reference_list.findall('.//ArticleId[@IdType="pubmed"]'):
                            txt = aid.text
                            if txt and txt.isdigit():
                                rels.append({'pmid': data['pmid'], 'cpmid': txt})
                                article_rels += 1
                    total_rels_found += article_rels
                    count += 1
                elem.clear()

                if count % BATCH_SIZE == 0:
                    logger.info(f"{path.name}: enqueue batch #{count//BATCH_SIZE}")
                    write_queue.put((path.name, nodes.copy(), rels.copy()))
                    nodes.clear()
                    rels.clear()

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
    
    # Берём только указанный файл
    latest_file = files[-2]
    logger.info(f"Обрабатываем только указанный файл: {latest_file.name}")
    
    # Проверяем дату модификации файла
    mod_time = datetime.datetime.fromtimestamp(latest_file.stat().st_mtime)
    logger.info(f"Дата модификации файла: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Проверяем размер файла
    file_size_mb = latest_file.stat().st_size / (1024 * 1024)
    logger.info(f"Размер файла: {file_size_mb:.1f} MB")
    
    # Если нужно обработать все файлы, раскомментируйте следующие строки:
    # logger.info("Обрабатываем ВСЕ файлы (не только последний)")
    # files_to_process = files
    # else:
    files_to_process = [latest_file]
    
    # Очищаем базу данных перед загрузкой нового файла
    try:
        with driver.session() as s:
            # Удаляем все узлы
            s.run("MATCH (n:Article) DETACH DELETE n")
            
            # Удаляем все ограничения, которые могут вызывать конфликты
            constraints = s.run("SHOW CONSTRAINTS").data()
            for constraint in constraints:
                constraint_name = constraint.get('name')
                if constraint_name and 'layer' in constraint_name.lower():
                    try:
                        s.run(f"DROP CONSTRAINT {constraint_name}")
                        logger.info(f"Удалено ограничение: {constraint_name}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить ограничение {constraint_name}: {e}")
            
        logger.info("База данных очищена")
    except Exception as e:
        logger.error(f"Ошибка при очистке базы: {e}")
        return

    try:
        for file_to_process in files_to_process:
            logger.info(f"Начинаем обработку файла: {file_to_process.name}")
            parse_one_file(file_to_process)
            logger.info(f"[OK] {file_to_process.name} обработан успешно")
    except Exception as e:
        logger.error(f"[PARSE-ERR] {file_to_process.name}: {e}")

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
            
            result = s.run("MATCH ()-[r:CITES]->() RETURN count(r) as total_rels")
            total_rels = result.single()["total_rels"]
            logger.info(f"ИТОГО загружено связей в базу: {total_rels}")
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")

    logger.info("Обработка завершена.")

if __name__ == "__main__":
    start = time.time()
    process_all()
    logger.info(f"Finished in {time.time() - start:.1f}s")
