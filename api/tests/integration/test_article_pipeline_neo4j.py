"""Neo4j integration: isolated identifiers, real transactions, no model calls."""
import copy
import os
import uuid
import pytest
from infrastructure.config import settings
from infrastructure.neo4j.article_pipeline_repository import Neo4jArticlePipelineRepository
from knowledge_pipeline.pipeline import source_revision
from knowledge_pipeline.knowledge_map_builder import build_knowledge_map
from knowledge_contracts.validation import ValidationError
from tests.unit.application.test_article_pipeline import build_blocks, document, TEXT

pytestmark = pytest.mark.skipif(os.getenv("PIPELINE_NEO4J_TEST") != "1",
                                reason="Explicit Neo4j integration opt-in")

def test_roundtrip_typed_edges_activation_and_rollback():
    repo = Neo4jArticlePipelineRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    article = "pipeline-test-" + str(uuid.uuid4()); actor = "pipeline-integration"
    source, profile, blocks = build_blocks()
    result = {"article_id": article, "run_id": str(uuid.uuid4()), "version_id": str(uuid.uuid4()),
              "source": source, "linguistic_profile": profile, "blocks": blocks,
              "graph": build_knowledge_map(blocks),
              "status": "completed", "stage": "complete", "success": True, "schemaVersion": 2,
              "coverage": {"token_preservation": 1.0, "semantic_token_fraction": 1.0},
              "validation": {"linguistic": "passed", "structural": "passed", "map": "passed"},
              "quality_metrics": {"version": 3}}
    ids = [article, source["id"], result["version_id"]] + [b["instanceId"] for b in blocks]
    try:
        repo.ensure_indexes()
        with repo.driver.session() as s:
            s.run("CREATE (d:Document {uid:$id,created_by_uid:$actor,current_source_hash:$hash})",
                  id=article, actor=actor, hash=source["sha256"]).consume()
        repo.save(result, actor)
        assert repo.load(article, result["version_id"], actor) == result
        repo.save(result, actor)  # idempotent completed-version save
        with repo.driver.session() as s:
            paths = s.run("""MATCH (:ArticlePipelineRun {uid:$v})-[:HAS_BLOCK]->(b)
              MATCH (b)-[:SOURCE_SPAN]->(:SourceSpan)-[:IN_REVISION]->(:SourceRevision)
              RETURN count(DISTINCT b) AS n""", v=result["version_id"]).single()["n"]
            assert paths == len(blocks)
            map_rows = s.run("MATCH (v:ArticlePipelineRun {uid:$v}) RETURN v.map_payload AS m",
                             v=result["version_id"]).single()
            assert map_rows["m"] is not None
        with pytest.raises(ValidationError, match="access"):
            repo.load(article, result["version_id"], "another-user")
        with pytest.raises(ValidationError, match="Source changed"):
            repo.apply(article, result["version_id"], actor, "stale")
        assert not any(v["active"] for v in repo.versions(article, actor))
        repo.apply(article, result["version_id"], actor, source["sha256"])
        repo.apply(article, result["version_id"], actor, source["sha256"])
        assert repo.versions(article, actor)[0]["active"]
        broken = copy.deepcopy(result)
        broken["graph"]["nodes"].pop()
        with pytest.raises(ValidationError):
            repo.save(broken, actor)
        assert repo.load(article, result["version_id"], actor) == result
    finally:
        for label in ("Document", "ArticlePipelineRun", "SourceRevision", "SourceSpan", "ArticleBlock"):
            with repo.driver.session() as cleanup:
                cleanup.run(f"MATCH (n:{label}) WHERE n.uid IN $ids DETACH DELETE n",
                            ids=ids).consume()
        repo.close()