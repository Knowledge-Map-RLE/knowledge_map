"""
PubMed Central data loader module.

Функции для загрузки данных из PubMed Central в Neo4j + S3.
Вызываются из worker.py.
"""

from .pmc_oa_bulk_to_db import (
    process_all as process_all_files,
    process_all_local_articles,
    parse_one_file_optimized,
    get_driver,
    ensure_schema,
)

__all__ = [
    "process_all_files",
    "process_all_local_articles",
    "parse_one_file_optimized",
    "get_driver",
    "ensure_schema",
]