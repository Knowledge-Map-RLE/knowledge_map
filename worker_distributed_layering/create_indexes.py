#!/usr/bin/env python3
"""
Скрипт для создания индексов в Neo4j для улучшения производительности
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к модулям проекта
sys.path.insert(0, str(Path(__file__).parent))

from src.neo4j_client import neo4j_client


async def create_indexes():
    """Создаёт необходимые индексы для улучшения производительности"""
    print("🔧 Создание индексов для Neo4j...")
    
    try:
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        print("✅ Подключение к Neo4j установлено")
        
        # Список индексов для создания
        indexes = [
            # Индекс на uid для быстрого поиска узлов
            "CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.uid)",
            
            # Индекс на is_pinned для быстрого подсчета закреплённых узлов
            "CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.is_pinned)",
            
            # Индекс на level для быстрого поиска по уровням
            "CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.level)",
            
            # Индекс на layer для быстрого поиска по слоям
            "CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.layer)",
            
            # Индекс на uid для связей CITES
            "CREATE INDEX IF NOT EXISTS FOR ()-[r:CITES]-() ON (r.uid)",
        ]
        
        for i, index_query in enumerate(indexes, 1):
            print(f"📊 Создание индекса {i}/{len(indexes)}...")
            try:
                result = await neo4j_client.execute_query_with_retry(index_query)
                print(f"✅ Индекс {i} создан успешно")
            except Exception as e:
                print(f"⚠️  Ошибка создания индекса {i}: {str(e)}")
        
        # Проверяем существующие индексы
        print("\n📋 Проверка существующих индексов...")
        result = await neo4j_client.execute_query_with_retry(
            "SHOW INDEXES YIELD name, labelsOrTypes, properties WHERE labelsOrTypes = ['Article']"
        )
        
        print("✅ Существующие индексы для Article:")
        for idx in result:
            print(f"   - {idx['name']}: {idx['properties']}")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    finally:
        await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(create_indexes())
