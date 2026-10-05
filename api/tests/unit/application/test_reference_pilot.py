"""Контроль версий, кэша этапов, остановки партий и изоляции цели."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from application.reference_pilot import ReferencePilot
from domain.article_maps import ArticleMapError, prepare_source
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.reference_pilot_sources import parse_references, validate_conversion
from infrastructure.reference_pilot_store import CachedStageModel, PilotStore


TEXT = "# Study\n\nMice were eligible and enrolled.\n\n## References\n\n1. Earlier study."


def graph(subject="Mice", head=True):
    concept = {"id": "C1", "display_text": subject, "aliases": [], "provenance": {"unit_ids": ["U2"]}}
    nodes = []
    for identifier, predicate in (("N1", "eligible"), ("N2", "enrolled")) if head else (("N1", "eligible"),):
        nodes.append({"id": identifier, "display_text": f"{subject} are {predicate}", "aliases": [],
                      "kind": "assertion", "provenance": {"unit_ids": ["U2"]},
                      "semantic": {"predicate": predicate, "roles": [{"role": "subject", "concept_id": "C1", "node_id": None}],
                                   "inputs": [], "quantifier": None, "modality": None, "negated": False,
                                   "conditions": [], "temporal_context": None, "qualifiers": {"attributes": []}}})
    return {"schema_version": 5, "concepts": [concept], "nodes": nodes, "edges": []}


class Gateway:
    model, provider, context_length, max_tokens, timeout = "configured", "test", 100000, 10000, 60
    reasoning_effort, url, strict_schema = None, "http://configured-service", True

    def __init__(self, raw=None):
        self.output_schema = extraction_map_json_schema()
        self.raw = raw or json.dumps(graph())
        self.count = 0
        self.last_call = {}

    async def __call__(self, system, user):
        self.count += 1
        self.last_call = {"model": self.model, "usage": {"prompt_tokens": 7, "completion_tokens": 17}}
        return self.raw


def request():
    source = prepare_source("article", TEXT)
    return json.dumps({"article_id": "article", "article_text": TEXT[:source["content_end"]],
                       "source_units": source["units"]})


@pytest.mark.asyncio
async def test_stage_checkpoint_reuses_and_counts_only_new_tokens(tmp_path):
    gateway, store = Gateway(), PilotStore(tmp_path)
    first = CachedStageModel(gateway, store, TEXT, stage="extraction")
    raw = await first("prompt v1", request())
    second = CachedStageModel(gateway, store, TEXT, stage="extraction")
    assert await second("prompt v1", request()) == raw
    assert gateway.count == 1
    assert first.calls[0]["usage"]["completion_tokens"] == 17
    assert second.calls[0]["reused"] and second.calls[0]["usage"] == {}


@pytest.mark.asyncio
async def test_interrupted_transport_archives_raw_and_safe_metadata_without_cache(tmp_path):
    from domain.article_maps import digest

    class InterruptedGateway(Gateway):
        async def __call__(self, system, user):
            self.count += 1
            self.last_response = '{"schema_version":5,'
            self.last_call = {"model": self.model, "usage": {}, "elapsed_seconds": 12,
                              "response_sha256": digest(self.last_response), "finish_reason": None,
                              "sse_terminal_frame": False}
            raise ArticleMapError("AI gateway reported an upstream error")

    gateway, store = InterruptedGateway(), PilotStore(tmp_path)
    with pytest.raises(ArticleMapError):
        await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    partial = next(tmp_path.glob("responses/extraction/*/*/transport_response.txt"))
    metadata = json.loads(partial.with_name(partial.name + ".metadata.json").read_text(encoding="utf-8"))
    assert partial.read_text(encoding="utf-8") == gateway.last_response
    assert metadata["model_call"]["response_sha256"] == digest(gateway.last_response)
    attempt = store.read("cost_ledger.json")["attempts"][0]
    assert attempt["model_call"] == gateway.last_call and attempt["usage"] == {}
    assert attempt["validated"] is False and gateway.count == 1
    assert not list(tmp_path.glob("stage_cache/extraction/*.json"))


@pytest.mark.asyncio
async def test_translation_reuses_exact_labels_without_repeating_llm(tmp_path):
    gateway = Gateway(json.dumps({"N1": "Мыши соответствовали критериям"}))
    gateway.output_schema = {"type": "object", "properties": {"N1": {"type": "string"}},
                             "required": ["N1"], "additionalProperties": False}
    store = PilotStore(tmp_path)
    labels = json.dumps({"N1": "Mice were eligible"})
    first = CachedStageModel(gateway, store, TEXT, stage="translation_ru")
    answer = await first("Translate labels", labels)
    second = CachedStageModel(gateway, store, TEXT, stage="translation_ru")
    assert await second("Translate labels", labels) == answer
    assert gateway.count == 1 and second.calls[0]["reused"]
    assert list(store.root.glob("requests/translation_ru/*.json"))
    assert list(store.root.glob("responses/translation_ru/*/*/*.txt"))
    await second("Translate labels", json.dumps({"N1": "Mice satisfied new criteria"}))
    assert gateway.count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ['{"other":"Другой блок"}', '{"N1":""}', '{"N1":'])
async def test_invalid_translation_is_archived_and_never_reused(tmp_path, raw):
    gateway, store = Gateway(raw), PilotStore(tmp_path)
    with pytest.raises(ArticleMapError):
        await CachedStageModel(gateway, store, TEXT, stage="translation_ru")(
            "Translate labels", json.dumps({"N1": "Mice were eligible"}))
    assert not list(store.root.glob("stage_cache/translation_ru/*.json"))
    assert store.read("cost_ledger.json")["attempts"][0]["validated"] is False


@pytest.mark.asyncio
async def test_dependency_prompt_change_reuses_extraction_and_translation_for_new_map(tmp_path, monkeypatch):
    from domain.article_maps import digest
    from infrastructure.reference_pilot_builder import ProductionPilotMapBuilder

    counts = {"extraction": 0, "dependencies": 0, "translation_ru": 0}

    class ModelGateway(Gateway):
        def __init__(self, *, output_schema=None, strict_schema=True):
            super().__init__()
            if output_schema is not None:
                self.output_schema = output_schema
            self.stage = ("dependencies" if output_schema is None else
                          "extraction" if "schema_version" in output_schema["properties"] else "translation_ru")

        async def __call__(self, system, user):
            counts[self.stage] += 1
            self.last_call = {"model": self.model, "usage": {"prompt_tokens": 7, "completion_tokens": 17}}
            if self.stage == "dependencies":
                return json.dumps({"dependencies": []})
            if self.stage == "translation_ru":
                return json.dumps({identifier: "Перевод: " + text for identifier, text in json.loads(user).items()})
            return json.dumps(graph())

    class Repository:
        def __init__(self):
            self.result = None

        def acquire(self, article_id, pipeline, owner, token):
            pass

        def release(self, article_id, pipeline, owner, token):
            pass

        def renew(self, article_id, pipeline, owner, token):
            pass

        def save(self, result, owner, token):
            self.result = copy.deepcopy(result)

        def get(self, article_id, pipeline, owner):
            return copy.deepcopy(self.result)

        def save_translation(self, article_id, pipeline, owner, run_id, translation, token):
            assert self.result["run_id"] == run_id
            self.result.setdefault("translations", {})["ru"] = translation

    class Reader:
        async def read_text(self, article_id, owner):
            return TEXT

    monkeypatch.setattr("infrastructure.reference_pilot_builder.ArticleMapModelGateway", ModelGateway)
    monkeypatch.setattr("infrastructure.reference_pilot_builder.ArticleMapDependencyModelGateway", ModelGateway)
    store = PilotStore(tmp_path / "artifacts")
    builder = ProductionPilotMapBuilder(Repository(), Reader(), "owner", store)
    source = {"article_id": "article", "source_sha256": digest(TEXT)}
    first = await builder.build(source)
    changed_prompt = tmp_path / "dependencies.en.md"
    changed_prompt.write_text("New dependency prompt version", encoding="utf-8")
    monkeypatch.setattr("infrastructure.reference_pilot_builder.DEPENDENCY_PROMPT_PATH", changed_prompt)
    monkeypatch.setattr("application.text_to_map.DEPENDENCY_PROMPT_PATH", changed_prompt)
    second = await builder.build(source)
    assert first["run_id"] != second["run_id"]
    assert counts == {"extraction": 1, "dependencies": 2, "translation_ru": 1}
    assert store.read(f"translations/{second['run_id']}/ru.json")["run_id"] == second["run_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["prompt", "source", "request", "model", "validator"])
async def test_changed_binding_rebuilds_affected_stage(tmp_path, monkeypatch, change):
    gateway, store = Gateway(), PilotStore(tmp_path)
    await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    prompt, source, user = "prompt", TEXT, request()
    if change == "prompt":
        prompt += " changed"
    if change == "source":
        source += "\n"
    if change == "request":
        user = json.dumps(json.loads(user), indent=2)
    if change == "model":
        gateway.reasoning_effort = "high"
    if change == "validator":
        monkeypatch.setattr("infrastructure.reference_pilot_store.validator_fingerprint", lambda stage: "new-validator")
    await CachedStageModel(gateway, store, source, stage="extraction")(prompt, user)
    assert gateway.count == 2


@pytest.mark.asyncio
async def test_corrupted_response_is_rejected_without_model_fallback(tmp_path):
    gateway, store = Gateway(), PilotStore(tmp_path)
    await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    path = next((tmp_path / "stage_cache" / "extraction").glob("*.json"))
    data = json.loads(path.read_text())
    data["raw"] += " "
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ArticleMapError, match="response changed"):
        await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    assert gateway.count == 1


@pytest.mark.asyncio
async def test_incomplete_or_invalid_answer_never_becomes_checkpoint(tmp_path):
    gateway, store = Gateway('{"schema_version":5'), PilotStore(tmp_path)
    with pytest.raises(ArticleMapError):
        await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    assert not (tmp_path / "stage_cache").exists()
    assert list((tmp_path / "responses").rglob("*.txt"))


@pytest.mark.asyncio
async def test_repeated_identical_invalid_answer_preserves_every_attempt_and_cost(tmp_path):
    gateway, store = Gateway('{"schema_version":5'), PilotStore(tmp_path)
    for _ in range(2):
        with pytest.raises(ArticleMapError):
            await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    assert len(list((tmp_path / "responses").rglob("*.txt"))) == 2
    assert len(store.read("cost_ledger.json")["attempts"]) == 2
    assert all(not call["validated"] for call in store.read("cost_ledger.json")["attempts"])
    assert len(list((tmp_path / "requests" / "extraction").glob("*.json"))) == 1


@pytest.mark.asyncio
async def test_dependency_validator_change_preserves_extraction_checkpoint(tmp_path, monkeypatch):
    gateway, store = Gateway(), PilotStore(tmp_path)
    monkeypatch.setattr("infrastructure.reference_pilot_store.validator_fingerprint",
                        lambda stage: "extraction-unchanged" if stage == "extraction" else "dependencies-v1")
    await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    monkeypatch.setattr("infrastructure.reference_pilot_store.validator_fingerprint",
                        lambda stage: "extraction-unchanged" if stage == "extraction" else "dependencies-v2")
    await CachedStageModel(gateway, store, TEXT, stage="extraction")("prompt", request())
    assert gateway.count == 1


@pytest.mark.asyncio
async def test_explicit_revalidation_accepts_identical_response_without_llm_or_edits(tmp_path, monkeypatch):
    gateway, store = Gateway(), PilotStore(tmp_path)
    monkeypatch.setattr("infrastructure.reference_pilot_store.validator_fingerprint", lambda stage: "old")
    first = CachedStageModel(gateway, store, TEXT, stage="extraction")

    def old_validator(raw, user):
        raise ArticleMapError("Old validator refusal")

    first._validate = old_validator
    with pytest.raises(ArticleMapError):
        await first("prompt", request())
    attempt = store.read("cost_ledger.json")["attempts"][0]
    monkeypatch.setattr("infrastructure.reference_pilot_store.validator_fingerprint", lambda stage: "new")
    resumed = CachedStageModel(gateway, store, TEXT, stage="extraction")
    receipt = resumed.revalidate_attempt(attempt["attempt_id"])
    assert receipt["llm_calls"] == 0 and receipt["validation"] == "passed"
    assert await resumed("prompt", request()) == gateway.raw
    assert gateway.count == 1 and resumed.calls[-1]["reused"]
    assert store.read("cost_ledger.json")["attempts"][0]["validated"] is False
    gateway.reasoning_effort = "changed"
    with pytest.raises(ArticleMapError, match="unchanged"):
        CachedStageModel(gateway, store, TEXT, stage="extraction").revalidate_attempt(attempt["attempt_id"])


def test_artifacts_are_immutable_and_cannot_escape_root(tmp_path):
    store = PilotStore(tmp_path)
    store.write("runs/one/report.json", {"version": 1})
    with pytest.raises(ArticleMapError, match="Immutable"):
        store.write("runs/one/report.json", {"version": 2})
    with pytest.raises(ArticleMapError, match="escapes"):
        store.write("../outside.json", {})
    with store.lock():
        with pytest.raises(ValueError, match="locked"):
            with store.lock():
                pass
    assert not (tmp_path / "writer.lock").exists()


def test_full_reference_registry_includes_last_four_and_rejects_truncation():
    refs = "".join(f'<ref><label>{n}.</label><mixed-citation publication-type="journal">'
                   f'<article-title>Paper {n}</article-title><year>2020</year>'
                   f'<pub-id pub-id-type="doi">10.1000/paper{n}</pub-id></mixed-citation></ref>' for n in range(1, 55))
    assert len(parse_references(f"<article><back><ref-list>{refs}</ref-list></back></article>".encode())) == 54
    truncated = refs[:refs.rfind("<ref>")]
    with pytest.raises(ArticleMapError, match="1–54"):
        parse_references(f"<article><ref-list>{truncated}</ref-list></article>".encode())


@pytest.mark.parametrize("failure", ["last_reference", "body", "language"])
def test_full_text_gate_rejects_lost_body_bibliography_or_non_english(failure):
    xml = '<article xml:lang="en"><body><p>Distinct scientific body tokens preserved.</p></body>' \
          '<back><ref-list><ref><label>54.</label><mixed-citation>Last source</mixed-citation>' \
          '</ref></ref-list></back></article>'
    markdown = '# Study\nDistinct scientific body tokens preserved.\n## References\n54. Last source'
    assert validate_conversion(xml.encode(), markdown)["body_token_presence"] == 1
    if failure == "last_reference":
        markdown = markdown.replace("54.", "50.")
    elif failure == "body":
        markdown = "# Empty\n## References\n54. Last source"
    else:
        xml = xml.replace('xml:lang="en"', 'xml:lang="ru"')
    with pytest.raises(ArticleMapError):
        validate_conversion(xml.encode(), markdown)


class Provider:
    def __init__(self, store):
        self.store = store
        self.materialized = []

    async def registry(self):
        return {"target_pmc_id": "PMC10000452", "target_doi": "target-doi",
                "order": list(range(1, 12)),
                "references": [{"number": n, "title": f"Cognitive study {n}", "status": "open_access"}
                               for n in range(1, 12)]}

    async def materialize(self, reference):
        self.materialized.append(reference["number"])
        return {"source_id": f"source-{reference['number']}", "title": reference["title"],
                "reference_number": reference["number"], "article_id": f"article-{reference['number']}"}

    async def target(self):
        assert list(self.store.root.glob("runs/*/predictions.json")), "Target loaded before predictions were sealed"
        return {"source_id": "PMC10000452", "article_id": "target"}


class Builder:
    def __init__(self):
        self.calls = []

    async def build(self, source):
        if source["source_id"] == "PMC10000452":
            value = graph("Hamsters")
            value["nodes"] = value["nodes"][1:]
        else:
            n = source["reference_number"]
            value = graph(f"Animals {n}", head=n < 3)
            if n < 3:
                value["edges"] = [{"source": "N1", "target": "N2"}]
        return {"run_id": source["article_id"], "graph": value}


@pytest.mark.asyncio
async def test_first_checkpoint_stops_at_five_and_target_is_evaluator_only(tmp_path):
    store = PilotStore(tmp_path)
    provider, builder = Provider(store), Builder()
    report = await ReferencePilot(provider, builder, store).run(5)
    assert provider.materialized == [1, 2, 3, 4, 5]
    assert report["source_count"] == 5 and not report["automatic_advance"]
    assert store.read("state.json")["completed_size"] == 5
    assert store.read(f"runs/{report['run_id']}/report.json")
    assert store.read("target/anchor.json")


@pytest.mark.asyncio
async def test_diagnostic_costs_are_counted_without_entering_prediction_corpus(tmp_path):
    baseline_store = PilotStore(tmp_path / "baseline")
    baseline = await ReferencePilot(Provider(baseline_store), Builder(), baseline_store).run(5)
    store = PilotStore(tmp_path / "diagnostic")
    store.write("diagnostic_calls.json", {"attempts": [{
        "attempt_id": "synthetic-control", "stage": "diagnostic_dependencies", "model": "configured",
        "reused": False, "validated": True, "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "arbitrary_claim_data": {"source_id": "PMC10000452", "graph": graph("Injected target")}}]})
    report = await ReferencePilot(Provider(store), Builder(), store).run(5)
    assert report["predictions"] == baseline["predictions"]
    assert report["sources"] == baseline["sources"]
    assert report["source_count"] == 5
    assert report["costs"]["scientific"] == {}
    costs = report["costs"]["diagnostic"]["diagnostic_dependencies"]
    assert costs["new_calls"] == 1 and costs["input_tokens"] == 10 and costs["output_tokens"] == 20
    assert report["costs"]["cumulative"] == report["costs"]["diagnostic"]


@pytest.mark.asyncio
async def test_failure_stops_queued_maps_and_preserves_already_running_neighbor(tmp_path):
    store = PilotStore(tmp_path)
    started = []
    first_failed, neighbor_started = asyncio.Event(), asyncio.Event()

    class ControlledBuilder(Builder):
        async def build(self, source):
            number = source["reference_number"]
            started.append(number)
            if number == 1:
                await neighbor_started.wait()
                first_failed.set()
                raise ArticleMapError("Rejected map")
            assert number == 2, "Queued sources must not start after a failure"
            neighbor_started.set()
            await first_failed.wait()
            await asyncio.sleep(0)
            store.write("maps/neighbor.json", {"validated": True})
            return await super().build(source)

    with pytest.raises(ArticleMapError, match="Rejected map"):
        await ReferencePilot(Provider(store), ControlledBuilder(), store, map_concurrency=2).run(5)
    assert started == [1, 2]
    assert store.read("maps/neighbor.json") == {"validated": True}
    assert store.read("state.json") is None
    assert not list(store.root.glob("runs/*/predictions.json"))


@pytest.mark.asyncio
async def test_checkpoint_cancellation_awaits_all_started_maps(tmp_path):
    store = PilotStore(tmp_path)
    both_started = asyncio.Event()
    active, finished = set(), set()

    class WaitingBuilder(Builder):
        async def build(self, source):
            number = source["reference_number"]
            active.add(number)
            if len(active) == 2:
                both_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active.remove(number)
                finished.add(number)

    task = asyncio.create_task(ReferencePilot(Provider(store), WaitingBuilder(), store, map_concurrency=2).run(5))
    await both_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not active and finished == {1, 2}
    assert store.read("state.json") is None


@pytest.mark.asyncio
async def test_checkpoint_cannot_skip_and_failure_does_not_replace_state(tmp_path):
    store = PilotStore(tmp_path)
    provider, builder = Provider(store), Builder()
    scenario = ReferencePilot(provider, builder, store)
    with pytest.raises(ArticleMapError, match="skip"):
        await scenario.run(10)
    first = await scenario.run(5)

    async def failing(source):
        raise ValueError("invalid map")

    builder.build = failing
    with pytest.raises(ValueError, match="invalid map"):
        await scenario.run(5)
    assert store.read("state.json")["run_id"] == first["run_id"]


@pytest.mark.asyncio
async def test_rerun_retains_anchor_and_previous_immutable_report(tmp_path):
    store = PilotStore(tmp_path)
    scenario = ReferencePilot(Provider(store), Builder(), store)
    one = await scenario.run(5)
    anchor = store.read("target/anchor.json")
    two = await scenario.run(5)
    assert two["previous_run_id"] == one["run_id"]
    assert store.read("target/anchor.json") == anchor
    assert store.read(f"runs/{one['run_id']}/report.json") == one


@pytest.mark.asyncio
async def test_frozen_reference_order_is_used_without_resorting(tmp_path):
    store = PilotStore(tmp_path)

    class ReversedProvider(Provider):
        async def registry(self):
            value = await super().registry()
            value["order"] = list(reversed(value["order"]))
            return value

    provider = ReversedProvider(store)
    await ReferencePilot(provider, Builder(), store).run(5)
    assert provider.materialized == [11, 10, 9, 8, 7]


@pytest.mark.asyncio
async def test_incompatible_map_versions_are_rejected_before_target(tmp_path):
    store = PilotStore(tmp_path)

    class MixedBuilder(Builder):
        async def build(self, source):
            result = await super().build(source)
            result["prompt"] = {"version": "1" if source["reference_number"] == 1 else "2"}
            return result

    with pytest.raises(ArticleMapError, match="Incompatible"):
        await ReferencePilot(Provider(store), MixedBuilder(), store).run(5)
    assert not list(store.root.glob("runs/*/predictions.json"))
