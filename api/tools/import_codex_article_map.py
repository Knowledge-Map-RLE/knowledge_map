"""Административный импорт карты Codex; генерация и перевод LLM запрещены."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
ROOT = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(ROOT / "shared/model_registry"))

from application.publish_article_map import PublishArticleMap
from application.text_to_development_map import (prompt_binding, extraction_input, dependency_input,
    PROMPT_PATH, DEPENDENCY_PROMPT_PATH, DEPENDENCY_BATCH_SIZE, registered_prompt_paths)
from domain.article_maps import digest, fingerprint, parse_json_response, prepare_source, require
from domain.knowledge_development import (apply_development_review, initialize_occurrences,
                                          model_contract, validate_development_map)

TARGET = "PMC10000452"
SOURCE_SHA = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
DOCUMENT = "pilot-pmc10000452-pmc10000452-f7df96ff746be4a6"

# Разрешены только адресно проверенные полные ревизии GOLD.
VERIFIED_SOURCES = {
    "PMC10000452": (DOCUMENT, SOURCE_SHA),
    "PMC5436834": ("pilot-pmc10000452-pmc5436834-10b9d676a760e5df", "10b9d676a760e5dff9c20a7858f3f795e0fa60adf931a02b82a3b02089df905a"),
    "PMC6416157": ("pilot-pmc10000452-pmc6416157-502eaa3572eaf017", "502eaa3572eaf01749010d6b4f40590ede4abef1dcc926d505da7aeecd644e4a"),
    "PMC7789349": ("pilot-pmc10000452-pmc7789349-73aceacf48b80ce6", "73aceacf48b80ce687091ad566213d687d981782580ef6128d6e21eca100f859"),
    "PMC8775386": ("pilot-pmc10000452-pmc8775386-953d8a7973426b47", "953d8a7973426b4790a3925cf72fdcee63c0bb3c3a4aa99c3097d7ad70f27c3a"),
    "PMC8918697": ("pilot-pmc10000452-pmc8918697-8c000fc820edb9c7", "8c000fc820edb9c7dd89ad948bc2c2563009c256a19c20c7f6b7ab787c373fee"),
}


def prohibit_generation():
    """Сеть хранилищ разрешена; HTTP-транспорт модельной генерации недоступен."""
    import httpx
    def forbidden(*args, **kwargs):
        raise RuntimeError("Model/translation HTTP calls are prohibited during Codex import")
    async def async_forbidden(*args, **kwargs):
        forbidden()
    httpx.AsyncClient.stream = forbidden
    httpx.AsyncClient.post = async_forbidden
    httpx.AsyncClient.send = async_forbidden
    httpx.Client.send = forbidden
    httpx.Client.request = forbidden


def load_bundle(folder):
    """Проверяет точные входы и ответы каждого этапа, не изменяя артефакты."""
    manifest = parse_json_response((folder / "manifest.json").read_text(encoding="utf-8"))
    binding = VERIFIED_SOURCES.get(manifest["pmc_id"])
    require(binding is not None and manifest["article_id"] == binding[0],
            "Codex import accepts only explicitly verified GOLD documents")
    article_id, source_sha = binding
    text = (folder / "article.md").read_bytes().decode("utf-8")
    require(digest(text) == source_sha == manifest["source_sha256"], "Incorrect full source revision")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe bundle path")
        from hashlib import sha256
        require(sha256((folder / relative).read_bytes()).hexdigest() == expected, f"Bundle checksum differs: {name}")
    extraction_path, dependency_path = registered_prompt_paths(manifest["prompt_binding"])
    generation = manifest["generation"]
    require(generation["kind"] == "codex_manual" and generation["external_llm_calls"] == 0
            and generation["local_llm_calls"] == 0 and generation["token_usage"] is None,
            "Codex import must not pretend to be a provider call")
    source = prepare_source(article_id, text)
    attachments = []
    if "source.attachments.json" in manifest["files"]:
        attachments = parse_json_response((folder / "source.attachments.json").read_text(encoding="utf-8"))
        require(isinstance(attachments, list) and bool(attachments), "Invalid source attachments")
        xml = (folder / "article.xml").read_text(encoding="utf-8")
        for attachment in attachments:
            require(set(attachment) == {"unit_id", "xml_asset", "text", "author", "media_file"}, "Invalid table evidence fields")
            require(attachment["unit_id"] in {u["id"] for u in source["units"]}
                    and attachment["xml_asset"] in xml and attachment["author"] == "Codex"
                    and bool(attachment["text"]) and attachment["media_file"] in manifest["files"],
                    "Unbound table evidence")
    prompt = extraction_path.read_text(encoding="utf-8")
    dependency_prompt = dependency_path.read_text(encoding="utf-8")
    def verify_request(name, system, user):
        require(name in manifest["files"], "Unbound stage request")
        request = parse_json_response((folder / name).read_text(encoding="utf-8"))
        require(request == {"system": system, "user": user}, "Stage request differs from production input")
    verify_request("extraction.request.json", prompt, extraction_input(article_id, text, source, attachments))
    extraction_raw = (folder / "extraction.response.json").read_text(encoding="utf-8")
    graph = validate_development_map(parse_json_response(extraction_raw), source, extraction=True)
    graph = initialize_occurrences(graph, source)
    groups = manifest["dependency_groups"]
    completed = []
    for group in groups:
        expected_targets = [k["knowledge_id"] for k in graph["knowledge"]][len(completed):len(completed) + DEPENDENCY_BATCH_SIZE]
        require(group["targets"] == expected_targets, "Dependency target group differs from production grouping")
        verify_request(group["request"], dependency_prompt,
            dependency_input(article_id, text, source, graph, group["targets"], completed, prompt, attachments))
        require(group["response"] in manifest["files"], "Unbound dependency response")
        raw = (folder / group["response"]).read_text(encoding="utf-8")
        graph = apply_development_review(raw, graph, source, target_keys=group["targets"])
        completed.extend(group["targets"])
    require(completed == [k["knowledge_id"] for k in graph["knowledge"]], "Incomplete canonical target review")
    graph = validate_development_map(model_contract(graph), source)
    coverage = parse_json_response((folder / "coverage.json").read_text(encoding="utf-8"))
    require(set(coverage) == {u["id"] for u in source["units"]}, "Source coverage inventory differs")
    knowledge = {k["knowledge_id"]: k for k in graph["knowledge"]}
    for uid, record in coverage.items():
        require(set(record) == {"knowledge_ids", "excluded_reason"}, "Invalid source coverage fields")
        require(bool(record["knowledge_ids"]) != bool(record["excluded_reason"]), "Source coverage must represent or explain exclusion")
        require(all(k in knowledge and uid in knowledge[k]["provenance"]["unit_ids"] for k in record["knowledge_ids"]),
                "Source coverage cites unrelated knowledge")
    labels = parse_json_response((folder / "translation.ru.json").read_text(encoding="utf-8"))
    return manifest, graph, labels


async def run(folder, *, validate_only=False):
    prohibit_generation()
    manifest, graph, labels = load_bundle(folder)
    article_id, source_sha = manifest["article_id"], manifest["source_sha256"]
    if validate_only:
        print(json.dumps({"validated": True, "run_id": manifest["run_id"], "analysis": graph["analysis"],
                          "external_llm_calls": 0, "local_llm_calls": 0}, ensure_ascii=False))
        return
    # Адаптеры хранилищ загружаются только после полной офлайн-валидации пакета.
    from infrastructure.config import settings
    from infrastructure.article_map_source import StoredArticleMapSource
    from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
    from infrastructure.s3.s3_storage import get_s3_client
    repo = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    try:
        repo.ensure_schema()
        with repo.driver.session() as session:
            document = session.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=article_id).single()
        require(document is not None and bool(document["owner"]), "Corrected target document or owner is missing")
        owner = document["owner"]
        structural = repo.get(article_id, "structural_rows", owner)
        previous = repo.get(article_id, "text_reified", owner)
        result = repo.get(article_id, "text_reified", owner, manifest["run_id"])
        if result is not None:
            require(result["graph"] == graph and result["source"]["sha256"] == source_sha
                    and result.get("artifact_binding_sha256") == fingerprint(manifest),
                    "Existing immutable run differs from prepared bundle")
            require(result["translations"]["ru"]["knowledge_labels"] == labels, "Existing translation differs")
        else:
            result = await PublishArticleMap(repo, StoredArticleMapSource(repo, get_s3_client(), settings.S3_BUCKET_NAME)).execute(
            article_id, owner, graph, expected_source_sha256=source_sha, run_id=manifest["run_id"], labels_ru=labels,
            metadata=manifest["prompt_binding"] | {"generation": manifest["generation"], "needs_expert_review": True,
                "expert_validated": False, "validator_version": "knowledge-development-6.1",
                "artifact_binding_sha256": fingerprint(manifest), "coverage_sha256": manifest["files"]["coverage.json"],
                "source_attachments": parse_json_response((folder / "source.attachments.json").read_text(encoding="utf-8"))
                    if "source.attachments.json" in manifest["files"] else []})
        saved = repo.get(article_id, "text_reified", owner, result["run_id"])
        require(saved == result, "Published run differs from validated Codex result")
        require(repo.get(article_id, "structural_rows", owner) == structural, "Structural map changed")
        if previous is not None:
            require(repo.get(article_id, "text_reified", owner, previous["run_id"]) == previous, "Previous map was not preserved")
        require(not any(n.startswith("infrastructure.article_map_model") for n in sys.modules),
                "Model gateway was unexpectedly imported")
        receipt = folder / "published.json"
        if receipt.exists():
            require(parse_json_response(receipt.read_text(encoding="utf-8")) == result, "Publication receipt differs")
        else:
            with receipt.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({"saved": True, "article_id": article_id, "run_id": result["run_id"], "analysis": graph["analysis"],
                          "external_llm_calls": 0, "local_llm_calls": 0}, ensure_ascii=False), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    require(os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required by AGENTS.md")
    parser = argparse.ArgumentParser(description="Publish a Codex-authored schema-6 map without calling any model")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.bundle.resolve(), validate_only=args.validate_only))
