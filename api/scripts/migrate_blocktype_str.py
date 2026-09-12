"""
Layer: Frameworks & Drivers — Scripts
Package: scripts.migrate_blocktype_str
Responsibility: одноразовая миграция числовых block_type на узлах ArticleBlock
в Neo4j в строковые обозначения из Спецификации.md (см. block_types.py).

Запуск (из каталога api/):
    poetry run python scripts/migrate_blocktype_str.py            # применить
    poetry run python scripts/migrate_blocktype_str.py --dry-run   # только посмотреть
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from neomodel import db  # noqa: E402

from infrastructure.config import settings  # noqa: E402
from src.schemas.block_types import coerce_block_type  # noqa: E402

_QUERY = """
MATCH (b:ArticleBlock)
WHERE b.block_type IS NOT NULL
  AND b.block_type <> ''
  AND toString(b.block_type) =~ '^[0-9]+$'
RETURN b.uid AS uid, toString(b.block_type) AS bt
ORDER BY uid
"""


def run(dry_run: bool) -> int:
    db.set_connection(settings.get_database_url())
    results, _ = db.cypher_query(_QUERY)

    if not results:
        print("Числовых block_type не найдено — миграция не требуется.")
        return 0

    print(f"Найдено узлов с числовым block_type: {len(results)}")

    updates: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    for uid, raw in results:
        designation = coerce_block_type(raw)
        if not designation or designation == raw:
            skipped.append((uid, raw))
            continue
        updates.append((uid, raw, designation))

    print(f"  к обновлению: {len(updates)}; пропущено (нет маппинга): {len(skipped)}")
    for uid, raw, designation in updates:
        print(f"    {uid}: {raw} -> {designation}")
    for uid, raw in skipped:
        print(f"    {uid}: {raw} (не распознан, оставлено)")

    if dry_run:
        print("--dry-run: изменения не применены.")
        return 0

    for uid, _raw, designation in updates:
        db.cypher_query(
            "MATCH (b:ArticleBlock {uid: $uid}) SET b.block_type = $designation",
            {"uid": uid, "designation": designation},
        )

    print(f"Обновлено узлов: {len(updates)}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[4].strip())
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, какие узлы будут обновлены, без изменений.",
    )
    args = parser.parse_args()
    return run(args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())