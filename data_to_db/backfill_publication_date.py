"""
Backfill publication_date для документов PubMed Baseline.

Проблема: импортёр pubmed_baseline_ftp_to_db.py извлекал год публикации
(publication_time), но НЕ записывал его в Neo4j. Поле Document.publication_date
осталось пустым у всех ~9.7M документов, что блокирует временной split в
eval/workability.

Скрипт повторно проходит по уже скачанным baseline XML (data/PubMed/*.xml.gz,
1334 файла): 4 потока парсят файлы, воркер ставит батчи в очередь, writer-поток
пишет их в Neo4j через UNWIND по индексу Document.uid.

Эффективность:
  - Запись по уникальному индексу uid (отсутствующие PMID игнорируются MATCH'ем).
  - Ограниченное окно фьючеров ~= числу воркеров (память ограничена).
  - Парсер направлен: `iterparse`, elem.clear() после каждого PMID.
  - Early-stop: baseline отсортирован по PMID, данные в БД покрывают
    диапазон PMID ≲ 12M; после 5 пустых файлов подряд прогон останавливается.
  - Чекпоинт по файлам — можно прерывать и продолжать.

Запуск из каталога data_to_db (окружение data_to_db/.venv):
  poetry run python backfill_publication_date.py
  poetry run python backfill_publication_date.py --files-limit 3   # смоук-тест
"""
import argparse
import gzip
import re
import sys
import tarfile
import time
import os
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from typing import Iterable, List
from lxml import etree as LET  # type: ignore

sys.path.insert(0, os.path.dirname(__file__))

from common import get_driver, load_checkpoint, append_checkpoint, setup_logging  # noqa: E402

logger = setup_logging(Path("./logs/backfill_publication_date.log"))

# ========== КОНФИГУРАЦИЯ ==========
DATA_DIR_PUBMED = Path("..") / "data" / "PubMed"
DATA_DIR_PMC = Path("..") / "data" / "PubMed_Central"
CHECKPOINT_FILE = Path("./logs/backfill_pubdate_checkpoint.txt")
CHECKPOINT_FILE_PMC = Path("./logs/backfill_pmc_checkpoint.txt")
BATCH_SIZE = 2000
WRITE_RETRIES = 3
PARSE_WORKERS = 4
QUEUE_SIZE = 32
EMPTY_STOP_FILES = 5
PMC_ARCHIVES = 3  # нужные PMC-документы лежат в PMC000-002 архивах (probe)

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_year_from_text(date_text) -> int | None:
    if not date_text:
        return None
    m = YEAR_RE.search(str(date_text))
    if m:
        year = int(m.group())
        if 1900 <= year <= 2030:
            return year
    return None


def parse_file_pairs(path: Path):
    """Потоково извлекает список (pmid, year) из одного PubMed XML.gz файла.

    PMID выступает uid документов в БД (source='pubmed').
    """
    pairs = []
    with gzip.open(path, "rb") as gf:
        context = LET.iterparse(gf, events=("end",), huge_tree=True)
        for _, elem in context:
            if elem.tag == "PubmedArticle":
                pid = elem.findtext(".//PMID")
                if pid and pid.strip():
                    year_text = (
                        elem.findtext(".//Journal/JournalIssue/PubDate/Year")
                        or elem.findtext(".//Journal/JournalIssue/PubDate/MedlineDate")
                        or ""
                    )
                    year = extract_year_from_text(year_text)
                    if year:
                        pairs.append((pid.strip(), year))
                elem.clear()
    return pairs


class Writer:
    """Один поток записывает батчи из очереди в Neo4j (последовательно, без гонок)."""

    def __init__(self, driver):
        self.driver = driver
        self.queue: Queue = Queue(maxsize=QUEUE_SIZE)
        self.total_written = 0
        self.error = None
        self._stop = False
        self._t = Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while not self._stop or not self.queue.empty():
            try:
                batch = self.queue.get(timeout=5)
            except Empty:
                continue
            try:
                self._write(batch)
                self.total_written += len(batch)
            except Exception as e:  # noqa: BLE001
                self.error = e
            finally:
                self.queue.task_done()

    def drain(self):
        """Ждёт, пока все поставленные батчи записаны."""
        self.queue.join()

    def _write(self, batch):
        rows = [{"pmid": pmid, "year": year} for pmid, year in batch]
        for attempt in range(1, WRITE_RETRIES + 1):
            try:
                with self.driver.session() as session:
                    session.run(
                        """
                        UNWIND $rows AS row
                          MATCH (d:Document {uid: row.pmid})
                          SET d.publication_date = datetime({year: row.year, month: 1, day: 1})
                        """,
                        rows=rows,
                    )
                return
            except Exception as e:  # noqa: BLE001
                if attempt == WRITE_RETRIES:
                    raise
                logger.warning("Retry %d/%d (batch=%d): %s", attempt, WRITE_RETRIES, len(batch), e)
                time.sleep(attempt * 2)

    def stop(self):
        self._stop = True
        self._t.join(timeout=120)


