"""Benchmark: measure pipeline throughput & per-stage timing."""

from __future__ import annotations

import asyncio
import time
import logging
from pathlib import Path

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.services.pipeline import Pipeline
from src.parser.dep_tree import DependencyTree
from src.parser.nlp_client import NLPClient
from src.extractor.engine import RuleEngine
from src.extractor.context import ExtractionContext

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

DATA_ARTICLES = Path(__file__).resolve().parent.parent.parent.parent / "data" / "articles"

ARTICLES = [
    "The hallmarks of Parkinson's disease",
    "Hallmarks of cancer and hallmarks of aging",
]

def load_article_text(article_name: str) -> str:
    for d in DATA_ARTICLES.iterdir():
        if not d.is_dir():
            continue
        norm = d.name.lower().replace("'", "").replace("’", "").replace("  ", " ")
        if article_name.lower().replace("'", "").replace("’", "") in norm:
            md = sorted(d.glob("*.md"))
            for f in md:
                if "rus" in f.name:
                    continue
                text = f.read_text(encoding="utf-8")
                # strip frontmatter
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        text = text[end + 3:]
                # Remove references section
                ref_idx = text.find("## References")
                if ref_idx != -1:
                    text = text[:ref_idx]
                return text.strip()
    raise FileNotFoundError(f"Article {article_name} not found")


async def benchmark_full_article(article_name: str, pipeline: Pipeline) -> dict:
    """Measure pipeline on full article text (production mode)."""
    text = load_article_text(article_name)
    print(f"\n{'='*60}")
    print(f"ARTICLE: {article_name}")
    print(f"  Text length: {len(text)} chars")

    t0 = time.perf_counter()
    result = await pipeline.process(text, doc_id="benchmark")
    total = time.perf_counter() - t0

    n_statements = result.get("total_statements", 0)
    n_concepts = result.get("total_concepts", 0)
    print(f"  Statements: {n_statements}, Concepts: {n_concepts}")
    print(f"  TOTAL TIME: {total:.3f}s ({total*1000:.0f}ms)")

    return {
        "article": article_name,
        "total_seconds": total,
        "statements": n_statements,
        "concepts": n_concepts,
    }


async def benchmark_stages(article_name: str, pipeline: Pipeline) -> dict:
    """Measure each stage of the pipeline individually."""
    text = load_article_text(article_name)

    # 1. Preprocess
    t0 = time.perf_counter()
    cleaned = pipeline._preprocess_text(text)
    t_pre = time.perf_counter() - t0

    # 2. NLP (dependency trees)
    t0 = time.perf_counter()
    trees = await pipeline._get_dependency_trees(cleaned)
    t_nlp = time.perf_counter() - t0

    print(f"  Sentences: {len(trees)}")

    # 3. Rule engine per sentence
    all_statements: list[Statement] = []
    concepts: dict[str, Concept] = {}
    t0 = time.perf_counter()
    for tree in trees:
        sentence_text = tree.root and tree.subtree_text(tree.root.idx) or ""
        if not sentence_text:
            continue
        ctx = ExtractionContext(
            sentence_text=sentence_text,
            existing_concepts=concepts,
            doc_id="benchmark",
        )
        statements = pipeline._engine.process_sentence(tree, ctx)
        all_statements.extend(statements)
    t_rules = time.perf_counter() - t0
    n_rules_statements = len(all_statements)

    # 4. Normalize
    t0 = time.perf_counter()
    pipeline._normalize_concepts(all_statements, concepts)
    t_norm = time.perf_counter() - t0

    # 5. Validate
    t0 = time.perf_counter()
    validated, errors = pipeline._validator.validate(all_statements)
    t_val = time.perf_counter() - t0

    # 6. Meta
    t0 = time.perf_counter()
    all_statements, concepts = pipeline._meta.process(all_statements, concepts, {"doc_id": "benchmark"})
    t_meta = time.perf_counter() - t0

    # 7. Serialize
    t0 = time.perf_counter()
    stmt_protos, concept_protos = pipeline._serializer.to_proto(all_statements, concepts)
    t_ser = time.perf_counter() - t0

    total = t_pre + t_nlp + t_rules + t_norm + t_val + t_meta + t_ser

    print(f"\n  STAGE TIMING:")
    print(f"    Preprocess:  {t_pre*1000:7.1f}ms")
    print(f"    NLP (gRPC):  {t_nlp*1000:7.1f}ms  ({len(trees)} sentences)")
    print(f"    RuleEngine:  {t_rules*1000:7.1f}ms  ({n_rules_statements} statements)")
    print(f"    Normalize:   {t_norm*1000:7.1f}ms")
    print(f"    Validate:    {t_val*1000:7.1f}ms")
    print(f"    MetaBuilder: {t_meta*1000:7.1f}ms  ({len(all_statements)} total)")
    print(f"    Serialize:   {t_ser*1000:7.1f}ms")
    print(f"    {'-'*30}")
    print(f"    TOTAL:       {total*1000:7.1f}ms")

    return {
        "article": article_name,
        "preprocess_seconds": t_pre,
        "nlp_seconds": t_nlp,
        "rules_seconds": t_rules,
        "normalize_seconds": t_norm,
        "validate_seconds": t_val,
        "meta_seconds": t_meta,
        "serialize_seconds": t_ser,
        "total_seconds": total,
        "sentences": len(trees),
        "rule_statements": n_rules_statements,
        "total_statements": len(all_statements),
    }


async def main():
    print("=" * 60)
    print("KNOWLEDGE MAP PIPELINE BENCHMARK")
    print("=" * 60)

    pipeline = Pipeline()

    for article in ARTICLES:
        # Full pipeline (production mode)
        await benchmark_full_article(article, pipeline)

        # Per-stage breakdown
        await benchmark_stages(article, pipeline)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
