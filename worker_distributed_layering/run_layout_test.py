#!/usr/bin/env python3
"""
Скрипт для запуска теста укладки с проверкой координат
"""

import asyncio
import logging
import sys
from src.algorithms.distributed_incremental_layout import distributed_incremental_layout

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция для тестирования укладки"""
    logger.info("=== ЗАПУСК ТЕСТА УКЛАДКИ ===")
    
    try:
        # Запускаем укладку
        logger.info("Запуск алгоритма укладки...")
        result = await distributed_incremental_layout.calculate_incremental_layout()
        
        if result.success:
            logger.info("✅ Укладка завершена успешно")
            logger.info(f"Статистика: {result.statistics}")
            
            # Проверяем координаты
            logger.info("Проверка координат...")
            await check_coordinates()
            
        else:
            logger.error(f"❌ Укладка завершилась с ошибкой: {result.error}")
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

async def check_coordinates():
    """Проверяет координаты после укладки"""
    from neo4j import AsyncGraphDatabase
    from src.config import settings
    
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password)
    )
    
    try:
        async with driver.session() as session:
            # Проверяем longest path блоки
            lp_query = """
            MATCH (n:Article)
            WHERE n.layout_status = 'in_longest_path'
            RETURN count(n) as count,
                   min(n.x) as min_x, max(n.x) as max_x,
                   min(n.y) as min_y, max(n.y) as max_y,
                   min(n.layer) as min_layer, max(n.layer) as max_layer
            """
            result = await session.run(lp_query)
            record = await result.single()
            if record:
                logger.info(f"Longest path: {record['count']} блоков")
                logger.info(f"  X: {record['min_x']} - {record['max_x']}")
                logger.info(f"  Y: {record['min_y']} - {record['max_y']}")
                logger.info(f"  Слои: {record['min_layer']} - {record['max_layer']}")
                
                # Проверяем, что координаты не равны (0,0)
                if record['min_x'] == 0 and record['max_x'] == 0:
                    logger.warning("⚠️  Все longest path блоки имеют x=0!")
                else:
                    logger.info("✅ Longest path блоки имеют правильные x координаты")
                    
                if record['min_y'] == 0 and record['max_y'] == 0:
                    logger.info("✅ Все longest path блоки имеют y=0 (это правильно)")
            
            # Проверяем блоки с координатами (0,0)
            zero_coords_query = """
            MATCH (n:Article)
            WHERE n.x = 0 AND n.y = 0
            RETURN count(n) as count
            """
            result = await session.run(zero_coords_query)
            record = await result.single()
            zero_count = record["count"] if record else 0
            logger.info(f"Блоков с координатами (0,0): {zero_count}")
            
            if zero_count == 0:
                logger.info("✅ Все блоки имеют ненулевые координаты!")
            else:
                logger.warning(f"⚠️  {zero_count} блоков имеют координаты (0,0)")
                
    except Exception as e:
        logger.error(f"Ошибка при проверке координат: {str(e)}")
        raise
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(main())
