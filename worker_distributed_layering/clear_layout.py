"""
Скрипт для очистки всех позиций layout
"""
import asyncio
import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_layout():
    """Очищаем все позиции layout"""
    
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    
    try:
        async with driver.session() as session:
            # Очищаем все позиции layout
            clear_query = """
            MATCH (n:Article)
            REMOVE n.layer, n.level, n.x, n.y, n.layout_status
            RETURN count(n) as cleared_count
            """
            
            result = await session.run(clear_query)
            record = await result.single()
            logger.info(f"Cleared layout positions for {record['cleared_count']} articles")
                
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(clear_layout())
