"""
Backfill: привязка автора (created_by_uid) к статьям и их контенту.

Проставляет created_by_uid на всех нодах Document / KnowledgeStatement /
ArticleBlock, где он отсутствует (или пуст). Идемпотентен: повторный запуск
не изменяет уже привязанные ноды.

Запуск:
    poetry run python scripts/backfill_article_authors.py
    poetry run python scripts/backfill_article_authors.py --uid <UID>
    poetry run python scripts/backfill_article_authors.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Корень проекта в sys.path + рабочая директория (для .env)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

from neomodel import config  # noqa: E402
from neomodel import db  # noqa: E402

from api.infrastructure.config import settings  # noqa: E402

config.DATABASE_URL = settings.get_database_url()

DEFAULT_BATCH_SIZE = 1000
DEFAULT_UID = "035f7f97a1b84bb99088af5200f997c6"  # Dimka

LABELS = ("Document", "KnowledgeStatement", "ArticleBlock")


def _missing_count(label: str) -> int:
    results, _ = db.cypher_query(
        f"MATCH (n:{label}) WHERE n.created_by_uid IS NULL OR n.created_by_uid = '' "
        "RETURN count(n)",
        {},
    )
    return results[0][0] if results else 0


def backfill(label: str, uid: str, batch_size: int, dry_run: bool) -> int:
    missing = _missing_count(label)
    if missing == 0:
        logger.info("%s: не требуется обновлений", label)
        return 0
    logger.info("%s: не привязано авторов — %d", label, missing)
    if dry_run:
        return 0

    updated = 0
    while True:
        results, _ = db.cypher_query(
            f"MATCH (n:{label}) WHERE n.created_by_uid IS NULL OR n.created_by_uid = '' "
            "WITH n LIMIT $batch "
            "SET n.created_by_uid = $uid "
            "RETURN count(n)",
            {"batch": batch_size, "uid": uid},
        )
        count = results[0][0] if results else 0
        if not count:
            break
        updated += count
        logger.info("%s: обновлено %d / %d", label, updated, missing)
    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Привязка автора к статьям/стейтментам/блокам без автора"
    )
    parser.add_argument(
        "--uid", type=str, default=DEFAULT_UID,
        help="UID пользователя, который станет автором (по умолчанию Dimka)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Размер пакета (по умолчанию 1000)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Только показать, сколько нод нуждается в обновлении",
    )
    args = parser.parse_args()

    total = 0
    for label in LABELS:
        total += backfill(label, args.uid, args.batch_size, args.dry_run)

    action = "Будет обновлено" if args.dry_run else "Обновлено"
    print(f"{action} нод с автором: {total}")


if __name__ == "__main__":
    main()
