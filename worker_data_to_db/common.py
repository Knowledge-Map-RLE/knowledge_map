"""Общие утилиты для воркеров worker_data_to_db."""
import logging
import os
from pathlib import Path

from neo4j import GraphDatabase

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
        return set()
    return set(line.strip() for line in checkpoint_file.read_text().splitlines() if line.strip())


def append_checkpoint(checkpoint_file: Path, fname: str) -> None:
    with checkpoint_file.open("a", encoding="utf-8") as f:
        f.write(fname + "\n")


def setup_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)
