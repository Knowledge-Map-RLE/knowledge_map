from models import Block
from neomodel import db

# Подключаемся к базе данных (используя конфигурацию из API)
import os
from neomodel import config
config.DATABASE_URL = os.getenv('NEO4J_DATABASE_URL', 'bolt://neo4j:password@localhost:7687')

try:
    # Проверяем конкретный блок
    block_id = "ee08efd342f241b481d715a1195aea90"
    result, _ = db.cypher_query(f'MATCH (b:Block {{uid: "{block_id}"}}) RETURN b.uid, b.is_pinned')
    print(f"Direct query result for {block_id}: {result}")

    # Проверяем через модель
    try:
        block = Block.nodes.get(uid=block_id)
        print(f"Block model: uid={block.uid}, is_pinned={block.is_pinned}")
    except Block.DoesNotExist:
        print(f"Block {block_id} not found using model")

    # Проверяем все закрепленные блоки
    result2, _ = db.cypher_query('MATCH (b:Block) WHERE b.is_pinned = true RETURN b.uid, b.content, b.is_pinned LIMIT 5')
    print(f"All pinned blocks: {result2}")

except Exception as e:
    print(f"Error: {e}") 