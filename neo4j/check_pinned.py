from neomodel import db

# Проверяем конкретный блок
block_id = "ee08efd342f241b481d715a1195aea90"
result, _ = db.cypher_query(f'MATCH (b:Block {{uid: "{block_id}"}}) RETURN b.uid, b.is_pinned')
print(f"Block {block_id}:")
print(f"Result: {result}")

# Проверяем все закрепленные блоки
result2, _ = db.cypher_query('MATCH (b:Block) WHERE b.is_pinned = true RETURN b.uid, b.content, b.is_pinned')
print(f"\nAll pinned blocks:")
print(f"Result: {result2}") 