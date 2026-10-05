"""Адаптер эксперимента к штатному сценарию TextToMap и отдельному переводу."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from application.text_to_map import DEPENDENCY_PROMPT_PATH, PROMPT_PATH, TextToMap, TranslateArticleMap
from domain.article_maps import digest, fingerprint, prepare_source, require
from domain.knowledge_map import model_contract, validate_knowledge_map
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.article_map_model import ArticleMapDependencyModelGateway, ArticleMapModelGateway
from infrastructure.reference_pilot_store import CachedStageModel, gateway_settings, validator_fingerprint

log = logging.getLogger(__name__)


class ProductionPilotMapBuilder:
    def __init__(self, repository, source_reader, owner, store, *, translate_ru: bool = True):
        self.repository, self.source_reader, self.owner, self.store = repository, source_reader, owner, store
        self.calls = []
        self.translate_ru = translate_ru

    async def build(self, source: dict) -> dict:
        article_id = source["article_id"]
        text = await self.source_reader.read_text(article_id, self.owner)
        require(digest(text) == source["source_sha256"], "Saved source revision differs from experiment manifest")
        model = ArticleMapModelGateway(output_schema=extraction_map_json_schema(), strict_schema=True)
        dependency_model = ArticleMapDependencyModelGateway()
        binding = {"source_sha256": digest(text), "article_id": article_id,
                   "extraction_prompt": digest(PROMPT_PATH.read_text(encoding="utf-8")),
                   "dependency_prompt": digest(DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")),
                   "validator": validator_fingerprint(), "settings": gateway_settings(model),
                   "dependency_settings": gateway_settings(dependency_model),
                   "scenario": digest(Path(__file__).parents[1].joinpath("application/text_to_map.py").read_text(encoding="utf-8"))}
        key = fingerprint(binding)
        relative = f"maps/{article_id}/{key}.json"
        cached = self.store.read(relative)
        prepared = prepare_source(article_id, text)
        if cached is not None:
            require(cached["binding"] == binding, "Map checkpoint binding differs")
            result = cached["result"]
            require(result["source"] == prepared and result["input_fingerprint"] == digest(text),
                    "Map checkpoint source differs")
            require(validate_knowledge_map(model_contract(result["graph"]), prepared) == result["graph"],
                    "Map checkpoint graph is invalid")
            for stage, call in (("extraction", result["model_call"]), ("dependencies", result["dependency_model_call"])):
                self.calls.append({"stage": stage, "article_id": article_id, "reused": True, "usage": {},
                                   "original_usage": call.get("usage", {}),
                                   "model": call.get("resolved_model") or call.get("model"),
                                   "reason": "validated_map_snapshot"})
        else:
            extraction = CachedStageModel(model, self.store, text, stage="extraction")
            dependencies = CachedStageModel(dependency_model, self.store, text, stage="dependencies")

            async def emit(event):
                log.info("reference_pilot article=%s stage=%s", article_id, event.get("stage"))

            try:
                result = await TextToMap(self.repository, self.source_reader, extraction, dependencies).execute(
                    article_id, self.owner, emit)
            finally:
                self.calls.extend(call | {"article_id": article_id} for call in extraction.calls + dependencies.calls)
            require(validate_knowledge_map(model_contract(result["graph"]), prepared) == result["graph"],
                    "Saved map does not pass independent validation")
            saved = self.repository.get(article_id, "text_reified", self.owner)
            require(saved == result, "Saved map differs from validated result")
            self.store.write(relative, {"binding": binding, "result": result})
        if self.translate_ru:
            translation_path = f"translations/{result['run_id']}/ru.json"
            translation = self.store.read(translation_path)
            if translation is None:
                labels = {n["id"]: {"type": "string", "minLength": 1} for n in result["graph"]["nodes"]}
                translator = ArticleMapModelGateway(output_schema={"type": "object", "properties": labels,
                                                    "required": list(labels), "additionalProperties": False}, strict_schema=True)
                cached_translator = CachedStageModel(translator, self.store, text, stage="translation_ru")
                try:
                    translation = await TranslateArticleMap(self.repository, cached_translator).execute(
                        article_id, "text_reified", self.owner)
                    require(translation["run_id"] == result["run_id"], "Current UI map differs from experiment snapshot")
                    self.store.write(translation_path, translation)
                except Exception as exc:
                    log.warning("reference_pilot translation_failed article=%s reason=%s", article_id, type(exc).__name__)
                finally:
                    self.calls.extend(call | {"article_id": article_id} for call in cached_translator.calls)
            else:
                require(translation["run_id"] == result["run_id"], "Translation belongs to another map result")
                self.calls.append({"stage": "translation_ru", "article_id": article_id, "reused": True,
                                   "usage": {}, "model": translation["model_call"].get("model"),
                                   "reason": "bound_translation_snapshot"})
        return result | {"experiment_binding": binding}
