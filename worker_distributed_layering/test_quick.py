#!/usr/bin/env python3
"""
Быстрый тест для проверки подключения и базовых запросов
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к модулям проекта
sys.path.insert(0, str(Path(__file__).parent))

from src.neo4j_client import neo4j_client


async def quick_test():
    """Быстрый тест подключения и запросов"""
    print("🔍 Быстрый тест Neo4j подключения...")
    
    try:
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        print("✅ Подключение к Neo4j установлено")
        
        # Простой тест - подсчет узлов
        print("📊 Подсчет узлов Article...")
        result = await neo4j_client.execute_query_with_retry(
            "MATCH (n:Article) RETURN count(n) as count LIMIT 1"
        )
        
        if result:
            count = result[0]["count"]
            print(f"✅ Найдено узлов Article: {count:,}")
        else:
            print("⚠️  Не удалось получить количество узлов")
        
        # Проверяем наличие связей CITES быстрее (без полного COUNT по графу)
        print("🔗 Проверка связей CITES...")
        try:
            # Попытка: взять оценку из статистики
            stats_query = (
                "CALL db.stats.retrieve('GRAPH COUNTS') YIELD data "
                "UNWIND data AS stat "
                "WITH stat WHERE stat.relationshipType = 'CITES' "
                "RETURN coalesce(stat.count, 0) AS count LIMIT 1"
            )
            cites_result = await neo4j_client.execute_query_with_retry(stats_query)

            cites_count = 0
            if cites_result and "count" in cites_result[0]:
                cites_count = cites_result[0]["count"] or 0

            # Фолбэк: просто проверить наличие хотя бы одной связи
            if cites_count == 0:
                exists = await neo4j_client.execute_query_with_retry(
                    "MATCH ()-[r:CITES]->() RETURN 1 AS ok LIMIT 1"
                )
                if exists:
                    print("✅ Связи CITES существуют (минимум 1)")
                else:
                    print("⚠️  Связи CITES не найдены")
            else:
                print(f"✅ Оценка количества связей CITES: {cites_count:,}")
        except Exception as e:
            print(f"⚠️  Ошибка при получении статистики связей: {str(e)}")
        
        print("✅ Тест завершен успешно")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return False
    finally:
        await neo4j_client.close()
    
    return True


if __name__ == "__main__":
    success = asyncio.run(quick_test())
    sys.exit(0 if success else 1)