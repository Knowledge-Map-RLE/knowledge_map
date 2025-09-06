"""
Скрипт для анализа структуры графа
"""
import asyncio
import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def analyze_graph_structure():
    """Анализируем структуру графа"""
    
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    
    try:
        async with driver.session() as session:
            # Общая статистика
            stats_query = """
            MATCH (n:Article)
            RETURN count(n) as total_nodes,
                   size([(n)-[:CITES]->() | 1]) as total_outgoing,
                   size([()-[:CITES]->(n) | 1]) as total_incoming
            """
            
            result = await session.run(stats_query)
            record = await result.single()
            logger.info(f"Graph statistics:")
            logger.info(f"  Total nodes: {record['total_nodes']}")
            logger.info(f"  Total outgoing edges: {record['total_outgoing']}")
            logger.info(f"  Total incoming edges: {record['total_incoming']}")
            
            # Анализ источников и стоков
            sources_sinks_query = """
            MATCH (n:Article)
            WITH n, 
                 size([(n)-[:CITES]->() | 1]) as out_degree,
                 size([()-[:CITES]->(n) | 1]) as in_degree
            RETURN 
                sum(CASE WHEN in_degree = 0 THEN 1 ELSE 0 END) as sources,
                sum(CASE WHEN out_degree = 0 THEN 1 ELSE 0 END) as sinks,
                sum(CASE WHEN in_degree > 0 AND out_degree > 0 THEN 1 ELSE 0 END) as intermediate
            """
            
            result = await session.run(sources_sinks_query)
            record = await result.single()
            logger.info(f"Node types:")
            logger.info(f"  Sources (no incoming): {record['sources']}")
            logger.info(f"  Sinks (no outgoing): {record['sinks']}")
            logger.info(f"  Intermediate: {record['intermediate']}")
            
            # Анализ длин путей
            path_lengths_query = """
            MATCH path = (start:Article)-[:CITES*1..5]->(end:Article)
            WHERE start <> end
            WITH length(path) as path_length, count(*) as count
            RETURN path_length, count
            ORDER BY path_length
            """
            
            result = await session.run(path_lengths_query)
            records = [dict(record) async for record in result]
            logger.info(f"Path length distribution:")
            for record in records:
                logger.info(f"  Length {record['path_length']}: {record['count']} paths")
            
            # Проверим, есть ли компоненты связности
            components_query = """
            CALL gds.wcc.stream('Article', {
                nodeLabels: ['Article'],
                relationshipTypes: ['CITES']
            })
            YIELD nodeId, componentId
            RETURN componentId, count(*) as component_size
            ORDER BY component_size DESC
            LIMIT 10
            """
            
            try:
                result = await session.run(components_query)
                records = [dict(record) async for record in result]
                logger.info(f"Largest connected components:")
                for record in records:
                    logger.info(f"  Component {record['componentId']}: {record['component_size']} nodes")
            except Exception as e:
                logger.info(f"GDS not available, trying alternative approach: {e}")
                
                # Альтернативный способ - найти узлы с наибольшим количеством связей
                alternative_query = """
                MATCH (n:Article)
                WITH n, 
                     size([(n)-[:CITES]->() | 1]) as out_degree,
                     size([()-[:CITES]->(n) | 1]) as in_degree
                WHERE out_degree > 0 OR in_degree > 0
                RETURN n.uid as uid, out_degree, in_degree, (out_degree + in_degree) as total_degree
                ORDER BY total_degree DESC
                LIMIT 10
                """
                
                result = await session.run(alternative_query)
                records = [dict(record) async for record in result]
                logger.info(f"Most connected nodes:")
                for record in records:
                    logger.info(f"  UID: {record['uid']}, Out: {record['out_degree']}, In: {record['in_degree']}, Total: {record['total_degree']}")
                
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(analyze_graph_structure())
