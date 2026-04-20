from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
with driver.session() as s:
    s.run("MATCH ()-[r]->() DELETE r")
    print("Связи удалены")
    s.run("MATCH (n) DELETE n")
    print("Все узлы удалены")
driver.close()
print("База очищена")