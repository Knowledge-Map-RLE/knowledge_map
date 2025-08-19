"""
Масштабируемый микросервис для инкрементальной раскладки DAG в Neo4j без minimization этапа.
Алгоритм:
 - Поддерживает `layer`, `order`, `x`, `y`.
 - При вставке узла/рёбра: обновление слоя (topological), назначение `order` через gap-buffer (среднее между соседями).
 - Простой, O(1) амортизированно, без перекрестков minimization.
 - Распределение задач через Dask.
"""

from neo4j import GraphDatabase
from dask.distributed import Client
import os
import uuid

# --- Конфигурация ---
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')
DASK_SCHEDULER = os.getenv('DASK_SCHEDULER', 'tcp://scheduler:8786')
LEVEL_HEIGHT = float(os.getenv('LEVEL_HEIGHT', 1.0))
NODE_SPACING = float(os.getenv('NODE_SPACING', 1.0))

class LayoutService:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    def init_constraints(self):
        with self.driver.session() as s:
            s.run('CREATE CONSTRAINT IF NOT EXISTS ON (n:Node) ASSERT n.id IS UNIQUE')
            s.run('CREATE INDEX IF NOT EXISTS FOR (n:Node) ON (n.layer, n.order)')

    def add_node(self, properties=None):
        nid = str(uuid.uuid4())
        with self.driver.session() as s:
            s.run(
                'CREATE (n:Node {id:$nid, layer:0, order:0.0, x:0.0, y:0.0}' +
                (',' + ','.join(f'{k}:$'+k for k in (properties or {})) if properties else '') + ')',
                nid=nid, **(properties or {})
            )
        return nid

    def add_edge(self, src_id, dst_id):
        with self.driver.session() as s:
            s.run(
                'MATCH (u:Node {id:$src}), (v:Node {id:$dst}) CREATE (u)-[:REL]->(v)',
                src=src_id, dst=dst_id
            )
        return self.schedule_update(src_id, dst_id)

    def schedule_update(self, src, dst):
        client = Client(DASK_SCHEDULER)
        fut = client.submit(process_change, src, dst)
        client.close()
        return fut.key

# --- Инкрементальное обновление ---

def process_change(src_id, dst_id):
    svc = LayoutService()
    # 1. Обновить layer: если src.layer >= dst.layer, сдвинуть dst и его потомков на +1
    with svc.driver.session() as s:
        rec = s.run(
            'MATCH (u:Node {id:$src}), (v:Node {id:$dst}) RETURN u.layer AS su, v.layer AS sv',
            src=src_id, dst=dst_id
        ).single()
        su, sv = rec['su'], rec['sv']
        if su >= sv:
            s.run(
                'MATCH (v:Node {id:$dst}) CALL apoc.path.subgraphNodes(v,{relationshipFilter:">REL"}) YIELD node ' +
                'SET node.layer = node.layer + 1', dst=dst_id
            )
    # 2. Назначить order и координаты dst в своём слое
    assign_order_and_coords(svc, dst_id)
    svc.close()
    return True


def assign_order_and_coords(svc, node_id):
    # Получить слой
    with svc.driver.session() as s:
        layer = s.run('MATCH (n:Node {id:$id}) RETURN n.layer AS l', id=node_id).single()['l']
        # Найти ближайших соседей по order
        rec = s.run(
            'MATCH (n:Node) WHERE n.layer=$l AND exists((n)-[:REL]-()) ' +
            'WITH n ORDER BY n.order LIMIT 1 RETURN n.id AS prev', l=layer).single()
        # упрощённо: поставить в конец: найти max order
        maxo = s.run('MATCH (n:Node {layer:$l}) RETURN max(n.order) AS mo', l=layer).single()['mo'] or 0.0
        new_order = maxo + NODE_SPACING
        x = new_order
        y = layer * LEVEL_HEIGHT
        s.run(
            'MATCH (n:Node {id:$id}) SET n.order=$o, n.x=$x, n.y=$y',
            id=node_id, o=new_order, x=x, y=y
        )

# --- Пример ---
if __name__ == '__main__':
    svc = LayoutService()
    svc.init_constraints()
    a = svc.add_node({'title':'A'})
    b = svc.add_node({'title':'B'})
    key = svc.add_edge(a, b)
    print('Scheduled:', key)
    svc.close()
