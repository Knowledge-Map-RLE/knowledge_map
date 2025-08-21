#!/usr/bin/env python3
"""
Тест подсчета рёбер CITES
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к модулям проекта
sys.path.insert(0, str(Path(__file__).parent))

from src.neo4j_client import neo4j_client


async def test_edge_count():
    """Тест различных методов подсчета рёбер"""
    print("🔍 Тест подсчета рёбер CITES...")
    
    try:
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        print("✅ Подключение к Neo4j установлено")
        
        # Тест 1: Прямой COUNT (должен быть быстрым)
        print("\n📊 Тест 1: Прямой COUNT...")
        start_time = asyncio.get_event_loop().time()
        
        result = await neo4j_client.execute_query_with_retry(
            "MATCH ()-[r:CITES]->() RETURN count(r) as count"
        )
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        if result:
            count = result[0]["count"]
            print(f"✅ COUNT выполнен за {duration:.3f}s: {count:,} рёбер")
        else:
            print("❌ COUNT не вернул результат")
        
        # Тест 2: Статистика Neo4j
        print("\n📊 Тест 2: Статистика Neo4j...")
        start_time = asyncio.get_event_loop().time()
        
        try:
            stats_result = await neo4j_client.execute_query_with_retry(
                """
                CALL db.stats.retrieve('GRAPH COUNTS')
                YIELD data
                UNWIND data AS stat
                WHERE stat.relationshipType = 'CITES'
                RETURN coalesce(stat.count, 0) as count
                """
            )
            
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            
            if stats_result:
                count = stats_result[0]["count"]
                print(f"✅ Статистика получена за {duration:.3f}s: {count:,} рёбер")
            else:
                print("⚠️  Статистика не найдена")
                
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {str(e)}")
        
        # Тест 3: Проверка существования
        print("\n📊 Тест 3: Проверка существования...")
        start_time = asyncio.get_event_loop().time()
        
        exists_result = await neo4j_client.execute_query_with_retry(
            "MATCH ()-[r:CITES]->() RETURN 1 as exists LIMIT 1"
        )
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        if exists_result:
            print(f"✅ Связи существуют (проверка за {duration:.3f}s)")
        else:
            print("❌ Связи не найдены")
        
        print("\n✅ Все тесты завершены")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return False
    finally:
        await neo4j_client.close()
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_edge_count())
    sys.exit(0 if success else 1)
