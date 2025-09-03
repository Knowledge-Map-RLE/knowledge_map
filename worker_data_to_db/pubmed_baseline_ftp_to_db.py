import gzip
import logging
import time
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

MAX_WORKERS       = 4        # потоки парсинга
WRITER_COUNT      = 2        # число потоков-писателей
MAX_WRITE_RETRIES = 3
WRITE_BACKOFF     = 5
BATCH_SIZE        = 500
POOL_SIZE         = 5
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
def ensure_schema():
    with driver.session() as session:
        # Создаём схему для нашего алгоритма укладки
        session.run("""
            CREATE CONSTRAINT IF NOT EXISTS
            FOR (n:Node) REQUIRE n.uid IS UNIQUE
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Node) ON (n.layout_status)
        """)
        session.run("""
            CREATE INDEX IF NOT EXISTS
            FOR (n:Node) ON (n.layer, n.level)
        """)
    logger.info("Schema constraints and indexes ensured")

# ========== ЗАПИСЬ ==========
def write_to_neo4j(path_name: str, nodes: list[dict], rels: list[dict]) -> bool:
    global driver

    def tx_work(tx):
        if nodes:
            tx.run("""
                UNWIND $nodes AS row
                  MERGE (n:Node {uid: row.pmid})
                  SET n = row,
                      n.uid = row.pmid,
                      n.layout_status = 'unprocessed',
                      n.layer = -1,
                      n.level = -1,
                      n.sublevel_id = -1,
                      n.x = 0.0,
                      n.y = 0.0,
                      n.is_pinned = false
            """, nodes=nodes)
        if rels:
            tx.run("""
                UNWIND $rels AS r
                  MERGE (source:Node {uid: r.pmid})
                  MERGE (target:Node {uid: r.cpmid})
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
MANDATORY_FIELDS = ['pmid', 'title', 'publication_time', 'journal']

def parse_one_file(path: Path):
    nodes, rels = [], []
    count = 0
    with gzip.open(path, 'rb') as gf:
        for _, elem in ET.iterparse(gf, events=("end",)):
            if elem.tag == "PubmedArticle":
                data = {
                    'pmid': elem.findtext('.//PMID'),
                    'doi': elem.findtext('.//ArticleIdList/ArticleId[@IdType="doi"]') or None,
                    'title': ''.join(elem.find('.//ArticleTitle').itertext()).strip()
                              if elem.find('.//ArticleTitle') is not None else None,
                    'publication_time': (
                        (elem.findtext('.//Journal/JournalIssue/PubDate/Year')
                         or elem.findtext('.//Journal/JournalIssue/PubDate/MedlineDate') or '').strip()
                    ),
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
                if all(data[f] for f in MANDATORY_FIELDS):
                    nodes.append(data)
                    for aid in elem.findall('.//ReferenceList//ArticleId[@IdType="pubmed"]'):
                        txt = aid.text
                        if txt and txt.isdigit():
                            rels.append({'pmid': data['pmid'], 'cpmid': txt})
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
    
    # Берём только последний файл
    latest_file = files[-1]
    logger.info(f"Обрабатываем только последний файл: {latest_file.name}")
    
    # Очищаем базу данных перед загрузкой нового файла
    try:
        with driver.session() as s:
            s.run("MATCH (n:Node) DETACH DELETE n")
        logger.info("База данных очищена")
    except Exception as e:
        logger.error(f"Ошибка при очистке базы: {e}")
        return

    try:
        parse_one_file(latest_file)
        logger.info(f"[OK] {latest_file.name} обработан успешно")
    except Exception as e:
        logger.error(f"[PARSE-ERR] {latest_file.name}: {e}")

    # ждём пока писатели обработают всё
    write_queue.join()
    for _ in range(WRITER_COUNT):
        write_queue.put(None)

    logger.info("Обработка завершена.")

if __name__ == "__main__":
    start = time.time()
    process_all()
    logger.info(f"Finished in {time.time() - start:.1f}s")
