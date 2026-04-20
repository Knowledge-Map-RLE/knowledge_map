"""
Layer: Application — Service
Package: services.data_download
Responsibility: Сервис управления загрузкой данных из внешних источников.
               Работает с Neo4j для хранения статусов и прогресса загрузки.
"""
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

DATA_SOURCES = {
    "PubMed": "PubMed",
    "PubMed Central": "PubMed Central",
}

DATA_SOURCES_CONFIG = {
    "PubMed": {
        "name": "PubMed",
        "ftp_url": "ftp.ncbi.nlm.nih.gov/pubmed/baseline/",
        "description": "База данных медицинских публикаций NCBI",
    },
    "PubMed Central": {
        "name": "PubMed Central",
        "ftp_url": "ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_bulk/oa_comm/xml/",
        "description": "Полнотекстовый архив медицинских публикаций NCBI",
    },
}


class DataDownloadService:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=5,
        )

    def close(self):
        self.driver.close()

    def _run_query(self, query: str, **params):
        with self.driver.session() as session:
            return session.run(query, **params)

    def initialize_sources(self):
        """Инициализирует узлы источников данных в Neo4j."""
        for source_key, config in DATA_SOURCES_CONFIG.items():
            self._run_query(
                """
                MERGE (s:DataSource {name: $name})
                SET s.ftp_url = $ftp_url,
                    s.description = $description,
                    s.total_files = 0,
                    s.downloaded_files = 0,
                    s.progress_percent = 0.0,
                    s.status = 'idle',
                    s.command = '',
                    s.error_message = null,
                    s.last_updated = datetime()
                """,
                name=config["name"],
                ftp_url=config["ftp_url"],
                description=config["description"],
            )
        logger.info("Data sources initialized in Neo4j")

    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Возвращает все источники данных с их статусами."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:DataSource)
                RETURN s.name as name,
                       s.ftp_url as ftp_url,
                       s.description as description,
                       s.total_files as total_files,
                       s.downloaded_files as downloaded_files,
                       s.progress_percent as progress_percent,
                       s.status as status,
                       s.error_message as error_message,
                       s.last_updated as last_updated
                ORDER BY s.name
            """)
            return [dict(record) for record in result]

    def get_source_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Возвращает статус конкретного источника."""
        result = self._run_query(
            """
            MATCH (s:DataSource {name: $name})
            RETURN s.name as name,
                   s.ftp_url as ftp_url,
                   s.total_files as total_files,
                   s.downloaded_files as downloaded_files,
                   s.progress_percent as progress_percent,
                   s.status as status,
                   s.error_message as error_message,
                   s.last_updated as last_updated
            """,
            name=name,
        )
        record = result.single()
        if record:
            result.consume()
            return dict(record)
        return None

    def update_progress(
        self,
        name: str,
        downloaded_files: int,
        total_files: int,
        status: str,
        error_message: Optional[str] = None,
    ):
        """Обновляет прогресс загрузки."""
        progress = (downloaded_files / total_files * 100) if total_files > 0 else 0
        self._run_query(
            """
            MATCH (s:DataSource {name: $name})
            SET s.downloaded_files = $downloaded,
                s.total_files = $total,
                s.progress_percent = $progress,
                s.status = $status,
                s.current_file = $current_file,
                s.error_message = $error_message,
                s.last_updated = datetime()
            """,
            name=name,
            downloaded=downloaded_files,
            total=total_files,
            progress=round(progress, 2),
            status=status,
            current_file=error_message or "",
            error_message=error_message,
        )
        logger.info(f"Updated {name}: {downloaded_files}/{total_files} ({progress:.1f}%) - {error_message}")

    def set_status(self, name: str, status: str, error_message: Optional[str] = None):
        """Устанавливает статус источника."""
        self._run_query(
            """
            MATCH (s:DataSource {name: $name})
            SET s.status = $status,
                s.error_message = $error_message,
                s.last_updated = datetime()
            """,
            name=name,
            status=status,
            error_message=error_message,
        )
        logger.info(f"Set {name} status to: {status}")

    def start_download(self, name: str):
        """Запускает загрузку для источника."""
        self.set_status(name, "starting")
        logger.info(f"Start download requested for: {name}")

    def pause_download(self, name: str):
        """Приостанавливает загрузку для источника."""
        self.set_status(name, "paused")
        logger.info(f"Pause download requested for: {name}")

    def reset_download(self, name: str):
        """Сбрасывает прогресс загрузки."""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (s:DataSource {name: $name})
                SET s.downloaded_files = 0,
                    s.progress_percent = 0.0,
                    s.status = 'idle',
                    s.current_file = '',
                    s.error_message = null,
                    s.last_updated = datetime()
                """,
                name=name,
            )
        # Force commit
        with self.driver.session() as session:
            session.run("RETURN 1")
        logger.info(f"Reset download for: {name}")

    def set_command(self, name: str, command: str):
        """Устанавливает команду для выполнения воркером."""
        self._run_query(
            """
            MATCH (s:DataSource {name: $name})
            SET s.command = $command,
                s.last_updated = datetime()
            """,
            name=name,
            command=command,
        )
        logger.info(f"Set command '{command}' for: {name}")


_service_instance: Optional[DataDownloadService] = None


def get_data_download_service() -> DataDownloadService:
    global _service_instance
    if _service_instance is None:
        _service_instance = DataDownloadService()
    return _service_instance