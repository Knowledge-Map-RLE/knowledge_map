import sys
sys.path.insert(0, "d:/Knowledge_Map/api")
from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
r,_=db.cypher_query('MATCH ()-[rel:LEADS_TO]->() WHERE rel.relation_subtype <> "PART_OF_GOAL" RETURN rel.status, count(rel) ORDER BY count(rel) DESC')
for row in r: print(row[0], row[1])
