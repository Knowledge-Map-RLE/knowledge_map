"""Общие утилиты для воркеров worker_data_to_db."""
import logging
import os
from pathlib import Path

from neo4j import GraphDatabase

from _logfmt import LogfmtStreamHandler, logfmt_handler

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://127.0.0.1:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def get_driver(pool_size: int = 2):
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
        max_connection_pool_size=pool_size,
        connection_acquisition_timeout=30,
    )


def load_checkpoint(checkpoint_file: Path) -> set[str]:
    if not checkpoint_file.exists():
        # Fallback: try backup file
        bak = checkpoint_file.with_suffix(".bak.txt")
        if bak.exists():
            checkpoint_file = bak
        else:
            return set()
    return set(line.strip() for line in checkpoint_file.read_text().splitlines() if line.strip())


def append_checkpoint(checkpoint_file: Path, fname: str) -> None:
    # Дедупликация: не дописываем если имя уже есть в файле
    existing = load_checkpoint(checkpoint_file)
    if fname in existing:
        return
    with checkpoint_file.open("a", encoding="utf-8") as f:
        f.write(fname + "\n")


def setup_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    has_logfmt = any(
        isinstance(handler, LogfmtStreamHandler) for handler in root.handlers
    )
    if not has_logfmt:
        root.addHandler(logfmt_handler(service_name="data_to_db"))

    has_file = any(
        isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", "") == str(log_file)
        for handler in root.handlers
    )
    if not has_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
        root.addHandler(file_handler)

    return logging.getLogger(__name__)
