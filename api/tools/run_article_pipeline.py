"""Full English article acceptance run. Uses configured services, never a mock/fallback."""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
from pathlib import Path
from infrastructure.config import model_registry, resolve_model_profile, settings
from infrastructure.article_pipeline import LinguisticGateway, SemanticGateway
from infrastructure.neo4j.article_pipeline_repository import Neo4jArticlePipelineRepository
from knowledge_pipeline import ArticlePipeline
from knowledge_pipeline.pipeline import uid, checksum
from knowledge_contracts.validation import require, validate_linguistic, validate_map, validate_structural

ROOT = Path(__file__).resolve().parents[2]
ARTICLE = ROOT / "data/articles/Immunometabolic resistors of aging in long-lived golden spiny mice/Immunometabolic resistors of aging in long-lived golden spiny mice.md"
REFERENCE = ARTICLE.with_name("knowledge_map_assertions_acomys.md")


def finalize(repo, doc_id, result, actor, output):
    """Persist a completed extraction, prove the Neo4j roundtrip, emit acceptance artifacts."""
    repo.save(result, actor)
    loaded = repo.load(doc_id, result["version_id"], actor)
    assert result == loaded, "DB roundtrip changed extraction artifacts"
    repo.save(loaded, actor)
    assert repo.load(doc_id, result["version_id"], actor) == loaded
    assert result == loaded, "DB roundtrip changed extraction artifacts (idempotent save)"
    profile = loaded["linguistic_profile"]
    validate_linguistic(profile, loaded["source"])
    validate_structural(loaded["blocks"], loaded["source"], profile["sentences"])
    validate_map(loaded["graph"], loaded["blocks"])
    # Reference is accessed only after extraction, never passed to the model.
    reference = REFERENCE.read_text(encoding="utf-8")
    blocks = result["blocks"]
    schema_issues = sorted({
        field for block in blocks
        for field in ((block["data"].get("_extra") or {}).keys())})
    usage = [step.get("model_call", {}).get("usage", {}) for step in result.get("model_steps", [])]
    report = {"article": str(ARTICLE), "source_sha256": checksum(result["source"]["text"]),
              "source_characters": len(result["source"]["text"]),
              "references_removed": result.get("processing", {}).get("references_removed"),
              "article_id": doc_id, "version_id": result["version_id"],
              "model": result.get("model", ""),
              "execution": result["execution"], "timing": result.get("timing", {}),
              "roundtrip": "passed", "idempotent_save": "passed",
              "coverage": result["coverage"], "quality_metrics": result["quality_metrics"],
              "model_steps_checksum": checksum(json.dumps(result["model_steps"], sort_keys=True)),
              "usage": usage,
              "schema_issues": schema_issues,
              "sections": [s["title"] for s in profile["sections"]],
              "blocks": len(blocks),
              "relations": sum(b["blockType"] in ("relation", "temporal_relation") for b in blocks),
              "graph_nodes": len(result["graph"]["nodes"]),
              "graph_edges": len(result["graph"].get("semantic_edges", []))
                           + len(result["graph"].get("dependency_edges", [])),
              "dedup": result["quality_metrics"]["structural_rows"]["duplicate_fingerprint_candidates"],
              "reference_assertions": sum(line.startswith("S") and ": " in line
                                          for line in reference.splitlines()),
              "semantic_comparison": "Manual semantic assessment required; reference is Russian, source and output are English."}
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "map.md").write_text(
        "\n".join(n["display_text"] for n in result["graph"]["nodes"]), encoding="utf-8")
    (output / "structural.json").write_text(
        json.dumps(result["blocks"], ensure_ascii=False, indent=2), encoding="utf-8")
    print("ACCEPTANCE_DB_ROUNDTRIP_PASSED", flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/pipeline_runs/acomys-cloudru")
    parser.add_argument("--batch", type=int, default=None,
                        help="Sentence batch size (local profiles only; OpenAI Responses receives the whole article)")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--finalize", action="store_true",
                        help="Persist a fully computed checkpoint whose DB save failed earlier; no model call")
    args = parser.parse_args()
    extraction_profile = model_registry.profile(
        resolve_model_profile("article_extraction")
    )
    is_responses_provider = extraction_profile.provider.kind == "openai_responses"
    if is_responses_provider and args.batch is not None:
        parser.error("--batch is not supported for OpenAI Responses profiles; the whole article is sent in one call")
    if args.batch is not None and args.batch <= 0:
        parser.error("--batch must be a positive integer")
    batch_sentences = (
        None if is_responses_provider
        else args.batch if args.batch is not None
        else 100
    )
    args.output.mkdir(parents=True, exist_ok=True)
    text = ARTICLE.read_bytes().decode("utf-8")
    repo = Neo4jArticlePipelineRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    repo.ensure_indexes()
    actor = "pipeline-acceptance"
    doc_id = "acceptance-acomys-" + uid()
    checkpoint_path = args.output / "checkpoint.json"
    latest = {}
    if args.resume:
        latest = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        doc_id = latest["article_id"]
    with repo.driver.session() as session:
        session.run("""MERGE (d:Document {uid:$id}) ON CREATE SET
            d.title='Acomys English pipeline acceptance',d.original_filename=$filename,
            d.created_by_uid=$actor,d.md5_hash=$id,d.s3_key='',d.processing_status='ready_for_annotation',
            d.pipeline_acceptance=true""", id=doc_id, actor=actor, filename=ARTICLE.name).consume()
    async def checkpoint(result):
        nonlocal latest
        latest = result
        await asyncio.to_thread(repo.save, result, actor)
        temporary = checkpoint_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(checkpoint_path)
        print(json.dumps({k: result.get(k)
                          for k in ("run_id", "version_id", "stage", "status", "processed", "total")}),
              flush=True)
    if args.finalize:
        completed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        require(completed.get("stage") == "complete" and "blocks" in completed and "graph" in completed
                and "quality_metrics" in completed, "Checkpoint holds no completed extraction")
        completed.update(status="completed", success=True)
        completed.pop("error", None)
        print(json.dumps({"run_id": completed.get("run_id"), "version_id": completed.get("version_id"),
                          "stage": "finalize", "status": "running"}), flush=True)
        finalize(repo, completed["article_id"], completed, actor, args.output)
        return
    try:
        result = await ArticlePipeline(LinguisticGateway(), SemanticGateway(),
                                       batch_sentences=batch_sentences).run(
            doc_id, text, checkpoint, resume=latest if args.resume else None)
        if not result.get("success"):
            coverage = result.get("coverage", {})
            uncovered = coverage.get("uncovered_sentence_ids", [])
            print(f"ACCEPTANCE_COVERAGE_FAILED uncovered={len(uncovered)}", flush=True)
            if uncovered:
                print(" ".join(uncovered[:200]), flush=True)
            raise SystemExit(1)
        finalize(repo, doc_id, result, actor, args.output)
    except BaseException as exc:
        if not isinstance(exc, SystemExit) and latest:
            latest.update(status="failed", error=str(exc), success=False)
            await checkpoint(latest)
            completed = len(latest.get("model_steps", []))
            total = latest.get("total")
            if completed or total:
                print(f"ACCEPTANCE_BATCH_PROGRESS completed_batches={completed}"
                      f" total_batches={total} — resume with --resume", flush=True)
        raise
    finally:
        repo.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
