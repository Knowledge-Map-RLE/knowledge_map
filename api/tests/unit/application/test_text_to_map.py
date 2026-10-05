"""Проверки реификации, потери смысла, отмены и независимого сохранения."""
import asyncio
import copy
import json
import re
import threading

import pytest

from application.text_to_map import DEPENDENCY_PROMPT_PATH, PROMPT_PATH, TextToMap, TranslateArticleMap
from application.article_map_lock import acquire_map_lock
from domain.article_maps import ArticleMapError, ArticleMapBusy, parse_model_map, prepare_source
from domain.knowledge_map import knowledge_text_keys

TEXT = "# Biology\n\nTrees are living objects. Some treated mice did not develop fibrosis.\n\n## References\n\nExample citation."


def node(identifier, text, kind="concept", roles=None, predicate=None):
    return {"id": identifier, "kind": kind, "display_text": text, "aliases": [],
            "semantic": {"predicate": predicate, "roles": roles or [], "quantifier": None,
                         "modality": None, "negated": False, "conditions": [],
                         "temporal_context": None, "qualifiers": {}}, "provenance": {"unit_ids": ["U2"]}}


def model_graph():
    return {"schema_version": 4, "nodes": [node("N1", "Trees"), node("N2", "Living objects", "class"),
            node("N3", "Trees are living objects", "assertion", [{"role": "subject", "node_id": "N1"},
                 {"role": "class", "node_id": "N2"}], "are")],
            "edges": [{"source": "N1", "target": "N3"}, {"source": "N2", "target": "N3"}]}


def current_model_graph():
    legacy = model_graph()
    claim = copy.deepcopy(legacy["nodes"][2])
    claim["semantic"]["inputs"] = []
    claim["semantic"]["qualifiers"] = {"attributes": []}
    for role in claim["semantic"]["roles"]:
        role["concept_id"], role["node_id"] = "C" + role["node_id"][1:], None
    return {"schema_version": 5, "concepts": [
        {"id": "C" + n["id"][1:], "display_text": n["display_text"], "aliases": n["aliases"],
         "provenance": n["provenance"]} for n in legacy["nodes"][:2]], "nodes": [claim], "edges": []}


class Repository:
    def __init__(self):
        self.maps = {"structural_rows": {"graph": {"schema_version": 3}}}
        self.locks = {}

    def acquire(self, article, pipeline, user, token):
        if pipeline in self.locks:
            raise ArticleMapBusy("Already running")
        self.locks[pipeline] = token

    def release(self, article, pipeline, user, token):
        if self.locks.get(pipeline) == token:
            del self.locks[pipeline]

    def renew(self, article, pipeline, user, token):
        assert self.locks[pipeline] == token

    def save(self, result, user, token):
        assert self.locks[result["pipeline_id"]] == token
        self.maps[result["pipeline_id"]] = copy.deepcopy(result)

    def get(self, article, pipeline, user):
        return copy.deepcopy(self.maps.get(pipeline))

    def save_translation(self, article, pipeline, user, run_id, translation, token):
        assert self.maps[pipeline]["run_id"] == run_id
        self.maps[pipeline]["translations"]["ru"] = translation


class Source:
    async def read_text(self, article, user):
        return TEXT


class Model:
    last_call = {"model": "configured-profile"}

    def __init__(self, raw=None):
        self.raw = raw if raw is not None else json.dumps(current_model_graph())
        self.calls = []

    async def __call__(self, system, user):
        self.calls.append((system, json.loads(user)))
        return self.raw


class DependencyModel(Model):
    def __init__(self, raw=None):
        super().__init__(raw if raw is not None else '{"dependencies":[]}')


async def emit(_event):
    pass


