"""
Worker для загрузки данных из PubMed и PubMed Central в Neo4j и S3.

Основной пайплайн управления загрузкой данных:
1. Скачивание сырых данных (архивы/статьи) с докачкой и проверкой целостности.
2. Обработка XML в Neo4j (parse -> markdown -> Document nodes).

Источники:
- PubMed Baseline:  https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/
- PubMed Update:    https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/
- PubMed Central:   s3://pmc-oa-opendata (инвентаризация CSV)
"""
import logging
import os
import platform
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, List, Tuple

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

DATA_ROOT = Path("..") / "data"

STATUS_REFRESH_INTERVAL = 60  # секунд между обновлением статуса idle-источников
STATUS_CACHE_TTL = 120        # секунд кэш get_status для idle-источников
PROGRESS_NOTIFY_INTERVAL = 3  # секунд минимальный интервал уведомлений о прогрессе
MONITOR_TICK = 2              # секунд между проверками команд монитором
CONNECTION_TIMEOUT = 10       # секунд таймаут подключения к Neo4j

# Эксклюзивный lease воркера: позволяет работать только одному экземпляру.
LEASE_ID = "data_download_worker"
LEASE_TTL = 30                # секунд, после которых lease считается свободным
LEASE_RENEW_INTERVAL = 10     # как часто воркер продлевает lease (должно быть < LEASE_TTL)
WATCHDOG_TIMEOUT = 30         # секунд без тика monitor-loop -> аварийный выход

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/worker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class DataSourceRunner:
    """Базовый класс runner'а источника данных."""

    def __init__(self, name: str, neo4j_driver, api_url: str):
        self.name = name
        self.driver = neo4j_driver
        self.api_url = api_url
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._status_cache: Optional[Tuple[float, int, int]] = None

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def wait_if_paused(self):
        self._pause_event.wait()

    def update_progress(self, downloaded: int, total: int, status: str, current_file: str = ""):
        """Обновляет прогресс в Neo4j."""
        progress = (downloaded / total * 100) if total > 0 else 0
        logger.info(f"[{self.name}] Progress: {downloaded}/{total} ({progress:.1f}%) - {current_file}")

        with self.driver.session() as session:
            session.run(
                """
                MATCH (s:DataSource {name: $name})
                SET s.downloaded_files = $downloaded,
                    s.total_files = $total,
                    s.progress_percent = $progress,
                    s.status = $status,
                    s.current_file = $current_file,
                    s.error_message = null,
                    s.last_updated = datetime()
                """,
                name=self.name,
                downloaded=downloaded,
                total=total,
                progress=round(progress, 2),
                status=status,
                current_file=current_file,
            )

    def update_process_progress(self, processed: int, total: int, current_file: str = ""):
        """Обновляет прогресс обработки XML в Neo4j (отдельные поля)."""
        progress = (processed / total * 100) if total > 0 else 0
        logger.info(f"[{self.name}] Processing: {processed}/{total} ({progress:.1f}%) - {current_file}")

        with self.driver.session() as session:
            session.run(
                """
                MATCH (s:DataSource {name: $name})
                SET s.processed_files = $processed,
                    s.processing_total = $total,
                    s.processing_percent = $progress,
                    s.processing_current_file = $current_file,
                    s.status = 'processing',
                    s.error_message = null,
                    s.last_updated = datetime()
                """,
                name=self.name,
                processed=processed,
                total=total,
                progress=round(progress, 2),
                current_file=current_file,
            )

    def set_status(self, status: str, current_file: str = ""):
        """Устанавливает только статус источника (без изменения счётчиков)."""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (s:DataSource {name: $name})
                SET s.status = $status,
                    s.current_file = $current_file,
                    s.last_updated = datetime()
                """,
                name=self.name,
                status=status,
                current_file=current_file,
            )
        logger.info(f"[{self.name}] Status: {status}")

    def _notify_progress(self, downloaded: int, total: int, percent: float, status: str, current_file: str = ""):
        """Отправляет уведомление через HTTP API."""
        try:
            import requests
            requests.post(
                f"{self.api_url}/api/data_download/progress",
                json={
                    "source": self.name,
                    "downloaded": downloaded,
                    "total": total,
                    "percent": percent,
                    "status": status,
                    "current_file": current_file,
                },
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to notify progress: {e}")

    def _notify_process_progress(self, processed: int, total: int, current_file: str = ""):
        """Отправляет прогресс обработки через HTTP API."""
        percent = (processed / total * 100) if total > 0 else 0
        try:
            import requests
            requests.post(
                f"{self.api_url}/api/data_download/progress",
                json={
                    "source": self.name,
                    "status": "processing",
                    "processed_files": processed,
                    "processing_total": total,
                    "processing_percent": percent,
                    "processing_current_file": current_file,
                },
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to notify processing progress: {e}")


class SourceDownloadRunner(DataSourceRunner):
    """Runner: скачивание сырых данных + обработка в Neo4j для одного источника."""

    def __init__(
        self,
        name: str,
        downloader,
        process_callable: Callable[[Callable[[int, int, str], None]], None],
        neo4j_driver,
        api_url: str,
        poll_interval: int = 300,
    ):
        super().__init__(name, neo4j_driver, api_url)
        self.downloader = downloader
        self._process_all = process_callable
        self.poll_interval = poll_interval
        self._last_progress_notify = 0.0
        self._last_process_notify = 0.0
        self._thread: Optional[threading.Thread] = None

    def _on_progress(self, downloaded: int, total: int, current_file: str):
        """Обновляет прогресс, троттлинг уведомлений (не чаще 1 раза в N секунд)."""
        now = time.time()
        self._status_cache = (now, downloaded, total)
        if downloaded < total and now - self._last_progress_notify < PROGRESS_NOTIFY_INTERVAL:
            return
        self._last_progress_notify = now
        self.update_progress(downloaded, total, "downloading", current_file)
        percent = (downloaded / total * 100) if total > 0 else 0
        self._notify_progress(downloaded, total, percent, "downloading", current_file)

    def _on_process_progress(self, processed: int, total: int, current_file: str):
        """Обновляет прогресс обработки XML, троттлинг уведомлений."""
        now = time.time()
        if processed < total and now - self._last_process_notify < PROGRESS_NOTIFY_INTERVAL:
            return
        self._last_process_notify = now
        self.update_process_progress(processed, total, current_file)
        self._notify_process_progress(processed, total, current_file)

    def refresh_status(self):
        """Показывает текущее состояние (уже скачанное) без запуска загрузки."""
        now = time.time()
        if self._status_cache and now - self._status_cache[0] < STATUS_CACHE_TTL:
            done, total = self._status_cache[1], self._status_cache[2]
        else:
            try:
                done, total = self.downloader.get_status()
                self._status_cache = (now, done, total)
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to refresh status: {e}")
                return
        self.update_progress(done, total, "idle", "")
        percent = (done / total * 100) if total > 0 else 0
        self._notify_progress(done, total, percent, "idle", "")

    def run(self):
        logger.info(f"[{self.name}] Runner started")

        while not self.should_stop():
            self.wait_if_paused()
            if self.should_stop():
                break

            try:
                self.set_status("downloading", "Скачивание данных...")
                self.downloader.download_all(
                    on_progress=self._on_progress,
                    should_stop=self.should_stop,
                    wait_if_paused=self.wait_if_paused,
                )
                if self.should_stop():
                    logger.info(f"[{self.name}] Stopped during download, skipping processing")
                    break
                self.set_status("processing", "Обработка XML...")
                self._process_all(self._on_process_progress)
                self.set_status("completed")
            except Exception as e:
                logger.error(f"[{self.name}] Error: {e}")
                self.update_progress(0, 0, "error", str(e)[:200])

            if self.should_stop():
                break

            logger.info(f"[{self.name}] Waiting for next iteration ({self.poll_interval}s)...")
            for _ in range(self.poll_interval):
                if self.should_stop():
                    break
                time.sleep(1)

        logger.info(f"[{self.name}] Downloader stopped")


class DataDownloadWorker:
    """Основной воркер управления загрузкой данных."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=3,
            connection_timeout=CONNECTION_TIMEOUT,
        )
        self.runners: Dict[str, DataSourceRunner] = {}
        self._running = False
        self._monitor_heartbeat = 0.0
        self._refresh_thread: Optional[threading.Thread] = None

    def _try_acquire_lease(self) -> bool:
        """Пытается захватить эксклюзивный lease воркера (single-instance)."""
        now = time.time()
        try:
            with self.driver.session() as session:
                row = session.run(
                    "MATCH (w:Worker {id: $id}) RETURN w.heartbeat AS heartbeat",
                    id=LEASE_ID,
                ).single()
                if row and row["heartbeat"] is not None:
                    last = row["heartbeat"]
                    if now - last < LEASE_TTL:
                        logger.error(
                            f"Lease воркера уже занят (heartbeat {now - last:.0f}с назад). "
                            "Возможно, запущен другой экземпляр worker.py. "
                            f"Завершите его или подождите {LEASE_TTL}с."
                        )
                        return False
                session.run(
                    """
                    MERGE (w:Worker {id: $id})
                    SET w.heartbeat = $hb, w.host = $host, w.pid = $pid,
                        w.last_updated = datetime()
                    """,
                    id=LEASE_ID,
                    hb=now,
                    host=platform.node(),
                    pid=os.getpid(),
                )
                logger.info("Lease воркера захвачен (single-instance)")
                return True
        except Exception as e:
            logger.error(f"Не удалось захватить lease воркера: {e}")
            return False

    def _renew_lease(self):
        """Продлевает lease, пока воркер жив."""
        try:
            with self.driver.session() as session:
                session.run(
                    "MATCH (w:Worker {id: $id}) SET w.heartbeat = $hb, w.last_updated = datetime()",
                    id=LEASE_ID,
                    hb=time.time(),
                )
        except Exception as e:
            logger.warning(f"Не удалось продлить lease воркера: {e}")

    def _release_lease(self):
        """Освобождает lease при чистом завершении воркера."""
        try:
            with self.driver.session() as session:
                session.run("MATCH (w:Worker {id: $id}) DELETE w", id=LEASE_ID)
            logger.info("Lease воркера освобождён")
        except Exception as e:
            logger.warning(f"Не удалось освободить lease воркера: {e}")

    def _read_pending_commands(self) -> List[Tuple[str, str]]:
        """Читает команды, оставленные с предыдущей сессии воркера."""
        try:
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (s:DataSource) RETURN s.name as name, s.command as command"
                )
                return [
                    (record["name"], record["command"])
                    for record in result
                    if record["command"] and record["command"].strip()
                ]
        except Exception as e:
            logger.warning(f"Не удалось прочитать отложенные команды: {e}")
            return []

    def start(self):
        self._running = True
        logger.info("Data Download Worker started")

        if not self._try_acquire_lease():
            self._running = False
            return

        try:
            # Команды читаем ДО _initialize_sources, т.к. та сбрасывает s.command.
            pending_commands = self._read_pending_commands()
            self._initialize_sources()
            self._start_runners()
            # Применяем отложенные команды, чтобы работа продолжилась после рестарта.
            for name, command in pending_commands:
                if name in self.runners:
                    self._apply_command(name, command)
        except Exception as e:
            logger.error(f"Ошибка инициализации воркера: {e}")
            self._release_lease()
            self._running = False
            return

        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        watchdog_thread.start()
        self._refresh_thread = threading.Thread(target=self._status_refresh_loop, daemon=True)
        self._refresh_thread.start()

        try:
            while self._running:
                threading.Event().wait(5)
        finally:
            self._release_lease()

    def _initialize_sources(self):
        sources = {
            "PubMed Baseline": {
                "name": "PubMed Baseline",
                "ftp_url": "ftp.ncbi.nlm.nih.gov/pubmed/baseline/",
                "source_type": "ftp",
            },
            "PubMed Update": {
                "name": "PubMed Update",
                "ftp_url": "ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/",
                "source_type": "ftp",
            },
            "PubMed Central": {
                "name": "PubMed Central",
                "ftp_url": "s3://pmc-oa-opendata",
                "source_type": "s3",
            },
        }

        with self.driver.session() as session:
            for config in sources.values():
                session.run("""
                    MERGE (s:DataSource {name: $name})
                    SET s.ftp_url = $ftp_url,
                        s.source_type = $source_type,
                        s.total_files = 0, s.downloaded_files = 0,
                        s.progress_percent = 0.0, s.status = 'idle',
                        s.current_file = '', s.command = null,
                        s.error_message = null,
                        s.processed_files = 0, s.processing_total = 0,
                        s.processing_percent = 0.0, s.processing_current_file = null
                """, name=config["name"], ftp_url=config["ftp_url"], source_type=config["source_type"])
            # Удаляем устаревшие источники, которых больше нет в конфигурации
            session.run(
                """
                MATCH (s:DataSource)
                WHERE NOT s.name IN $names
                DETACH DELETE s
                """,
                names=list(sources.keys()),
            )
        logger.info("Data sources initialized")

    def _start_runners(self):
        from PubMed.pubmed_ftp_downloader import PubMedDownloader
        from PubMed_Central.pmc_oa_opendata_downloader import PmcOaOpendataDownloader
        from PubMed.pubmed_baseline_ftp_to_db import process_all_files as pubmed_process
        from PubMed_Central.pmc_oa_bulk_to_db import process_all_local_articles

        baseline_dir = DATA_ROOT / "PubMed"
        update_dir = DATA_ROOT / "PubMed"

        baseline_downloader = PubMedDownloader("PubMed Baseline", "/pubmed/baseline/", baseline_dir)
        update_downloader = PubMedDownloader("PubMed Update", "/pubmed/updatefiles/", update_dir)
        pmc_downloader = PmcOaOpendataDownloader()

        self.runners["PubMed Baseline"] = SourceDownloadRunner(
            name="PubMed Baseline",
            downloader=baseline_downloader,
            process_callable=lambda on_progress: pubmed_process(data_dir=baseline_dir, on_progress=on_progress),
            neo4j_driver=self.driver,
            api_url=API_BASE_URL,
        )
        self.runners["PubMed Update"] = SourceDownloadRunner(
            name="PubMed Update",
            downloader=update_downloader,
            process_callable=lambda on_progress: pubmed_process(data_dir=update_dir, on_progress=on_progress),
            neo4j_driver=self.driver,
            api_url=API_BASE_URL,
        )
        self.runners["PubMed Central"] = SourceDownloadRunner(
            name="PubMed Central",
            downloader=pmc_downloader,
            process_callable=lambda on_progress: process_all_local_articles(on_progress=on_progress),
            neo4j_driver=self.driver,
            api_url=API_BASE_URL,
        )
        logger.info("All runners created")

    def _monitor_loop(self):
        """Monitor-loop: только быстрые операции с Neo4j (команды, lease).

        Обновление статуса источников вынесено в отдельный поток
        (_status_refresh_loop), т.к. get_status() может долго читать диск —
        блокировка здесь срывала бы heartbeat и вызывала watchdog.
        """
        last_lease = 0.0
        while self._running:
            self._monitor_heartbeat = time.time()
            try:
                self._check_and_apply_commands()
                now = time.time()
                if now - last_lease >= LEASE_RENEW_INTERVAL:
                    self._renew_lease()
                    last_lease = now
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            threading.Event().wait(MONITOR_TICK)

        logger.info("Data Download Worker stopped")

    def _status_refresh_loop(self):
        """Фоновое обновление статуса idle-источников.

        Может блокироваться на get_status() (первичный MD5-скан), поэтому
        выполняется вне monitor-loop и не влияет на heartbeat/watchdog.
        """
        while self._running:
            try:
                self._refresh_idle_sources()
            except Exception as e:
                logger.error(f"Error in status refresh loop: {e}")
            threading.Event().wait(STATUS_REFRESH_INTERVAL)

    def _watchdog_loop(self):
        """Сторожевой таймер: если monitor-loop завис, аварийно завершаем процесс."""
        while self._running:
            threading.Event().wait(WATCHDOG_TIMEOUT)
            if not self._running:
                break
            age = time.time() - self._monitor_heartbeat
            if age > WATCHDOG_TIMEOUT:
                logger.error(
                    f"Monitor-loop не отвечает {age:.0f}с — принудительный выход. "
                    "Проверьте доступность Neo4j и перезапустите воркер."
                )
                os._exit(1)

    def _refresh_idle_sources(self):
        for name, runner in self.runners.items():
            status = self._get_source_status(name)
            if status != "downloading" and status != "processing":
                runner.refresh_status()

    def _get_source_status(self, name: str) -> str:
        with self.driver.session() as session:
            result = session.run(
                "MATCH (s:DataSource {name: $name}) RETURN s.status as status",
                name=name,
            )
            record = result.single()
            return record["status"] if record else "idle"

    def _check_and_apply_commands(self):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:DataSource)
                RETURN s.name as name, s.command as command
            """)
            commands = [(record["name"], record["command"]) for record in result]

        for name, command in commands:
            if not (command and command.strip()):
                continue
            if name not in self.runners:
                continue
            self._apply_command(name, command)
            with self.driver.session() as session:
                session.run(
                    "MATCH (s:DataSource {name: $name}) SET s.command = null",
                    name=name,
                )

    def _apply_command(self, name: str, command: str):
        runner = self.runners.get(name)
        if not runner:
            return

        logger.info(f"[MONITOR] Applying command '{command}' to {name}")

        if command == "start":
            if runner._thread is not None and runner._thread.is_alive():
                logger.info(f"[{name}] Already running, skipping start")
                return
            runner._stop_event.clear()
            runner._pause_event.set()
            # Новый цикл запуска: сбрасываем прогресс обработки прошлого запуска.
            with self.driver.session() as session:
                session.run("""
                    MATCH (s:DataSource {name: $name})
                    SET s.processed_files = 0, s.processing_total = 0,
                        s.processing_percent = 0.0, s.processing_current_file = null
                """, name=name)
            runner._thread = threading.Thread(target=runner.run, daemon=True)
            runner._thread.start()
            logger.info(f"Started: {name}")

        elif command == "pause":
            runner.pause()
            self._set_source_status(name, "paused")
            logger.info(f"Paused: {name}")

        elif command == "stop":
            runner.stop()
            self._set_source_status(name, "stopped")
            logger.info(f"Stopped: {name}")

        elif command == "reset":
            runner.stop()
            with self.driver.session() as session:
                session.run("""
                    MATCH (s:DataSource {name: $name})
                    SET s.downloaded_files = 0, s.progress_percent = 0.0,
                        s.status = 'idle', s.current_file = '', s.command = null,
                        s.processed_files = 0, s.processing_total = 0,
                        s.processing_percent = 0.0, s.processing_current_file = null
                """, name=name)
            runner._stop_event.clear()
            runner._pause_event.set()
            logger.info(f"Reset: {name}")

    def _set_source_status(self, name: str, status: str):
        with self.driver.session() as session:
            session.run(
                "MATCH (s:DataSource {name: $name}) SET s.status = $status",
                name=name,
                status=status,
            )

    def stop(self):
        self._running = False
        for runner in self.runners.values():
            runner.stop()
        self.driver.close()


def signal_handler(signum, frame):
    logger.info("Received signal, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("Starting Data Download Worker...")
    worker = DataDownloadWorker()
    worker.start()
