"""Изолированные интеграционные проверки слотов и блокировок в Neo4j."""
import copy
import json
import os
from uuid import uuid4

import pytest

from domain.article_maps import ArticleMapAccessDenied, ArticleMapBusy, ArticleMapConflict, new_result
from infrastructure.config import settings
from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository

pytestmark = pytest.mark.skipif(os.getenv("PIPELINE_NEO4J_TEST") != "1", reason="Explicit Neo4j integration opt-in")


def test_independent_slots_locks_authorization_translation_and_migration():
    repo = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    article, owner = "article-map-test-" + uuid4().hex, "article-map-test-owner"
    graph = {"schema_version": 3, "nodes": [], "edges": []}
    try:
        repo.ensure_schema()
        with repo.driver.session() as session:
            session.run("CREATE (d:Document {uid:$id,created_by_uid:$owner,deterministic_map_payload:$graph,deterministic_map_blocks_fingerprint:'legacy',deterministic_map_rebuilt_at:'2026-10-03T00:00:00+00:00'})",
                        id=article, owner=owner, graph=json.dumps(graph)).consume()
        repo.migrate_legacy_snapshots(article)
        migrated = repo.get(article, "structural_rows", owner)
        repo.migrate_legacy_snapshots()
        assert repo.get(article, "structural_rows", owner) == migrated
        repo.acquire(article, "text_reified", owner, "one")
        with pytest.raises(ArticleMapBusy):
            repo.acquire(article, "text_reified", owner, "two")
        with pytest.raises(ArticleMapConflict):
            repo.renew(article, "text_reified", owner, "wrong-token")
        with pytest.raises(ArticleMapAccessDenied):
            repo.renew(article, "text_reified", "intruder", "one")
        with repo.driver.session() as session:
            before_lease = session.run("MATCH (m:ArticleMap {article_id:$id,pipeline_id:'text_reified'}) RETURN m.lease_until AS lease",
                                      id=article).single()["lease"]
        repo.renew(article, "text_reified", owner, "one")
        with repo.driver.session() as session:
            after_lease = session.run("MATCH (m:ArticleMap {article_id:$id,pipeline_id:'text_reified'}) RETURN m.lease_until AS lease",
                                     id=article).single()["lease"]
        assert after_lease > before_lease
        # Разные пайплайны имеют независимые блокировки.
        repo.acquire(article, "structural_rows", owner, "other")
        repo.release(article, "structural_rows", owner, "other")
        with pytest.raises(ArticleMapAccessDenied):
            repo.get(article, "structural_rows", "intruder")
        result = new_result(article, "text_reified", {**graph, "schema_version": 4}, "source")
        with pytest.raises(ArticleMapConflict):
            repo.save(result, owner, "wrong-token")
        assert repo.get(article, "text_reified", owner) is None
        repo.save(result, owner, "one")
        assert repo.get(article, "structural_rows", owner) == migrated
        original = copy.deepcopy(result["graph"])
        repo.save_translation(article, "text_reified", owner, result["run_id"], {"run_id": result["run_id"], "labels": {}}, "one")
        assert repo.get(article, "text_reified", owner)["graph"] == original
        with pytest.raises(ArticleMapConflict):
            repo.save_translation(article, "text_reified", owner, "stale", {}, "one")
        repo.release(article, "text_reified", owner, "one")
        repo.acquire(article, "text_reified", owner, "next")
        # Новый контракт хранится в том же независимом слоте без миграции старых данных.
        current_graph = {"schema_version": 5, "concepts": [], "nodes": [], "edges": [],
                         "analysis": {"depth": 1, "layer_counts": {}, "knowledge_input_count": 0,
                                      "concept_count": 0, "operation_count": 0}}
        updated = new_result(article, "text_reified", current_graph, "changed", builder_version="2")
        repo.save(updated, owner, "next")
        assert len(repo.list_maps(article, owner)) == 2
        assert repo.get(article, "text_reified", owner)["run_id"] == updated["run_id"]
        assert repo.get(article, "text_reified", owner)["graph"] == current_graph
        assert repo.get(article, "text_reified", owner)["translations"] == {}
        assert repo.get(article, "structural_rows", owner) == migrated
    finally:
        with repo.driver.session() as session:
            session.run("MATCH (m:ArticleMap {article_id:$id}) DETACH DELETE m", id=article).consume()
            session.run("MATCH (d:Document {uid:$id}) DETACH DELETE d", id=article).consume()
        repo.close()
