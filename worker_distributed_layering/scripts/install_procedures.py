#!/usr/bin/env python3
"""
Скрипт для установки Neo4j процедур и индексов
Выполняется при запуске контейнера
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем путь к модулям проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.neo4j_client import neo4j_client
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def install_neo4j_procedures():
    """Устанавливает Neo4j процедуры и индексы"""
    logger.info("Starting Neo4j procedures installation...")
    
    try:
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        logger.info("Connected to Neo4j")
        
        # Читаем файл с процедурами
        procedures_file = Path(__file__).parent.parent / "cypher_procedures" / "simple_functions.cypher"
        
        if not procedures_file.exists():
            logger.warning(f"Procedures file not found: {procedures_file}")
            return False
        
        with open(procedures_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Разбиваем на отдельные команды
        statements = [stmt.strip() for stmt in content.split(';') if stmt.strip() and not stmt.strip().startswith('//')]
        
        logger.info(f"Found {len(statements)} statements to execute")
        
        success_count = 0
        for i, statement in enumerate(statements, 1):
            try:
                logger.info(f"Executing statement {i}/{len(statements)}")
                await neo4j_client.execute_query_with_retry(statement + ";")
                success_count += 1
                logger.info(f"Statement {i} executed successfully")
            except Exception as e:
                logger.warning(f"Statement {i} failed: {str(e)}")
                # Продолжаем выполнение других команд
        
        logger.info(f"Installation completed: {success_count}/{len(statements)} statements successful")
        
        # Проверяем установленные индексы
        verify_query = """
        SHOW INDEXES
        YIELD name
        WHERE name CONTAINS 'node_' OR name CONTAINS 'relationship_' OR name CONTAINS 'pinned_'
        RETURN count(name) as installedIndexes;
        """
        
        result = await neo4j_client.execute_query_with_retry(verify_query)
        if result:
            installed_count = result[0].get('installedIndexes', 0)
            logger.info(f"Verified {installed_count} indexes installed")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Failed to install procedures: {str(e)}")
        return False
    finally:
        await neo4j_client.close()


async def main():
    """Основная функция"""
    logger.info("Neo4j procedures installer started")
    
    # Ждём немного для готовности Neo4j
    await asyncio.sleep(10)
    
    success = await install_neo4j_procedures()
    
    if success:
        logger.info("Procedures installation completed successfully")
        sys.exit(0)
    else:
        logger.error("Procedures installation failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
