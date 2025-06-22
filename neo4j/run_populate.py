#!/usr/bin/env python3
"""
Упрощенный скрипт для автоматического заполнения Neo4j тестовыми данными
Запускается без интерактивного подтверждения для автоматизации
"""

import sys
import os

# Добавляем путь к api папке для импорта моделей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from neomodel import config, db, clear_neo4j_database
from populate_test_data import (
    create_test_user, create_test_blocks, create_test_links, 
    create_test_tags, assign_random_tags, verify_data
)

# Настройка подключения к Neo4j
NEO4J_URL = os.getenv('NEO4J_URL', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

config.DATABASE_URL = f'bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{NEO4J_URL.replace("bolt://", "")}'

def auto_populate():
    """Автоматически заполняет базу тестовыми данными"""
    print("=== Автоматическое заполнение Neo4j тестовыми данными ===")
    print(f"Подключение к Neo4j: {config.DATABASE_URL}")
    
    try:
        # Проверяем подключение
        db.cypher_query("RETURN 1")
        print("✓ Подключение к Neo4j установлено")
        
    except Exception as e:
        print(f"❌ Ошибка подключения к Neo4j: {e}")
        print("Убедитесь что Neo4j запущен и доступен")
        return False
    
    try:
        # Очищаем базу данных БЕЗ подтверждения
        print("\n🗑️  Очищаю базу данных...")
        clear_neo4j_database(db)
        print("✓ База данных очищена")
        
        # Создаем тестовые данные
        print("\n📊 Создаю тестовые данные...")
        
        # 1. Создаем пользователя
        user = create_test_user()
        
        # 2. Создаем блоки
        blocks = create_test_blocks(user, 20)
        
        # 3. Создаем связи
        links = create_test_links(blocks, user, 10)
        
        # 4. Создаем теги
        tags = create_test_tags()
        
        # 5. Назначаем теги блокам
        assign_random_tags(blocks, tags)
        
        # 6. Проверяем результат
        stats = verify_data()
        
        print("\n✅ Тестовые данные успешно созданы!")
        print(f"📈 Статистика: {stats}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании данных: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = auto_populate()
    sys.exit(0 if success else 1) 