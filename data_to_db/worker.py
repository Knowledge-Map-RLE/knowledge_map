"""
Worker для загрузки данных из PubMed и PubMed Central в Neo4j и S3.

Основной пайплайн управления загрузкой данных.
Вызывает функции из папок PubMed и PubMed_Central.

Поток:
1. Проверить S3 - статья уже обработана?
2. Получить XML (из архива PMC или локально PubMed)
3. Обработать через xml_to_md (gRPC)
4. Сохранить Markdown + images в S3
5. Сохранить метаданные в Neo4j как Document
"""
import asyncio
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

from neo4j import GraphDatabase

from common import get_driver

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

PMC_MAX_ARCHIVES = int(os.getenv("PMC_MAX_ARCHIVES", "0"))
PMC_MAX_ARTICLES_PER_ARCHIVE = int(os.getenv("PMC_MAX_ARTICLES_PER_ARCHIVE", "0"))

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
    """Базовый класс для загрузки источника данных."""

    def __init__(self, name: str, neo4j_driver, api_url: str):
        self.name = name
        self.driver = neo4j_driver
        self.api_url = api_url
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._thread_started = False

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

    def run(self):
        raise NotImplementedError

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
                    s.last_updated = datetime()
                """,
                name=self.name,
                downloaded=downloaded,
                total=total,
                progress=round(progress, 2),
                status=status,
                current_file=current_file,
            )

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
            logger.warning(f"Failed to notify progress: {e}")


class PubMedCentralRunner(DataSourceRunner):
    """Загрузчик PubMed Central - вызывает функции из папки PubMed_Central."""

    def __init__(self, neo4j_driver, api_url: str):
        super().__init__("PubMed Central", neo4j_driver, api_url)
        self.checkpoint_file = Path("./logs/pmc_s3_checkpoint.txt")
        self._processed_files = set()
        self.temp_dir = Path("/tmp/pmc_data")

        from PubMed_Central import process_all_files
        self._process_all = process_all_files
        
        logger.info(f"[PMC] Runner initialized using PubMed_Central module")

    def run(self):
        logger.info(f"[PMC] Starting with PubMed_Central module")
        self._load_checkpoint()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        while not self.should_stop():
            self.wait_if_paused()
            if self.should_stop():
                break

            try:
                self._process_all()
            except Exception as e:
                logger.error(f"[PMC] Error processing: {e}")
                self.update_progress(0, 0, "error", str(e)[:100])

            if self.should_stop():
                break
            
            logger.info("[PMC] Waiting for next iteration...")
            asyncio.run(asyncio.sleep(300))

        logger.info("[PMC] Downloader stopped")

    def _load_checkpoint(self):
        if self.checkpoint_file.exists():
            self._processed_files = set(
                line.strip() for line in self.checkpoint_file.read_text().splitlines() if line.strip()
            )
            logger.info(f"[PMC] Loaded checkpoint: {len(self._processed_files)} files processed")

    def _save_checkpoint(self, filename: str):
        self._processed_files.add(filename)
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with self.checkpoint_file.open("a", encoding="utf-8") as f:
            f.write(filename + "\n")


class PubMedRunner(DataSourceRunner):
    """Загрузчик PubMed - вызывает функции из папки PubMed."""

    def __init__(self, neo4j_driver, api_url: str):
        super().__init__("PubMed", neo4j_driver, api_url)
        self.checkpoint_file = Path("./logs/pubmed_s3_checkpoint.txt")
        self._processed_files = set()

        from PubMed import process_all_files
        self._process_all = process_all_files
        
        logger.info(f"[PubMed] Runner initialized using PubMed module")

    def run(self):
        logger.info(f"[PubMed] Starting with PubMed module")
        self._load_checkpoint()

        while not self.should_stop():
            self.wait_if_paused()
            if self.should_stop():
                break

            try:
                self._process_all()
            except Exception as e:
                logger.error(f"[PubMed] Error processing: {e}")
                self.update_progress(0, 0, "error", str(e)[:100])

            if self.should_stop():
                break
            
            logger.info("[PubMed] Waiting for next iteration...")
            asyncio.run(asyncio.sleep(60))

        logger.info("[PubMed] Downloader stopped")

    def _load_checkpoint(self):
        if self.checkpoint_file.exists():
            self._processed_files = set(
                line.strip() for line in self.checkpoint_file.read_text().splitlines() if line.strip()
            )
            logger.info(f"[PubMed] Loaded checkpoint: {len(self._processed_files)} files processed")

    def _save_checkpoint(self, filename: str):
        self._processed_files.add(filename)
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with self.checkpoint_file.open("a", encoding="utf-8") as f:
            f.write(filename + "\n")


class DataDownloadWorker:
    """Основной воркер управления загрузкой данных."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=3,
        )
        self.runners: Dict[str, DataSourceRunner] = {}
        self._running = False

    def start(self):
        self._running = True
        logger.info("Data Download Worker started")

        self._initialize_sources()
        self._start_runners()

        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()

        while self._running:
            logger.info("Main loop running")
            threading.Event().wait(5)

    def _initialize_sources(self):
        sources = {
            "PubMed": {"name": "PubMed", "ftp_url": "ftp.ncbi.nlm.nih.gov/pubmed/baseline/"},
            "PubMed Central": {"name": "PubMed Central", "ftp_url": "ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_bulk/oa_comm/xml/"},
        }

        with self.driver.session() as session:
            for config in sources.values():
                session.run("""
                    MERGE (s:DataSource {name: $name})
                    SET s.ftp_url = $ftp_url,
                        s.total_files = 0, s.downloaded_files = 0,
                        s.progress_percent = 0.0, s.status = 'idle',
                        s.current_file = ''
                """, name=config["name"], ftp_url=config["ftp_url"])
        logger.info("Data sources initialized")

    def _start_runners(self):
        pmc_runner = PubMedCentralRunner(self.driver, API_BASE_URL)
        self.runners["PubMed Central"] = pmc_runner
        logger.info("PubMed Central runner created")

        pubmed_runner = PubMedRunner(self.driver, API_BASE_URL)
        self.runners["PubMed"] = pubmed_runner
        logger.info("PubMed runner created")

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_and_apply_commands()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            threading.Event().wait(2)

        logger.info("Data Download Worker stopped")

    def _check_and_apply_commands(self):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:DataSource)
                RETURN s.name as name, s.command as command
            """)
            for record in result:
                name = record["name"]
                command = record["command"]
                if command and command.strip() and name in self.runners:
                    self._apply_command(name, command)
                    session.run("MATCH (s:DataSource {name: $name}) SET s.command = null", name=name)

    def _apply_command(self, name: str, command: str):
        runner = self.runners.get(name)
        if not runner:
            return

        logger.info(f"[MONITOR] Applying command '{command}' to {name}")

        if command == "start":
            runner_thread = threading.Thread(target=runner.run, daemon=True)
            runner_thread.start()
            logger.info(f"Started: {name}")

        elif command == "pause":
            runner.pause()
            with self.driver.session() as session:
                session.run("MATCH (s:DataSource {name: $name}) SET s.status = 'paused'", name=name)
            logger.info(f"Paused: {name}")

        elif command == "stop":
            runner.stop()
            with self.driver.session() as session:
                session.run("MATCH (s:DataSource {name: $name}) SET s.status = 'stopped'", name=name)
            logger.info(f"Stopped: {name}")

        elif command == "reset":
            runner.stop()
            runner._processed_files.clear()
            with self.driver.session() as session:
                session.run("""
                    MATCH (s:DataSource {name: $name})
                    SET s.downloaded_files = 0, s.progress_percent = 0.0,
                        s.status = 'idle', s.current_file = ''
                """, name=name)
            runner._stop_event.clear()
            runner._pause_event.set()
            logger.info(f"Reset: {name}")

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