"""
Скрипт создания индексов для оптимизации dependency n-gram запросов.

Запуск: poetry run python scripts/create_ngram_indexes.py
"""
import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def create_indexes():
    """Создаёт индексы для ускорения поиска паттернов."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    queries = [
        # Индекс по pos для быстрого поиска LexicalUnit по части речи
        "CREATE INDEX lexical_unit_pos IF NOT EXISTS FOR (lu:LexicalUnit) ON (lu.pos)",
        
        # Индекс по dep для фильтрации по типу зависимости
        "CREATE INDEX lexical_unit_dep IF NOT EXISTS FOR (lu:LexicalUnit) ON (lu.dep)",
        
        # Индекс по lemma для кросс-документных запросов
        "CREATE INDEX lexical_unit_lemma IF NOT EXISTS FOR (lu:LexicalUnit) ON (lu.lemma)",
        
        # Индекс по verb для Action узлов
        "CREATE INDEX action_verb IF NOT EXISTS FOR (a:Action) ON (a.verb)",
        
        # Составной индекс для быстрого поиска verb + lemma
        "CREATE INDEX action_verb_lemma IF NOT EXISTS FOR (a:Action) ON (a.verb, a.verb_lemma)",
        
        # Индекс по text для поиска текстовых совпадений
        "CREATE INDEX lexical_unit_text IF NOT EXISTS FOR (lu:LexicalUnit) ON (lu.text)",
    ]
    
    print(f"Подключение к Neo4j: {NEO4J_URI}")
    with driver.session() as session:
        for query in queries:
            try:
                session.run(query)
                # Извлекаем имя индекса из запроса для логирования
                idx_name = query.split("INDEX ")[1].split(" IF")[0] if "INDEX " in query else "?"
                print(f"  ✓ {idx_name}")
            except Exception as e:
                print(f"  ✗ {query[:60]}... : {e}")
    
    # Проверяем созданные индексы
    print("\nАктивные индексы:")
    with driver.session() as session:
        result = session.run("SHOW INDEXES")
        for record in result:
            if record.get("type") == "RANGE" and record.get("entityType") == "NODE":
                name = record.get("name", "?")
                labels = record.get("labelsOrTypes", [])
                props = record.get("properties", [])
                state = record.get("state", "?")
                print(f"  {name}: {labels} {props} [{state}]")
    
    driver.close()
    print("\nГотово!")


if __name__ == "__main__":
    create_indexes()
