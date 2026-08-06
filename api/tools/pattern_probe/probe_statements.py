"""Temporary probe: sample statements of target article."""
from neomodel import db
from neomodel import config as neomodel_config

neomodel_config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
neomodel_config.ENCRYPTED = False

TARGET = "000657ba-aec6-8a11-9c5c-986526539651"


def q(c, **p):
    r, _ = db.cypher_query(c, p)
    return r


def dump(title, c, **p):
    rows = q(c, **p)
    print(f"\n===== {title} ({len(rows)}) =====")
    for r in rows[:60]:
        print(" | ".join(str(x) for x in r))


def main():
    dump(
        "FINDING direction statements",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
        "WHERE s.predicate IN ['понижено в','повышено в','без изменений в','тренд в'] "
        "RETURN s.subject_text, s.predicate, s.object_text, s.sort_order LIMIT 60",
        u=TARGET,
    )
    dump(
        "EXPERIMENT -> result",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {predicate:'результат'}) "
        "RETURN s.subject_text, s.predicate, s.object_text LIMIT 20",
        u=TARGET,
    )
    dump(
        "GROUP назначение",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {predicate:'назначение'}) "
        "RETURN s.subject_text, s.predicate, s.object_text LIMIT 30",
        u=TARGET,
    )
    dump(
        "p-value META",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {predicate:'p-value'}) "
        "RETURN s.subject_text, s.predicate, s.object_text LIMIT 12",
        u=TARGET,
    )
    dump(
        "CLAIM-like (T38 predicates)",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
        "WHERE s.predicate IN ['является','ингибирует','связано с','определяет','уверенность'] "
        "AND s.type='FACT' RETURN s.subject_text, s.predicate, s.object_text LIMIT 30",
        u=TARGET,
    )
    dump(
        "GOAL statements",
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {predicate:'цель'}) "
        "RETURN s.subject_text, s.predicate, s.object_text LIMIT 10",
        u=TARGET,
    )


if __name__ == "__main__":
    main()
