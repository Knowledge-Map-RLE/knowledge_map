"""
Скрипт для проверки лейблов в базе данных Neo4j
"""

import asyncio
import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.neo4j_client import neo4j_client


async def check_database_labels():
    """Проверяет какие лейблы есть в базе данных"""
    print("=== ПРОВЕРКА ЛЕЙБЛОВ В БАЗЕ ДАННЫХ ===")
    print()
    
    try:
        await neo4j_client.connect()
        print("✅ Подключение к Neo4j успешно")
        print()
        
        # Проверяем все лейблы
        print("1. Проверка всех лейблов:")
        labels_query = """
        CALL db.labels() YIELD label
        RETURN label
        ORDER BY label
        """
        
        labels_result = await neo4j_client.execute_query_with_retry(labels_query)
        if labels_result:
            print("Найденные лейблы:")
            for row in labels_result:
                print(f"  - {row['label']}")
        else:
            print("  Лейблы не найдены")
        print()
        
        # Проверяем количество узлов по лейблам
        print("2. Количество узлов по лейблам:")
        count_query = """
        CALL db.labels() YIELD label
        CALL apoc.cypher.doIt('MATCH (n:' + label + ') RETURN count(n) as count', {}) YIELD value
        RETURN label, value.count as count
        ORDER BY count DESC
        """
        
        try:
            count_result = await neo4j_client.execute_query_with_retry(count_query)
            if count_result:
                for row in count_result:
                    print(f"  - {row['label']}: {row['count']} узлов")
            else:
                print("  Не удалось получить количество узлов")
        except Exception as e:
            print(f"  Ошибка при подсчете узлов: {e}")
            # Альтернативный способ
            print("  Пробуем альтернативный способ...")
            for row in labels_result:
                label = row['label']
                try:
                    alt_query = f"MATCH (n:{label}) RETURN count(n) as count"
                    alt_result = await neo4j_client.execute_query_with_retry(alt_query)
                    if alt_result:
                        count = alt_result[0]['count']
                        print(f"  - {label}: {count} узлов")
                except Exception as e2:
                    print(f"  - {label}: ошибка - {e2}")
        print()
        
        # Проверяем свойства узлов
        print("3. Проверка свойств узлов:")
        properties_query = """
        CALL db.propertyKeys() YIELD propertyKey
        RETURN propertyKey
        ORDER BY propertyKey
        """
        
        try:
            properties_result = await neo4j_client.execute_query_with_retry(properties_query)
            if properties_result:
                print("Найденные свойства:")
                for row in properties_result:
                    print(f"  - {row['propertyKey']}")
            else:
                print("  Свойства не найдены")
        except Exception as e:
            print(f"  Ошибка при получении свойств: {e}")
        print()
        
        # Проверяем связи
        print("4. Проверка типов связей:")
        relationships_query = """
        CALL db.relationshipTypes() YIELD relationshipType
        RETURN relationshipType
        ORDER BY relationshipType
        """
        
        try:
            relationships_result = await neo4j_client.execute_query_with_retry(relationships_query)
            if relationships_result:
                print("Найденные типы связей:")
                for row in relationships_result:
                    print(f"  - {row['relationshipType']}")
            else:
                print("  Типы связей не найдены")
        except Exception as e:
            print(f"  Ошибка при получении типов связей: {e}")
        print()
        
        # Проверяем общую статистику
        print("5. Общая статистика:")
        stats_query = """
        MATCH (n) RETURN count(n) as total_nodes
        UNION ALL
        MATCH ()-[r]->() RETURN count(r) as total_relationships
        """
        
        try:
            stats_result = await neo4j_client.execute_query_with_retry(stats_query)
            if stats_result:
                total_nodes = stats_result[0]['total_nodes'] if len(stats_result) > 0 else 0
                total_relationships = stats_result[1]['total_relationships'] if len(stats_result) > 1 else 0
                print(f"  - Всего узлов: {total_nodes}")
                print(f"  - Всего связей: {total_relationships}")
            else:
                print("  Не удалось получить статистику")
        except Exception as e:
            print(f"  Ошибка при получении статистики: {e}")
        print()
        
        # Проверяем конкретно CITES связи
        print("6. Проверка CITES связей:")
        cites_query = """
        MATCH ()-[r:CITES]->() 
        RETURN count(r) as cites_count
        """
        
        try:
            cites_result = await neo4j_client.execute_query_with_retry(cites_query)
            if cites_result:
                cites_count = cites_result[0]['cites_count']
                print(f"  - CITES связей: {cites_count}")
            else:
                print("  CITES связи не найдены")
        except Exception as e:
            print(f"  Ошибка при проверке CITES связей: {e}")
        print()
        
        # Проверяем узлы с CITES связями
        print("7. Проверка узлов с CITES связями:")
        nodes_with_cites_query = """
        MATCH (n)-[:CITES]-()
        RETURN DISTINCT labels(n) as node_labels, count(n) as count
        ORDER BY count DESC
        """
        
        try:
            nodes_cites_result = await neo4j_client.execute_query_with_retry(nodes_with_cites_query)
            if nodes_cites_result:
                print("Узлы с CITES связями:")
                for row in nodes_cites_result:
                    labels = row['node_labels']
                    count = row['count']
                    print(f"  - {labels}: {count} узлов")
            else:
                print("  Узлы с CITES связями не найдены")
        except Exception as e:
            print(f"  Ошибка при проверке узлов с CITES связями: {e}")
        print()
        
    except Exception as e:
        print(f"❌ Ошибка подключения к Neo4j: {e}")
        return
    
    finally:
        try:
            await neo4j_client.close()
            print("✅ Соединение с Neo4j закрыто")
        except:
            pass


if __name__ == "__main__":
    print("Запуск проверки лейблов в базе данных...")
    print()
    
    try:
        asyncio.run(check_database_labels())
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