def test_complete_english_prompt_and_source_coordinates():
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    assert re.findall(r"(?m)^(\d+)\.", prompt) == [str(i) for i in range(1, 146)]
    assert not re.search(r"[А-Яа-яЁё]", prompt)
    assert "Version: 2" in prompt
    assert "DECLARES the immediate dependency" not in prompt
    assert "Leave semantic.inputs=[] on EVERY node and edges=[]" in prompt
    assert not re.search(r"[А-Яа-яЁё]", DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8"))
    api_root = PROMPT_PATH.parents[1]
    dockerignore = (api_root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for path in (PROMPT_PATH, DEPENDENCY_PROMPT_PATH):
        assert "!" + path.relative_to(api_root).as_posix() in dockerignore
    source = prepare_source("article", TEXT.replace("Trees", "Trees 🌳"))
    assert source["text"].endswith("Example citation.")
    assert source["references_excluded"]
    for unit in source["units"]:
        assert source["text"][unit["start"]:unit["end"]] == unit["text"]
        assert "Example citation" not in unit["text"]


def test_reification_and_server_ranks():
    graph = parse_model_map(json.dumps(model_graph()), prepare_source("article", TEXT))
    assert [n["rank"] for n in graph["nodes"]] == [0, 0, 1]
    assert graph["nodes"][2]["display_text"] == "Trees are living objects"
    assert graph["nodes"][2]["provenance"]["source_spans"]
    assert all(set(e) == {"source", "target"} for e in graph["edges"])


def test_real_world_feedback_is_two_reified_assertions_not_a_graph_cycle():
    roles = [{"role": "cause", "node_id": "A"}, {"role": "effect", "node_id": "B"}]
    graph = {"schema_version": 4, "nodes": [node("A", "Process A"), node("B", "Process B"),
             node("K1", "Process A causes process B", "assertion", roles, "causes"),
             node("K2", "Process B causes process A", "assertion", [
                 {"role": "cause", "node_id": "B"}, {"role": "effect", "node_id": "A"}], "causes")],
             "edges": [{"source": i, "target": k} for i in ("A", "B") for k in ("K1", "K2")]}
    source = prepare_source("article", "# Feedback\n\nProcess A causes process B, and process B causes process A.")
    validated = parse_model_map(json.dumps(graph), source)
    assert [n["rank"] for n in validated["nodes"]] == [0, 0, 1, 1]


def test_quantifiers_negation_modality_context_aliases_and_actions_are_preserved():
    graph = model_graph()
    graph["nodes"][0].update(display_text="Treated mice", aliases=["Experimental mice"])
    graph["nodes"][1].update(display_text="Fibrosis", kind="property")
    assertion = graph["nodes"][2]
    assertion["display_text"] = "Some treated mice may not develop fibrosis at six months"
    assertion["semantic"].update(predicate="develop", quantifier="some", negated=True, modality="may",
                                  temporal_context="at six months", conditions=["after treatment"],
                                  qualifiers={"sample_size": 12, "age_unit": "months"})
    assertion["semantic"]["roles"][1]["role"] = "outcome"
    action = node("N4", "Assess fibrosis after treatment", "action",
                  [{"role": "knowledge", "node_id": "N3"}], "assess")
    graph["nodes"].append(action)
    graph["edges"].append({"source": "N3", "target": "N4"})
    source_text = ("# Study\n\nSome treated mice (experimental mice) in a group of n=12 may not develop fibrosis at six months "
                   "after treatment. Assess fibrosis after treatment using this observation.")
    validated = parse_model_map(json.dumps(graph), prepare_source("article", source_text))
    assert validated["nodes"][2]["semantic"] == assertion["semantic"]
    assert validated["nodes"][0]["aliases"] == ["Experimental mice"]
    assert validated["nodes"][3]["rank"] == 2


@pytest.mark.parametrize("mutation", [
    lambda g: g["edges"].append({"source": "N3", "target": "N1"}),
    lambda g: g["edges"].append({"source": "unknown", "target": "N3"}),
    lambda g: g["edges"][0].update(type="is_a"),
    lambda g: g["nodes"][1].update(display_text="Trees"),
    lambda g: g["nodes"][0]["provenance"].update(unit_ids=["U999"]),
    lambda g: g["edges"].append(dict(g["edges"][0])),
    lambda g: g["nodes"][2]["semantic"]["roles"][0].update(node_id="unknown"),
    lambda g: g["nodes"][0]["semantic"].pop("modality"),
])
def test_reject_invalid_graph(mutation):
    graph = model_graph()
    mutation(graph)
    with pytest.raises(ArticleMapError):
        parse_model_map(json.dumps(graph), prepare_source("article", TEXT))


def test_materializes_dependencies_from_complete_semantic_roles():
    graph = model_graph()
    graph["edges"] = []
    validated = parse_model_map(json.dumps(graph), prepare_source("article", TEXT))
    assert validated["edges"] == [{"source": "N1", "target": "N3"}, {"source": "N2", "target": "N3"}]
    assert validated["nodes"][2]["rank"] == 1
    assert graph["edges"] == []


def test_rejects_cycle_declared_only_through_semantic_roles():
    graph = model_graph()
    graph["edges"] = []
    graph["nodes"][0]["semantic"]["roles"] = [{"role": "input", "node_id": "N3"}]
    with pytest.raises(ArticleMapError, match="cycle"):
        parse_model_map(json.dumps(graph), prepare_source("article", TEXT))


@pytest.mark.parametrize("raw", ['{"schema_version":4,', '```json\n{}\n```', '{"nodes":[],"nodes":[]}'])
def test_reject_incomplete_or_ambiguous_json(raw):
    with pytest.raises(ArticleMapError):
        parse_model_map(raw, prepare_source("article", TEXT))


@pytest.mark.asyncio
async def test_success_does_not_modify_structural_map_and_replaces_own_result():
    repo, model = Repository(), Model()
    old = copy.deepcopy(repo.maps["structural_rows"])
    dependencies = DependencyModel()
    usecase = TextToMap(repo, Source(), model, dependencies)
    first = await usecase.execute("article", "owner", emit)
    second = await usecase.execute("article", "owner", emit)
    assert repo.maps["structural_rows"] == old
    assert repo.maps["text_reified"]["run_id"] == second["run_id"] != first["run_id"]
    assert "Example citation" not in model.calls[0][1]["article_text"]
    assert repo.maps["text_reified"]["source"]["text"] == TEXT
    assert model.calls[0][1]["article_text"] == dependencies.calls[0][1]["article_text"]
    assert dependencies.calls[0][1]["knowledge_map"]["schema_version"] == 5
    dependency_request = dependencies.calls[0][1]
    assert dependency_request["knowledge_text_keys"] == knowledge_text_keys(dependency_request["knowledge_map"]["nodes"])
    assert second["graph_schema_version"] == 5 and second["builder_version"] == "2"
    assert second["prompt"]["version"] == "2" and second["dependency_prompt"]["sha256"]
    assert second["dependency_prompt"]["version"] == "14"
    assert second["validation"]["dependency_review"] == "passed"
    assert not repo.locks


@pytest.mark.asyncio
async def test_failed_conversion_keeps_previous_success():
    repo = Repository()
    await TextToMap(repo, Source(), Model(), DependencyModel()).execute("article", "owner", emit)
    before = copy.deepcopy(repo.maps)
    with pytest.raises(ArticleMapError):
        await TextToMap(repo, Source(), Model("incomplete"), DependencyModel()).execute("article", "owner", emit)
    assert repo.maps == before
    assert not repo.locks


@pytest.mark.asyncio
async def test_source_change_rejects_result():
    class ChangingSource(Source):
        reads = 0
        async def read_text(self, article, user):
            self.reads += 1
            return TEXT if self.reads == 1 else TEXT + "Changed"
    repo = Repository()
    with pytest.raises(ArticleMapError, match="changed"):
        await TextToMap(repo, ChangingSource(), Model(), DependencyModel()).execute("article", "owner", emit)
    assert "text_reified" not in repo.maps


@pytest.mark.asyncio
async def test_cancel_releases_lock_without_saving():
    started = asyncio.Event()
    class WaitingModel(Model):
        async def __call__(self, system, user):
            started.set()
            await asyncio.Event().wait()
    repo = Repository()
    task = asyncio.create_task(TextToMap(repo, Source(), WaitingModel(), DependencyModel()).execute("article", "owner", emit))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "text_reified" not in repo.maps
    assert not repo.locks


@pytest.mark.asyncio
async def test_cancel_during_driver_lock_acquisition_does_not_leak_lock():
    entered, proceed = threading.Event(), threading.Event()
    class SlowRepository(Repository):
        def acquire(self, article, pipeline, user, token):
            entered.set()
            assert proceed.wait(5)
            super().acquire(article, pipeline, user, token)
    repo = SlowRepository()
    task = asyncio.create_task(acquire_map_lock(repo, "article", "text_reified", "owner", "token"))
    await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    proceed.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not repo.locks


@pytest.mark.asyncio
async def test_translation_only_adds_sidecar_and_rejects_changed_ids():
    repo = Repository()
    await TextToMap(repo, Source(), Model(), DependencyModel()).execute("article", "owner", emit)
    original = copy.deepcopy(repo.maps["text_reified"]["graph"])
    await TranslateArticleMap(repo, Model(json.dumps({"N3": "Деревья — живые объекты"}))).execute("article", "text_reified", "owner")
    assert repo.maps["text_reified"]["graph"] == original
    repo.maps["text_reified"]["translations"] = {}
    with pytest.raises(ArticleMapError, match="ids changed"):
        await TranslateArticleMap(repo, Model('{"other":"Другое"}')).execute("article", "text_reified", "owner")


@pytest.mark.asyncio
async def test_failed_dependency_review_keeps_previous_schema_four_success():
    repo = Repository()
    repo.maps["text_reified"] = {"graph": model_graph(), "run_id": "previous-v1", "translations": {}}
    before = copy.deepcopy(repo.maps)
    with pytest.raises(ArticleMapError):
        await TextToMap(repo, Source(), Model(), DependencyModel('{"dependencies":[')).execute("article", "owner", emit)
    assert repo.maps == before
    assert not repo.locks


@pytest.mark.asyncio
async def test_cancel_during_dependency_review_keeps_previous_map_and_releases_lock():
    entered = asyncio.Event()
    class WaitingDependencies(DependencyModel):
        async def __call__(self, system, user):
            entered.set()
            await asyncio.Event().wait()
    repo = Repository()
    repo.maps["text_reified"] = {"graph": model_graph(), "run_id": "previous-v1"}
    before = copy.deepcopy(repo.maps)
    task = asyncio.create_task(TextToMap(repo, Source(), Model(), WaitingDependencies()).execute("article", "owner", emit))
    await entered.wait()
    with pytest.raises(ArticleMapBusy):
        await TextToMap(repo, Source(), Model(), DependencyModel()).execute("article", "owner", emit)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.maps == before
    assert not repo.locks


@pytest.mark.asyncio
async def test_live_pipeline_rejects_schema_four_without_switching_to_legacy_builder():
    repo, dependencies = Repository(), DependencyModel()
    with pytest.raises(ArticleMapError, match="knowledge graph fields"):
        await TextToMap(repo, Source(), Model(json.dumps(model_graph())), dependencies).execute("article", "owner", emit)
    assert not dependencies.calls
    assert "text_reified" not in repo.maps


@pytest.mark.asyncio
async def test_extraction_cannot_skip_stage_boundary_with_early_dependencies():
    candidate = current_model_graph()
    second = copy.deepcopy(candidate["nodes"][0])
    second.update(id="N4", display_text="The source applies its classification of trees")
    second["semantic"]["inputs"] = [{"node_id": "N3", "usage": "premise",
        "reason": "The classification is used in the stated application.",
        "unit_ids": list(candidate["nodes"][0]["provenance"]["unit_ids"])}]
    candidate["nodes"].append(second)
    candidate["edges"] = [{"source": "N3", "target": "N4"}]
    repo, dependencies = Repository(), DependencyModel()
    repo.maps["text_reified"] = {"graph": model_graph(), "run_id": "previous-v1"}
    before = copy.deepcopy(repo.maps)
    with pytest.raises(ArticleMapError, match="Extraction stage"):
        await TextToMap(repo, Source(), Model(json.dumps(candidate)), dependencies).execute("article", "owner", emit)
    assert not dependencies.calls
    assert repo.maps == before
    assert not repo.locks


def test_rejects_unrelated_concept_inventory_without_reified_knowledge():
    from domain.article_maps import ArticleMapError, prepare_source, validate_reified_map
    source = prepare_source("article", "Trees are living objects.")
    nodes = [{"id": identifier, "kind": "concept", "display_text": label, "aliases": [],
              "semantic": {"predicate": None, "roles": [], "quantifier": None, "modality": None,
                           "negated": False, "conditions": [], "temporal_context": None, "qualifiers": {}},
              "provenance": {"unit_ids": ["U1"]}}
             for identifier, label in [("N1", "Trees"), ("N2", "Living objects")]]
    with pytest.raises(ArticleMapError, match="isolated concept inventory"):
        validate_reified_map({"schema_version": 4, "nodes": nodes, "edges": []}, source)
