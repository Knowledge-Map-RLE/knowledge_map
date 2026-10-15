"""История, происхождение, права доступа и независимость русского отображения."""
import copy

import pytest
from fastapi import HTTPException

from application.publish_article_map import russian_translation
from domain.article_maps import ArticleMapAccessDenied
from tests.unit.application.test_knowledge_development import SOURCE, extracted, knowledge, reviewed, transition
from web.routers import article_maps as routes


class Repository:
    def __init__(self):
        graph = reviewed(extracted(knowledge(1), knowledge(2), knowledge(3)),
                         [transition("T1", ["B1", "B2"], "B3")])
        self.value = {"article_id": "article", "pipeline_id": "text_reified", "run_id": "historic",
                      "graph": graph, "source": SOURCE, "translations": {"ru": russian_translation(
                          graph, {"K1": "Первое", "K2": "Второе", "K3": "Заключение"}, "historic", {"kind": "codex_manual"})}}
        self.calls = []

    def get(self, article, pipeline, owner, run_id=None):
        if owner != "owner":
            raise ArticleMapAccessDenied("Article belongs to another user")
        self.calls.append((article, pipeline, owner, run_id))
        return copy.deepcopy(self.value) if run_id in (None, "historic") else None


@pytest.mark.asyncio
async def test_historical_translation_changes_only_display_text():
    repo = Repository()
    before = copy.deepcopy(repo.value)
    ru = await routes.get_map("article", "text_reified", "ru", "historic", {"uid": "owner"}, repo)
    assert ru["graph"]["nodes"][0]["display_text"] == "Первое"
    assert ru["graph"]["knowledge"] == before["graph"]["knowledge"]
    assert ru["graph"]["edges"] == before["graph"]["edges"]
    assert repo.value == before and "source" not in ru
    assert repo.calls[-1][-1] == "historic"


@pytest.mark.asyncio
async def test_historical_block_and_joint_transition_provenance():
    repo = Repository()
    node = await routes.provenance("article", "text_reified", "B3", "historic", {"uid": "owner"}, repo)
    assert node["knowledge"]["knowledge_id"] == "K3"
    assert node["run_id"] == "historic" and node["offset_encoding"] == "unicode_codepoints"
    for fragment in node["fragments"]:
        assert fragment["text"] == SOURCE["text"][fragment["start"]:fragment["end"]]
    edge = await routes.transition_details("article", "text_reified", "T1", "historic", {"uid": "owner"}, repo)
    assert edge["transition"]["sources"] == ["B1", "B2"]
    assert edge["source_sha256"] == SOURCE["sha256"]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["map", "node", "transition"])
async def test_history_and_provenance_enforce_article_owner(endpoint):
    repo = Repository()
    with pytest.raises(HTTPException) as error:
        if endpoint == "map":
            await routes.get_map("article", "text_reified", "en", "historic", {"uid": "intruder"}, repo)
        elif endpoint == "node":
            await routes.provenance("article", "text_reified", "B1", "historic", {"uid": "intruder"}, repo)
        else:
            await routes.transition_details("article", "text_reified", "T1", "historic", {"uid": "intruder"}, repo)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_run_never_returns_current_map():
    with pytest.raises(HTTPException) as error:
        await routes.get_map("article", "text_reified", "en", "missing", {"uid": "owner"}, Repository())
    assert error.value.status_code == 404
