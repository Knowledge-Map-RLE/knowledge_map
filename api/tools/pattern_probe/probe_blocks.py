"""Temporary probe: dump key blocks of target article."""
import json

from neomodel import db
from neomodel import config as neomodel_config

neomodel_config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
neomodel_config.ENCRYPTED = False

TARGET = "000657ba-aec6-8a11-9c5c-986526539651"

WANT = {1, 2, 7, 14, 20, 27, 37, 39, 40, 55, 57}


def main():
    res, _ = db.cypher_query(
        "MATCH (d:Document {uid:$u})-[:HAS_BLOCK]->(b:ArticleBlock) "
        "RETURN b.uid, b.block_type, b.data, b.order ORDER BY b.order",
        {"u": TARGET},
    )
    for uid, bt, data, order in res:
        if bt not in WANT:
            continue
        try:
            d = json.loads(data)
        except Exception:
            d = {}
        print(f"\n{'='*70}\norder={order} T{bt} uid={uid}\n{json.dumps(d, ensure_ascii=False, indent=1)}")


if __name__ == "__main__":
    main()
