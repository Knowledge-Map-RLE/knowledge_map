#!/usr/bin/env python3
"""
Тест подсчета закреплённых узлов
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к модулям проекта
sys.path.insert(0, str(Path(__file__).parent))

from src.neo4j_client import neo4j_client


async def test_pinned_count():
    """Тест различных методов подсчета закреплённых узлов"""
    print("🔍 Тест подсчета закреплённых узлов...")
    
    try:
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        print("✅ Подключение к Neo4j установлено")
        
        # Тест 1: Проверяем существование поля is_pinned
        print("\n📊 Тест 1: Проверка существования поля is_pinned...")
        start_time = asyncio.get_event_loop().time()
        
        result = await neo4j_client.execute_query_with_retry(
            "MATCH (n:Article) WHERE n.is_pinned IS NOT NULL RETURN count(n) as count LIMIT 1"
        )
        
        execution_time = asyncio.get_event_loop().time() - start_time
        if result:
            count = result[0]["count"]
            print(f"✅ Узлов с полем is_pinned: {count:,} (время: {execution_time:.3f}s)")
        else:
            print(f"⚠️  Поле is_pinned не найдено (время: {execution_time:.3f}s)")
        
        # Тест 2: Подсчет закреплённых узлов
        print("\n📊 Тест 2: Подсчет закреплённых узлов...")
        start_time = asyncio.get_event_loop().time()
        
        result = await neo4j_client.execute_query_with_retry(
            "MATCH (n:Article) WHERE n.is_pinned = true RETURN count(n) as count LIMIT 1"
        )
        
        execution_time = asyncio.get_event_loop().time() - start_time
        if result:
            count = result[0]["count"]
            print(f"✅ Закреплённых узлов: {count:,} (время: {execution_time:.3f}s)")
        else:
            print(f"⚠️  Закреплённых узлов не найдено (время: {execution_time:.3f}s)")
        
        # Тест 3: Быстрая проверка существования
        print("\n📊 Тест 3: Быстрая проверка существования...")
        start_time = asyncio.get_event_loop().time()
        
        result = await neo4j_client.execute_query_with_retry(
            "MATCH (n:Article {is_pinned: true}) RETURN count(n) as count LIMIT 1"
        )
        
        execution_time = asyncio.get_event_loop().time() - start_time
        if result:
            count = result[0]["count"]
            print(f"✅ Закреплённых узлов (быстрый): {count:,} (время: {execution_time:.3f}s)")
        else:
            print(f"⚠️  Закреплённых узлов не найдено (быстрый) (время: {execution_time:.3f}s)")
        
        # Тест 4: Проверка индексов
        print("\n📊 Тест 4: Проверка индексов...")
        start_time = asyncio.get_event_loop().time()
        
        result = await neo4j_client.execute_query_with_retry(
            "SHOW INDEXES YIELD name, labelsOrTypes, properties WHERE labelsOrTypes = ['Article']"
        )
        
        execution_time = asyncio.get_event_loop().time() - start_time
        print(f"✅ Индексы для Article (время: {execution_time:.3f}s):")
        for idx in result:
            print(f"   - {idx['name']}: {idx['properties']}")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    finally:
        await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(test_pinned_count())