def backfill_pubmed(files_limit: int | None = None, no_early_stop: bool = False):
    driver = get_driver(pool_size=2)
    writer = Writer(driver)
    done = load_checkpoint(CHECKPOINT_FILE)

    files = sorted(DATA_DIR_PUBMED.rglob("*.xml.gz"))
    if files_limit:
        files = files[:files_limit]
    to_process = [p for p in files if p.name not in done]
    logger.info(f"Файлов: {len(files)}, пропущено (чекпоинт): {len(files)-len(to_process)}")

    total_pairs = 0
    empty_streak = 0
    t0 = time.monotonic()
    done_names = set(done)

    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
        it = iter(to_process)
        pending: dict = {}
        for _ in range(min(PARSE_WORKERS, len(to_process))):
            path = next(it)
            pending[pool.submit(parse_file_pairs, path)] = path.name

        processed = 0
        while pending:
            futs_done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for fut in futs_done:
                name = pending.pop(fut)
                pairs = fut.result()
                done_names.add(name)
                processed += 1

                if pairs:
                    for i in range(0, len(pairs), BATCH_SIZE):
                        writer.queue.put(pairs[i:i + BATCH_SIZE])
                    total_pairs += len(pairs)
                    empty_streak = 0
                else:
                    empty_streak += 1

                # Целостность: чекпоинт только после фактической записи батчей файла.
                writer.drain()
                if writer.error is not None:
                    raise writer.error
                append_checkpoint(CHECKPOINT_FILE, name)
                if processed % 20 == 0 or empty_streak >= EMPTY_STOP_FILES or not pending:
                    logger.info(
                        f"[{processed}/{len(to_process)}] {name}: +{len(pairs)} пар, "
                        f"итого {total_pairs}, {time.monotonic()-t0:.0f}s, "
                        f"записано в БД {writer.total_written}"
                    )

                # Ранняя остановка: файлы отсортированы по PMID; данные в БД
                # покрывают диапазон PMID ≲ 12M, дальше все файлы пусты.
                # Полный прогон (--no-early-stop) никогда не останавливается.
                if empty_streak >= EMPTY_STOP_FILES and not no_early_stop:
                    logger.info(f"Ранняя остановка: {EMPTY_STOP_FILES} пустых файлов подряд")
                    writer.stop()
                    logger.info(
                        f"BACKFILL: пар={total_pairs}, записано в БД={writer.total_written}"
                    )
                    driver.close()
                    return

            # Держим окно загруженным.
            for _ in range(len(futs_done)):
                try:
                    path = next(it)
                except StopIteration:
                    break
                pending[pool.submit(parse_file_pairs, path)] = path.name

    writer.stop()
    logger.info(f"BACKFILL ЗАВЕРШЁН: пар={total_pairs}, записано в БД={writer.total_written}")
    driver.close()


def pmc_uid_from_name(name: str) -> str:
    """Извлекает PMC uid из имени файла/папки: 'PMC10005275.1' -> 'PMC10005275'."""
    while name.endswith(".xml") or name.endswith(".gz") or name.endswith(".tar"):
        name = name[:-4]
    m = re.match(r"(PMC\d+)", name)
    return m.group(1) if m else name


