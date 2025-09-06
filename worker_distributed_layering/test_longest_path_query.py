"""
Скрипт для тестирования запроса поиска longest path
"""
import asyncio
import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_longest_path_query():
    """Тестируем запрос поиска longest path"""
    
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    
    try:
        async with driver.session() as session:
            # Сначала проверим, сколько всего путей в графе
            total_paths_query = """
            MATCH path = (start:Article)-[:CITES*1..5]->(end:Article)
            WHERE start <> end
            RETURN count(path) as total_paths
            """
            
            result = await session.run(total_paths_query)
            record = await result.single()
            logger.info(f"Total paths of length 1-5: {record['total_paths']}")
            
            # Теперь попробуем найти longest path с ограничением
            longest_path_query = """
            MATCH path = (start:Article)-[:CITES*1..10]->(end:Article)
            WHERE start <> end
            WITH path, length(path) as path_length
            ORDER BY path_length DESC
            LIMIT 1
            
            WITH path, nodes(path) as path_nodes, size(nodes(path)) as path_size
            RETURN path_size as longest_path_length
            """
            
            result = await session.run(longest_path_query)
            record = await result.single()
            if record:
                logger.info(f"Longest path length (limited to 10): {record['longest_path_length']}")
            else:
                logger.info("No paths found")
            
            # Попробуем без ограничения длины (может быть медленно)
            logger.info("Trying to find longest path without length limit...")
            try:
                unlimited_query = """
                MATCH path = (start:Article)-[:CITES*]->(end:Article)
                WHERE start <> end
                WITH path, length(path) as path_length
                ORDER BY path_length DESC
                LIMIT 1
                
                WITH path, nodes(path) as path_nodes, size(nodes(path)) as path_size
                RETURN path_size as longest_path_length
                """
                
                result = await session.run(unlimited_query)
                record = await result.single()
                if record:
                    logger.info(f"Longest path length (unlimited): {record['longest_path_length']}")
                else:
                    logger.info("No paths found")
            except Exception as e:
                logger.error(f"Error with unlimited query: {e}")
                
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(test_longest_path_query())
