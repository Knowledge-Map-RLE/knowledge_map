import time
import redis
from neo4j import GraphDatabase
import json
# Assuming layout_algorithm.py is in the same directory or accessible via path
from .layout_algorithm import layout_graph  # Import the layout algorithm
from .neo4j_procedures import get_subgraph # Import neo4j procedures

def process_task(task_data):
    """
    Processes a layout task.
    """
    article_id = task_data.get("article_id")
    depth = task_data.get("depth", 2)  # Default depth

    # 1. Get subgraph from Neo4j
    with GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password")) as driver:
        with driver.session() as session:
            subgraph_data = session.read_transaction(get_subgraph, article_id=article_id, depth=depth)

    if not subgraph_data:
        print(f"No subgraph found for article ID: {article_id}")
        return

    nodes = subgraph_data[0]
    relationships = subgraph_data[1]

    # Convert Neo4j graph data to a format suitable for the layout algorithm
    graph = {
        "nodes": [{"id": node.id, "label": node.labels} for node in nodes],
        "edges": [{"source": rel.start_node.id, "target": rel.end_node.id, "type": type(rel)} for rel in relationships],
    }

    # 2. Apply layout algorithm
    layouted_graph = layout_graph(graph)

    # 3. Persist layouted graph data back to Neo4j
    #  ... Implementation to update node positions in Neo4j ...
    print(f"Layout complete for subgraph starting at article {article_id}")

def start_worker():
    """
    Starts the worker, listening for tasks.
    """
    r = redis.Redis(host='redis', port=6379, db=0)
    print('Waiting for tasks...')

    while True:
        task = r.blpop('layout_tasks')
        if task:
            queue_name, task_data_json = task
            task_data = json.loads(task_data_json.decode('utf-8'))

            print(f'Received task: {task_data}')
            process_task(task_data)
        else:
            time.sleep(1)

if __name__ == '__main__':
    start_worker()
