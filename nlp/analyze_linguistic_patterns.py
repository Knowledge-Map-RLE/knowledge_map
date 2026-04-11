"""
Скрипт для комплексного анализа лингвистических паттернов в Neo4j.

Обёртка над UnifiedPatternAnalyzer (api/application/patterns/unified_pattern_analyzer.py).
Делегирует весь анализ единому сервису.

Запуск: poetry run python nlp/analyze_linguistic_patterns.py
"""

import os
import sys
import logging

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация подключения
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    """
    Обёртка над UnifiedPatternAnalyzer.
    Делегирует анализ сервису из api/application/patterns/unified_pattern_analyzer.py
    """
    # Добавляем api/ в sys.path
    api_path = os.path.join(os.path.dirname(__file__), "api")
    if api_path not in sys.path:
        sys.path.insert(0, api_path)

    from application.patterns.unified_pattern_analyzer import UnifiedPatternAnalyzer

    logger.info("=" * 60)
    logger.info("АНАЛИЗ ЛИНГВИСТИЧЕСКИХ ПАТТЕРНОВ")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    analyzer = UnifiedPatternAnalyzer(driver)

    try:
        result = analyzer.analyze_global(output_dir="docs")

        logger.info("=" * 60)
        logger.info("АНАЛИЗ ЗАВЕРШЁН УСПЕШНО")
        logger.info(f"Узлов: {result.graph_stats['nodes']}")
        logger.info(f"Рёбер: {result.graph_stats['relationships']}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Ошибка при анализе: {e}", exc_info=True)
        raise
    finally:
        driver.close()


if __name__ == "__main__":
    main()