def parse_pmc_bytes(data: bytes, name: str) -> List[tuple[str, int]]:
    """Извлекает uid и год публикации из PMC XML (bytes). name — для чекпоинта."""
    pairs: List[tuple[str, int]] = []
    try:
        root = LET.fromstring(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("PMC parse error %s: %s", name, e)
        return pairs

    uid = pmc_uid_from_name(name)
    year: int | None = None
    for pd in root.iter("{http://www.ncbi.nlm.nih.gov/JATS1}pub-date"):
        for y in pd.iter():
            if isinstance(y.tag, str) and y.tag.endswith("}year"):
                year = extract_year_from_text(y.text)
                break
        if year:
            break
    if not year:
        for pd in root.iter("pub-date"):
            for y in pd.iter():
                if isinstance(y.tag, str) and y.tag.split("}")[-1] == "year":
                    year = extract_year_from_text(y.text)
                    break
            if year:
                break
    if year:
        pairs.append((uid, year))
    return pairs


def iter_pmc_sources(only_ids: set[str] | None = None) -> Iterable[tuple[str, bytes]]:
    """Все PMC XML-источники: распакованные папки + нужные файлы из tar.gz.

    Возвращает (имя для чекпоинта, содержимое XML). only_ids — ускорить
    чтение архивов: брать только файлы, чей PMC uid есть в наборе.
    """
    for p in sorted(DATA_DIR_PMC.glob("PMC*.xml")):
        yield p.name, p.read_bytes()
    for sub in sorted(DATA_DIR_PMC.glob("PMC*")):
        if sub.is_dir():
            for p in sorted(sub.glob("*.xml")):
                yield p.name, p.read_bytes()
    for tf in sorted(DATA_DIR_PMC.glob("*.tar.gz"))[:PMC_ARCHIVES]:
        with tarfile.open(tf, "r:gz") as tar:
            for m in tar.getmembers():
                if not (m.isfile() and m.name.endswith(".xml") and "PMC" in m.name):
                    continue
                if only_ids is not None:
                    want = pmc_uid_from_name(Path(m.name).name)
                    if want not in only_ids:
                        continue
                f = tar.extractfile(m)
                if f is not None:
                    yield Path(m.name).name, f.read()


def load_pmc_uids() -> set[str]:
    """Все Document.uid со source='pmc' — для фильтрации архивов."""
    with get_driver(pool_size=1).session() as s:
        return {str(r[0]) for r in s.run(
            "MATCH (d:Document) WHERE d.source='pmc' RETURN d.uid").values()}


def backfill_pmc(files_limit: int | None = None):
    """Бэкфилл publication_date для PMC-документов.

    Отличается от PubMed: PMC в БД имеют зависимость вида
    d.uid == pmc_id из XML (например 'PMC176545'), а источники лежат в
    папках PMC*/PMC*.xml и внутри tar.gz-архивов. Записываем по индексу uid.
    """
    driver = get_driver(pool_size=2)
    writer = Writer(driver)
    done = load_checkpoint(CHECKPOINT_FILE_PMC)

    pmc_uids = load_pmc_uids()
    logger.info(f"PMC-документов в БД: {len(pmc_uids)}")

    sources = list(iter_pmc_sources(only_ids=pmc_uids))
    if files_limit:
        sources = sources[:files_limit]
    to_process = [src for src in sources if src[0] not in done]
    logger.info(f"PMC-файлов: {len(sources)}, пропущено (чекпоинт): {len(sources) - len(to_process)}")

    total_pairs = 0
    t0 = time.monotonic()
    done_names = set(done)

    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
        it = iter(to_process)
        pending: dict = {}
        for _ in range(min(PARSE_WORKERS, len(to_process))):
            name, data = next(it)
            pending[pool.submit(parse_pmc_bytes, data, name)] = name

        processed = 0
        while pending:
            futs_done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            for fut in futs_done:
                name = pending.pop(fut)
                pairs = fut.result()
                done_names.add(name)
                processed += 1

                if pairs:
                    for i in range(0, len(pairs), BATCH_SIZE):
                        writer.queue.put(pairs[i:i + BATCH_SIZE])
                    total_pairs += len(pairs)

                writer.drain()
                if writer.error is not None:
                    raise writer.error
                append_checkpoint(CHECKPOINT_FILE_PMC, name)
                if processed % 200 == 0:
                    logger.info(
                        f"[{processed}/{len(to_process)}] {name}: +{len(pairs)} пар, "
                        f"итого {total_pairs}, {time.monotonic()-t0:.0f}s, "
                        f"записано в БД {writer.total_written}"
                    )

            for _ in range(len(futs_done)):
                try:
                    name, data = next(it)
                except StopIteration:
                    break
                pending[pool.submit(parse_pmc_bytes, data, name)] = name

    writer.stop()
    logger.info(f"PMC BACKFILL ЗАВЕРШЁН: пар={total_pairs}, записано в БД={writer.total_written}")
    driver.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill publication_date из PubMed baseline XML")
    parser.add_argument("--pmc", action="store_true", help="бэкфилл publication_date для PMC-документов")
    parser.add_argument("--files-limit", type=int, default=None, help="обработать только N файлов")
    parser.add_argument(
        "--no-early-stop", action="store_true",
        help="прогнать все файлы без ранней остановки по пустым",
    )
    args = parser.parse_args()
    if args.pmc:
        backfill_pmc(files_limit=args.files_limit)
    else:
        backfill_pubmed(files_limit=args.files_limit, no_early_stop=args.no_early_stop)


if __name__ == "__main__":
    main()