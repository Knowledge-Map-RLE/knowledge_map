"""Проверяет сквозные связи групп, сохранность карты и возобновление без новых вызовов."""
import asyncio
import copy
import json

import pytest

from application.text_to_map import TextToMap
from domain.article_maps import ArticleMapError, prepare_source
from domain.knowledge_map import dependency_review_view, knowledge_text_keys, parse_knowledge_map
from infrastructure.reference_pilot_store import CachedStageModel, PilotStore
from tests.unit.application.test_text_to_map import Repository, Model, current_model_graph, emit


TEXT = "# Study\n\n" + " ".join(f"Observation {number:03d} was recorded." for number in range(1, 42))


def extracted():
    graph = current_model_graph()
    original = graph["nodes"][0]
    graph["nodes"] = []
    for number in range(1, 42):
        node = copy.deepcopy(original)
        node.update(id=f"N{number}", display_text=f"Observation {number:03d} was recorded")
        graph["nodes"].append(node)
    return graph


class Source:
    async def read_text(self, article, owner):
        return TEXT


def edge(source, target):
    return {"source": source, "target": target, "usage": "evidence",
            "reason": f"{target} uses the observation in {source}.", "unit_ids": ["U2"]}


class Dependencies:
    def __init__(self, second="success"):
        self.requests = []
        self.last_call = {}
        self.second = second
        self.waiting = asyncio.Event()

    async def __call__(self, system, user):
        request = json.loads(user)
        self.requests.append(request)
        self.last_call = {"model": "configured-profile", "reasoning_effort": "max",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                      "completion_tokens_details": {"reasoning_tokens": 30}}, "elapsed_seconds": 1}
        if request["completed_target_keys"]:
            if self.second == "cycle":
                return json.dumps({"dependencies": [edge("T40", "T41")]})
            if self.second == "truncated":
                raise ArticleMapError("Truncated or incomplete model response")
            if self.second == "cancel":
                self.waiting.set()
                await asyncio.Event().wait()
            return '{"dependencies":[]}'
        return json.dumps({"dependencies": [edge("T41", "T1"), edge("T1", "T40")]})


@pytest.mark.asyncio
async def test_complete_source_and_future_inputs_with_single_final_save():
    repository, dependencies, events = Repository(), Dependencies(), []
    async def track(event):
        events.append(event)
        assert "text_reified" not in repository.maps
    result = await TextToMap(repository, Source(), Model(json.dumps(extracted())), dependencies).execute(
        "article", "owner", track)
    assert len(dependencies.requests) == 2
    first, last = dependencies.requests
    assert len(first["dependency_target_keys"]) == 40
    assert last["dependency_target_keys"] == ["T41"]
    assert first["completed_target_keys"] == [] and first["accepted_dependencies"] == []
    assert set(last["completed_target_keys"]) == set(first["dependency_target_keys"])
    assert last["accepted_dependencies"] == [edge("T41", "T1"), edge("T1", "T40")]
    for request in dependencies.requests:
        assert request["article_text"] == TEXT
        assert len(request["knowledge_map"]["nodes"]) == 41
        assert request["knowledge_map"]["edges"] == []
    assert result["graph"]["edges"] == [{"source": "N41", "target": "N1"}, {"source": "N1", "target": "N40"}]
    assert result["graph"]["analysis"]["depth"] == 3
    calls = result["dependency_model_call"]
    assert calls["batch_count"] == 2 and calls["reasoning_effort"] == "max"
    assert calls["usage"]["total_tokens"] == 300 and calls["usage_complete"]
    assert calls["usage"]["completion_tokens_details"]["reasoning_tokens"] == 60
    assert [(event["processed"], event["total"]) for event in events if event["stage"] == "dependencies"] == [(0, 2), (1, 2), (2, 2)]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cycle", "truncated"])
async def test_later_failed_group_preserves_previous_map(failure):
    repository = Repository()
    repository.maps["text_reified"] = {"run_id": "previous", "graph": {"schema_version": 4}}
    before = copy.deepcopy(repository.maps)
    with pytest.raises(ArticleMapError):
        await TextToMap(repository, Source(), Model(json.dumps(extracted())), Dependencies(failure)).execute(
            "article", "owner", emit)
    assert repository.maps == before and not repository.locks


@pytest.mark.asyncio
async def test_cancel_later_group_preserves_previous_map_and_releases_lock():
    repository, dependencies = Repository(), Dependencies("cancel")
    repository.maps["text_reified"] = {"run_id": "previous"}
    before = copy.deepcopy(repository.maps)
    task = asyncio.create_task(TextToMap(repository, Source(), Model(json.dumps(extracted())), dependencies).execute(
        "article", "owner", emit))
    await dependencies.waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repository.maps == before and not repository.locks


def batch_request():
    source = prepare_source("article", TEXT)
    graph = parse_knowledge_map(json.dumps(extracted()), source)
    view = dependency_review_view(graph)
    return {"article_id": "article", "article_text": TEXT, "source_units": source["units"],
        "knowledge_map": view, "knowledge_text_keys": knowledge_text_keys(view["nodes"]),
        "accepted_dependencies": [edge("T41", "T1"), edge("T1", "T40")],
        "completed_target_keys": [f"T{i}" for i in range(1, 41)], "dependency_target_keys": ["T41"]}


class Gateway(Dependencies):
    model, provider, context_length, max_tokens, timeout = "configured", "test", 100000, 10000, 60
    reasoning_effort, url, strict_schema, output_schema = "max", "http://configured-service", True, None


@pytest.mark.asyncio
async def test_scoped_checkpoint_reuses_exact_prefix_and_rejects_cross_group_cycle(tmp_path):
    store, gateway = PilotStore(tmp_path), Gateway()
    request = batch_request()
    raw = json.dumps(request)
    first = CachedStageModel(gateway, store, TEXT, stage="dependencies")
    assert await first("prompt", raw) == '{"dependencies":[]}'
    assert await CachedStageModel(gateway, store, TEXT, stage="dependencies")("prompt", raw) == '{"dependencies":[]}'
    assert len(gateway.requests) == 1
    changed = copy.deepcopy(request)
    changed["accepted_dependencies"] = [edge("T41", "T1")]
    await CachedStageModel(gateway, store, TEXT, stage="dependencies")("prompt", json.dumps(changed))
    assert len(gateway.requests) == 2
    gateway.second = "cycle"
    changed["knowledge_text_keys"] = dict(reversed(list(changed["knowledge_text_keys"].items())))
    changed["accepted_dependencies"] = request["accepted_dependencies"]
    with pytest.raises(ArticleMapError, match="cycle"):
        await CachedStageModel(gateway, store, TEXT, stage="dependencies")("prompt", json.dumps(changed))
    assert len(gateway.requests) == 3
    assert store.read("cost_ledger.json")["attempts"][-1]["validated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [
    lambda request: request.update(completed_target_keys=["T1"]),
    lambda request: request.update(dependency_target_keys=["T1"]),
    lambda request: request["accepted_dependencies"].append(edge("T1", "unknown")),
])
async def test_checkpoint_rejects_inconsistent_completed_scope(tmp_path, mutation):
    request = batch_request()
    mutation(request)
    with pytest.raises(ArticleMapError):
        await CachedStageModel(Gateway(), PilotStore(tmp_path), TEXT, stage="dependencies")("prompt", json.dumps(request))
