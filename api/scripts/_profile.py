# -*- coding: utf-8 -*-
"""Профилировка фаз generate_all на корпусе документов с утверждениями."""
import asyncio, time
from neomodel import config as neo_config
from infrastructure.config import settings

neo_config.DATABASE_URL = settings.get_database_url()

from adapters.repositories.pattern_miner_repository import PatternMinerRepository
from services.pattern_miner_service import _is_meaningful

async def main() -> None:
    repo = PatternMinerRepository()
    t = time.time()
    corpus = repo.load_corpus(doc_limit=60, statements_per_doc_cap=140, noise_filter=False)
    print("[load_corpus]", round(time.time()-t, 1), "s, docs:", len(corpus),
          "stmts:", sum(len(e['statements']) for e in corpus))

    pool = [
        {"subject_text": st.get("subject_text"), "predicate": st.get("predicate"),
         "object_text": st.get("object_text"), "subject_type": st.get("subject_type"),
         "object_type": st.get("object_type"), "doc_id": entry.get("doc_id")}
        for entry in corpus for st in entry.get("statements", []) if _is_meaningful(st)
    ]
    print("[pool]", len(pool), "утверждений")

    from application.patterns.mine_statement_patterns import target_graph_from_statements, mine_assertion_patterns
    t = time.time()
    graphs = [target_graph_from_statements(e['doc_id'], e['statements']) for e in corpus]
    print("[graphs]", round(time.time()-t, 1), "s, graphs:", len(graphs))
    t = time.time()
    pats = mine_assertion_patterns(graphs, min_support=0.15, min_size=2, max_size=6)
    print("[mine]", round(time.time()-t, 1), "s, patterns:", len(pats))

    from application.generation import run_generation
    from application.generation.provenance import LOGICAL, SYLLOGISM, THINKING
    for m in (LOGICAL, SYLLOGISM, THINKING):
        t = time.time()
        groups = run_generation(method=m, statements=pool, limit=120)
        print(f"[run_generation {m}]", round(time.time()-t, 1), "s, groups:", len(groups))

asyncio.run(main())