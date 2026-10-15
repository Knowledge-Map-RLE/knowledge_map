"""Штатный двухэтапный сценарий новой модели непосредственного развития знаний."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from uuid import uuid4

from application.article_map_lock import acquire_map_lock
from application.publish_article_map import PublishArticleMap
from domain.article_maps import ArticleMapError, digest, parse_json_response, prepare_source, require
from domain.knowledge_development import (apply_development_review, initialize_occurrences,
                                          model_contract, validate_development_map)

PROMPT_ID = "KM.TEXT_TO_MAP"
PROMPT_VERSION = "4"
PROMPT_PATH = Path(__file__).with_name("text_to_map.v4.en.md")
DEPENDENCY_PROMPT_ID = "KM.TEXT_TO_MAP.DEPENDENCIES"
DEPENDENCY_PROMPT_VERSION = "16"
DEPENDENCY_PROMPT_PATH = Path(__file__).with_name("text_to_map_dependencies.v16.en.md")
DEPENDENCY_BATCH_SIZE = 40
log = logging.getLogger(__name__)


def prompt_binding():
    return {"prompt": {"id": PROMPT_ID, "version": PROMPT_VERSION,
                       "sha256": digest(PROMPT_PATH.read_text(encoding="utf-8"))},
            "dependency_prompt": {"id": DEPENDENCY_PROMPT_ID, "version": DEPENDENCY_PROMPT_VERSION,
                                  "sha256": digest(DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8"))}}


def registered_prompt_paths(binding):
    """Исторический импорт использует зарегистрированные точные версии, а не текущий промпт."""
    pair = (binding["prompt"]["version"], binding["dependency_prompt"]["version"])
    require(pair in {("3", "15"), ("4", "16")}, "Unsupported historical prompt pair")
    extraction = Path(__file__).with_name(f"text_to_map.v{pair[0]}.en.md")
    dependency = Path(__file__).with_name(f"text_to_map_dependencies.v{pair[1]}.en.md")
    expected = {"prompt": {"id": PROMPT_ID, "version": pair[0], "sha256": digest(extraction.read_text(encoding="utf-8"))},
                "dependency_prompt": {"id": DEPENDENCY_PROMPT_ID, "version": pair[1], "sha256": digest(dependency.read_text(encoding="utf-8"))}}
    require(binding == expected, "Historical prompt hashes differ")
    return extraction, dependency


def extraction_input(article_id, text, source, attachments=None):
    value = {"article_id": article_id, "article_text": text[:source["content_end"]], "source_units": source["units"]}
    if attachments:
        value["source_attachments"] = attachments
    return json.dumps(value, ensure_ascii=False)


def dependency_input(article_id, text, source, graph, targets, completed, prompt, attachments=None):
    value = {"article_id": article_id, "article_text": text[:source["content_end"]],
        "source_units": source["units"], "model_rules": prompt, "knowledge_map": model_contract(graph),
        "dependency_target_keys": targets, "completed_target_keys": completed}
    if attachments:
        value["source_attachments"] = attachments
    return json.dumps(value, ensure_ascii=False)


class TextToMap:
    def __init__(self, repository, source, model, dependency_model):
        self.repository, self.source, self.model, self.dependency_model = repository, source, model, dependency_model

    async def execute(self, article_id, user_uid, emit):
        token, started = str(uuid4()), time.monotonic()
        await acquire_map_lock(self.repository, article_id, "text_reified", user_uid, token)
        try:
            text = await self.source.read_text(article_id, user_uid)
            source = prepare_source(article_id, text)
            prompt = PROMPT_PATH.read_text(encoding="utf-8")
            user = extraction_input(article_id, text, source)
            await emit({"type": "progress", "stage": "model", "processed": 0, "total": 1})
            log.info("text_to_map v4 started article=%s source_hash=%s chars=%s", article_id, source["sha256"], len(text))
            raw = await self.model(prompt, user)
            extraction_call = dict(self.model.last_call)
            graph = validate_development_map(parse_json_response(raw), source, extraction=True)
            graph = initialize_occurrences(graph, source)
            canonical_keys = [k["knowledge_id"] for k in graph["knowledge"]]
            batches = [canonical_keys[i:i + DEPENDENCY_BATCH_SIZE] for i in range(0, len(canonical_keys), DEPENDENCY_BATCH_SIZE)]
            calls, stage_bindings, completed = [], [], []
            dependency_prompt = DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")
            await emit({"type": "progress", "stage": "dependencies", "processed": 0, "total": len(batches)})
            for index, targets in enumerate(batches):
                await asyncio.to_thread(self.repository.renew, article_id, "text_reified", user_uid, token)
                dependency_user = dependency_input(article_id, text, source, graph, targets, completed, prompt)
                dependency_raw = await self.dependency_model(dependency_prompt, dependency_user)
                graph = apply_development_review(dependency_raw, graph, source, target_keys=targets)
                calls.append(dict(self.dependency_model.last_call))
                stage_bindings.append({"targets": targets, "system_sha256": digest(dependency_prompt),
                                       "user_sha256": digest(dependency_user), "response_sha256": digest(dependency_raw)})
                completed.extend(targets)
                log.info("text_to_map v4 group article=%s batch=%s total=%s transitions=%s", article_id,
                         index + 1, len(batches), len(graph["transitions"]))
                await emit({"type": "progress", "stage": "dependencies", "processed": index + 1, "total": len(batches)})
            require(completed == canonical_keys, "Review did not cover every canonical knowledge")
            graph = validate_development_map(model_contract(graph), source)
            await emit({"type": "progress", "stage": "saving", "processed": 1, "total": 1})
            from application.text_to_map import _dependency_call_summary
            return await PublishArticleMap(self.repository, self.source).execute(article_id, user_uid, graph,
                expected_source_sha256=source["sha256"], token=token,
                metadata=prompt_binding() | {"generation": {"kind": "project_llm", "model": extraction_call.get("model"),
                                                           "reasoning_effort": extraction_call.get("reasoning_effort")},
                    "model_call": extraction_call, "dependency_model_call": _dependency_call_summary(calls),
                    "stage_bindings": {"extraction": {"system_sha256": digest(prompt), "user_sha256": digest(user),
                                                       "response_sha256": digest(raw)}, "dependencies": stage_bindings},
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "validator_version": "knowledge-development-6.1"})
        except BaseException as exc:
            reason = str(exc) if isinstance(exc, ArticleMapError) else type(exc).__name__
            log.warning("text_to_map v4 stopped article=%s reason=%s elapsed=%.2f", article_id,
                        reason, time.monotonic() - started)
            raise
        finally:
            await asyncio.shield(asyncio.to_thread(self.repository.release, article_id, "text_reified", user_uid, token))
