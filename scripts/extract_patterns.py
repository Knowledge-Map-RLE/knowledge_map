"""
CLI-скрипт: извлечение паттернов из существующей БД Neo4j.

Работает поверх существующих Action и LexicalUnit узлов — не удаляет и не пересоздаёт
их. Создаёт только узлы Pattern с связями CONTAINS_NODE.

Использование:
    poetry run python scripts/extract_patterns.py
    poetry run python scripts/extract_patterns.py --mode dependency --max-depth 5
    poetry run python scripts/extract_patterns.py --mode action --min-frequency 2
    poetry run python scripts/extract_patterns.py --mode all --save
    poetry run python scripts/extract_patterns.py --doc-id <doc_id>
    poetry run python scripts/extract_patterns.py --global --max-nodes 50 --limit-per-n 30

После запуска:
    - Паттерны извлечены и сохранены в Neo4j (с флагом --save)
    - Или только выведены в консоль (по умолчанию)
    - На странице /nlp нажмите «Анализировать» для просмотра
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(str(project_root))

import os
from neo4j import GraphDatabase

from api.infrastructure.config import settings
from api.application.patterns.pattern_extractor import PatternExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Извлечение паттернов (Action + LexicalUnit графы) из Neo4j.",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "dependency", "action", "mixed"],
        default="all",
        help="Режим извлечения (по умолчанию: all)",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=100,
        help="Макс. узлов в паттерне (по умолчанию: 100)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        help="Макс. глубина dependency n-grams (по умолчанию: 5)",
    )
    parser.add_argument(
        "--limit-per-n",
        type=int,
        default=50,
        help="Лимит паттернов на длину (по умолчанию: 50)",
    )
    parser.add_argument(
        "--min-frequency",
        type=int,
        default=1,
        help="Мин. частота паттерна (по умолчанию: 1)",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="ID документа для анализа (по умолчанию: все документы)",
    )
    parser.add_argument(
        "--global",
        dest="is_global",
        action="store_true",
        help="Глобальный анализ всех документов",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Сохранить паттерны в Neo4j",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Путь для сохранения результата в JSON (по умолчанию: не сохраняется)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Показать топ-N паттернов в консоли (по умолчанию: 20)",
    )

    args = parser.parse_args()

    # Создаём driver
    uri = os.getenv("NEO4J_URI", settings.NEO4J_URI)
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    # Очищаем uri от префиксов протоколов, если они есть
    uri_clean = uri.replace("neo4j://", "bolt://").replace("bolt+ssc://", "bolt://")
    logger.info(f"Neo4j: {uri_clean}")

    driver = GraphDatabase.driver(uri_clean, auth=(user, password))

    try:
        extractor = PatternExtractor(driver)

        logger.info(f"Режим: {args.mode}, max_nodes: {args.max_nodes}, max_depth: {args.max_depth}")
        if args.doc_id:
            logger.info(f"Документ: {args.doc_id}")

        # Извлекаем паттерны
        result = extractor.extract_all(
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
            limit_per_n=args.limit_per_n,
            min_frequency=args.min_frequency,
            doc_id=args.doc_id,
        )

        logger.info(f"Извлечено {result.total_patterns} паттернов")
        logger.info(f"Макс. узлов: {result.max_nodes_seen}")
        logger.info(f"Документов: {len(result.doc_ids)}")

        # Показываем топ паттерны
        top_n = min(args.top, result.total_patterns)
        sorted_patterns = sorted(result.patterns, key=lambda p: p.frequency, reverse=True)
        if top_n > 0:
            logger.info(f"\nТоп-{top_n} паттернов по частоте:")
            for i, p in enumerate(sorted_patterns[:top_n]):
                freq_info = f"частота={p.frequency}"
                if p.stability > 0:
                    freq_info += f", стабильность={p.stability:.2f}"
                if p.doc_count > 0:
                    freq_info += f", документов={p.doc_count}"
                logger.info(
                    f"  #{i+1}: {p.name} ({p.size_category}) "
                    f"[{p.node_count} узлов, {p.edge_count} рёбер] — {freq_info}"
                )

        # Сохраняем в БД
        if args.save:
            logger.info("Сохранение паттернов в Neo4j...")
            saved = _save_patterns_to_db(driver, result.patterns)
            logger.info(f"Сохранено {saved} паттернов")

        # Сохраняем в JSON
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "total_patterns": result.total_patterns,
                        "max_nodes_seen": result.max_nodes_seen,
                        "doc_ids": result.doc_ids,
                        "patterns": [p.to_dict() for p in sorted_patterns],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(f"Результат сохранён в {output_path}")

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        driver.close()


def _save_patterns_to_db(driver, patterns):
    """Сохраняет паттерны в Neo4j через Cypher."""
    saved = 0
    with driver.session() as session:
        for p in patterns:
            edges_json = json.dumps(
                [
                    {
                        "source_id": e.source_id,
                        "target_id": e.target_id,
                        "edge_type": e.edge_type.value,
                        "relation_subtype": e.relation_subtype,
                    }
                    for e in p.canon_edges
                ],
                ensure_ascii=False,
            )

            session.run(
                """
                CREATE (pat:Pattern {
                    uid: $uid,
                    name: $name,
                    description: $description,
                    pattern_hash: $pattern_hash,
                    frequency: $frequency,
                    stability: $stability,
                    doc_count: $doc_count,
                    node_count: $node_count,
                    edge_count: $edge_count,
                    size_category: $size_category,
                    edges_json: $edges_json
                })
                """,
                {
                    "uid": p.uid,
                    "name": p.name,
                    "description": p.description,
                    "pattern_hash": p.pattern_hash,
                    "frequency": p.frequency,
                    "stability": p.stability,
                    "doc_count": p.doc_count,
                    "node_count": p.node_count,
                    "edge_count": p.edge_count,
                    "size_category": p.size_category,
                    "edges_json": edges_json,
                },
            )
            saved += 1
    return saved


if __name__ == "__main__":
    main()
