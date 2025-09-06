"""
Скрипт для проверки соответствия Node и Article узлов
"""
import asyncio
import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_node_article_mapping():
    """Проверяем соответствие Node и Article узлов"""
    
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    
    try:
        async with driver.session() as session:
            # Проверяем LP Article узлы
            lp_articles_query = """
            MATCH (n:Article) 
            WHERE n.layout_status = 'in_longest_path' 
            RETURN n.uid as uid, n.x as x, n.y as y, n.layer as layer, n.level as level
            ORDER BY n.layer
            """
            
            result = await session.run(lp_articles_query)
            lp_articles = [dict(record) async for record in result]
            logger.info(f"LP Article nodes ({len(lp_articles)}):")
            for article in lp_articles:
                logger.info(f"  UID: {article['uid']}, X: {article['x']}, Y: {article['y']}, Layer: {article['layer']}, Level: {article['level']}")
            
            # Проверяем соответствующие Node узлы
            for article in lp_articles:
                uid = article['uid']
                node_query = f"""
                MATCH (n:Article {{uid: '{uid}'}}) 
                RETURN n.uid as uid, n.x as x, n.y as y, n.layer as layer, n.level as level, n.layout_status as status
                """
                
                result = await session.run(node_query)
                node_record = await result.single()
                
                if node_record:
                    node = dict(node_record)
                    logger.info(f"Corresponding Node for UID {uid}:")
                    logger.info(f"  UID: {node['uid']}, X: {node['x']}, Y: {node['y']}, Layer: {node['layer']}, Level: {node['level']}, Status: {node['status']}")
                    
                    # Проверяем соответствие координат
                    if (article['x'] == node['x'] and article['y'] == node['y'] and 
                        article['layer'] == node['layer'] and article['level'] == node['level']):
                        logger.info(f"  ✅ Coordinates match!")
                    else:
                        logger.info(f"  ❌ Coordinates mismatch!")
                else:
                    logger.info(f"  ❌ No corresponding Node found for UID {uid}")
                
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(check_node_article_mapping())
