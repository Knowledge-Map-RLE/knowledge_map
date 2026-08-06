"""Temporary probe: dump hypothesis-level blocks."""
import json

from neomodel import db
from neomodel import config as neomodel_config

neomodel_config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
neomodel_config.ENCRYPTED = False

TARGET = "000657ba-aec6-8a11-9c5c-986526539651"

WANT = {2, 7, 16, 37, 38, 39, 40, 44, 46, 47, 54, 22, 23, 51}


def main():
    res, _ = db.cypher_query(
        "MATCH (d:Document {uid:$u})-[:HAS_BLOCK]->(b:ArticleBlock) "
        "RETURN b.uid, b.block_type, b.data, b.order ORDER BY b.order",
        {"u": TARGET},
    )
    out = []
    for uid, bt, data, order in res:
        if bt not in WANT:
            continue
        try:
            d = json.loads(data)
        except Exception:
            d = {}
        out.append(f"\n{'='*70}\norder={order} T{bt} uid={uid}\n{json.dumps(d, ensure_ascii=False, indent=1)}")
    with open(r"C:\Users\dimka\AppData\Local\Temp\opencode\probe_hyp_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("written", len(out))


if __name__ == "__main__":
    main()
