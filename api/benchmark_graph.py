"""Benchmark: сколько времени занимает запрос графа."""
import time, sys
sys.path.insert(0, '.')

from adapters.repositories.pattern_graph_repository import PatternGraphRepository

t0 = time.time()
repo = PatternGraphRepository()
nodes, edges = repo.get_global_linguistic_graph()
t1 = time.time()

print(f"nodes={len(nodes)}")
print(f"edges={len(edges)}")
print(f"query_time={t1-t0:.2f}s")

# Проверим есть ли layout
has_layout = sum(1 for n in nodes if n.get("layout_x") is not None)
print(f"nodes_with_layout={has_layout}")
