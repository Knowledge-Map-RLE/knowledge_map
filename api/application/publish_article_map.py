"""Общая публикация карты: проверка источника, семантики и отдельного перевода."""
from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from application.article_map_lock import acquire_map_lock
from domain.article_maps import digest, new_result, prepare_source, require
from domain.knowledge_development import model_contract, validate_development_map

log = logging.getLogger(__name__)


def russian_translation(graph, labels, run_id, generation):
    require(isinstance(labels, dict) and set(labels) == {k["knowledge_id"] for k in graph["knowledge"]},
            "Translation must cover exactly the canonical knowledge ids")
    require(all(isinstance(v, str) and v.strip() for v in labels.values()), "Empty translated knowledge")
    return {"run_id": run_id, "knowledge_labels": dict(labels),
            "labels": {n["id"]: labels[n["knowledge_id"]] for n in graph["nodes"]}, "generation": generation}


class PublishArticleMap:
    """Не создаёт AI-клиентов: принимает уже подготовленное содержимое карты."""

    def __init__(self, repository, source):
        self.repository, self.source = repository, source

    async def execute(self, article_id, user_uid, graph, *, expected_source_sha256,
                      metadata, labels_ru=None, run_id=None, token=None):
        owns_lock = token is None
        token = token or str(uuid4())
        if owns_lock:
            await acquire_map_lock(self.repository, article_id, "text_reified", user_uid, token)
        try:
            text = await self.source.read_text(article_id, user_uid)
            require(digest(text) == expected_source_sha256, "Saved article differs from prepared map source")
            source = prepare_source(article_id, text)
            validated = validate_development_map(model_contract(graph), source)
            result = new_result(article_id, "text_reified", validated, source["sha256"], source=source,
                                builder_version="3", **metadata,
                                validation={"contract": "passed", "dag": "passed", "provenance": "passed",
                                            "canonical_knowledge": "passed", "occurrences": "passed",
                                            "transition_groups": "passed", "scientific_accuracy": "not_assessed"})
            if run_id is not None:
                from uuid import UUID
                require(str(UUID(run_id)) == run_id, "Invalid map run id")
                result["run_id"] = run_id
            if labels_ru is not None:
                result["translations"] = {"ru": russian_translation(validated, labels_ru, result["run_id"],
                                                                       metadata["generation"])}
            require(digest(await self.source.read_text(article_id, user_uid)) == source["sha256"],
                    "Article text changed before publication")
            await asyncio.to_thread(self.repository.renew, article_id, "text_reified", user_uid, token)
            await asyncio.to_thread(self.repository.save, result, user_uid, token)
            log.info("article_map published article=%s run=%s schema=6 source_hash=%s knowledge=%s edges=%s generation=%s",
                     article_id, result["run_id"], source["sha256"], len(validated["knowledge"]),
                     len(validated["edges"]), metadata["generation"]["kind"])
            return result
        finally:
            if owns_lock:
                await asyncio.shield(asyncio.to_thread(self.repository.release, article_id, "text_reified", user_uid, token))
