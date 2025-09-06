"""
Скрипт для синхронизации координат между Article и Node узлами
"""
import asyncio
import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_coordinates():
    """Синхронизируем координаты между Article и Node узлами"""
    
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    
    try:
        async with driver.session() as session:
            # Синхронизируем координаты для всех Article узлов с layout данными
            sync_query = """
            MATCH (a:Article)
            WHERE a.x IS NOT NULL AND a.y IS NOT NULL AND a.layer IS NOT NULL AND a.level IS NOT NULL
            MERGE (n:Article {uid: a.uid})
            SET n.x = a.x,
                n.y = a.y,
                n.layer = a.layer,
                n.level = a.level,
                n.layout_status = a.layout_status
            RETURN count(n) as synced_count
            """
            
            result = await session.run(sync_query)
            record = await result.single()
            logger.info(f"Synced coordinates for {record['synced_count']} nodes")
            
            # Проверяем результат
            check_query = """
            MATCH (n:Article) 
            WHERE n.layout_status = 'in_longest_path' 
            RETURN count(n) as node_count
            """
            
            result = await session.run(check_query)
            record = await result.single()
            logger.info(f"Node nodes with LP status after sync: {record['node_count']}")
            
            # Показываем LP Node узлы
            lp_nodes_query = """
            MATCH (n:Article) 
            WHERE n.layout_status = 'in_longest_path' 
            RETURN n.uid as uid, n.x as x, n.y as y, n.layer as layer, n.level as level
            ORDER BY n.layer
            """
            
            result = await session.run(lp_nodes_query)
            lp_nodes = [dict(record) async for record in result]
            logger.info(f"LP Node nodes ({len(lp_nodes)}):")
            for node in lp_nodes:
                logger.info(f"  UID: {node['uid']}, X: {node['x']}, Y: {node['y']}, Layer: {node['layer']}, Level: {node['level']}")
                
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(sync_coordinates())
