import time, sys, json
sys.path.insert(0, '.')
from adapters.repositories.pattern_graph_repository import PatternGraphRepository

t0 = time.time()
repo = PatternGraphRepository()
nodes, edges = repo.get_global_linguistic_graph()
t1 = time.time()

with open('bench_result.json', 'w') as f:
    json.dump({
        "nodes": len(nodes),
        "edges": len(edges),
        "time_sec": round(t1 - t0, 2),
        "has_layout": sum(1 for n in nodes if n.get("layout_x") is not None)
    }, f)
