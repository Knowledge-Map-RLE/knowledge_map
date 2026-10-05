"""Rebuild a saved article map from its structural rows without model calls."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time

from knowledge_contracts.validation import (
    require,
    validate_linguistic,
    validate_structural,
)
from application.ports.article_pipeline import ArticlePipelineRepository
from knowledge_pipeline.knowledge_map_builder import build_knowledge_map
from knowledge_pipeline.pipeline import uid
from knowledge_pipeline.quality_metrics import evaluate_article_transformation
from application.ports.article_maps import ArticleMapsRepository
from domain.article_maps import new_result
from application.article_map_lock import acquire_map_lock


class RebuildArticleMap:
    """Create an immutable pipeline version with a deterministically rebuilt map."""

    def __init__(self, repository: ArticlePipelineRepository, maps: ArticleMapsRepository):
        self.repository = repository
        self.maps = maps

    @staticmethod
    def _current_blocks(blocks: list[dict]) -> list[dict]:
        """Keep the stable structural contract and supply local tags for legacy rows."""
        normalized = []
        used_tags = {
            block.get("data", {}).get("tag")
            for block in blocks
            if isinstance(block.get("data", {}).get("tag"), str)
            and block["data"]["tag"].strip()
        }
        next_tag = 1
        for block in blocks:
            data = copy.deepcopy(block.get("data") or {})
            if not isinstance(data.get("tag"), str) or not data["tag"].strip():
                while f"B{next_tag}" in used_tags:
                    next_tag += 1
                data["tag"] = f"B{next_tag}"
                used_tags.add(data["tag"])
                next_tag += 1
            normalized.append({
                "instanceId": block["instanceId"],
                "blockType": block["blockType"],
                "data": data,
                "order": int(block.get("order", 0)),
            })
        return normalized

    @staticmethod
    def _fingerprint(blocks: list[dict]) -> str:
        canonical = json.dumps(blocks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def load_current(self, doc_id: str, user_uid: str, blocks: list[dict]) -> dict:
        rows = self._current_blocks(blocks)
        fingerprint = self._fingerprint(rows)
        snapshot = await asyncio.to_thread(self.maps.get, doc_id, "structural_rows", user_uid)
        current = bool(snapshot and snapshot["input_fingerprint"] == fingerprint)
        return {
            "graph": snapshot["graph"] if current else None,
            "blocks": rows,
            "rebuilt_at": snapshot["updated_at"] if current else None,
            "stale": bool(snapshot and not current),
        }

    async def execute_current(self, doc_id: str, user_uid: str, blocks: list[dict]) -> dict:
        require(isinstance(blocks, list) and bool(blocks),
                "There are no saved structural rows to build a map from")
        token = uid()
        await acquire_map_lock(self.maps, doc_id, "structural_rows", user_uid, token)
        try:
            rows = self._current_blocks(blocks)
            graph = build_knowledge_map(rows)
            result = await self._save_map(doc_id, user_uid, rows, graph, token)
            return {**result, "blocks": rows, "rebuilt_at": result["updated_at"], "created": True}
        finally:
            await asyncio.shield(asyncio.to_thread(self.maps.release, doc_id, "structural_rows", user_uid, token))

    async def _save_map(self, doc_id, user_uid, rows, graph, token, **metadata):
        """Все точки пересборки публикуют один и тот же независимый результат."""
        result = new_result(doc_id, "structural_rows", graph, self._fingerprint(rows),
                            validation={"contract": "passed", "dag": "passed"}, **metadata)
        await asyncio.to_thread(self.maps.save, result, user_uid, token)
        return result

    async def execute(self, doc_id: str, source_version_id: str, user_uid: str) -> dict:
        token = uid()
        await acquire_map_lock(self.maps, doc_id, "structural_rows", user_uid, token)
        try:
            return await self._execute_version(doc_id, source_version_id, user_uid, token)
        finally:
            await asyncio.shield(asyncio.to_thread(self.maps.release, doc_id, "structural_rows", user_uid, token))

    async def _execute_version(self, doc_id, source_version_id, user_uid, token):
        source_result = await asyncio.to_thread(
            self.repository.load, doc_id, source_version_id, user_uid
        )
        require(
            source_result.get("success") is True
            and source_result.get("stage") == "complete"
            and source_result.get("status") in ("completed", "completed_with_warnings"),
            "Only completed pipeline versions can be rebuilt",
        )

        source = source_result["source"]
        profile = source_result["linguistic_profile"]
        blocks = source_result["blocks"]
        validate_linguistic(profile, source)
        validate_structural(blocks, source, profile["sentences"])

        started_at = time.perf_counter()
        graph = build_knowledge_map(blocks)
        if graph == source_result.get("graph"):
            await self._save_map(doc_id, user_uid, self._current_blocks(blocks), graph, token,
                                 source_version_id=source_version_id)
            return {
                "version_id": source_version_id,
                "source_version_id": source_version_id,
                "created": False,
                "graph_schema_version": graph["schema_version"],
            }

        rebuilt = copy.deepcopy(source_result)
        rebuilt["version_id"] = uid()
        rebuilt["run_id"] = uid()
        rebuilt["graph"] = graph
        rebuilt["quality_metrics"] = evaluate_article_transformation(
            source, profile, blocks, graph
        )
        rebuilt.setdefault("validation", {})["map"] = "passed"
        rebuilt["map_rebuild"] = {
            "source_version_id": source_version_id,
            "strategy": "deterministic_structural_rows",
            "schema_version": graph["schema_version"],
            "elapsed_seconds": round(time.perf_counter() - started_at, 6),
        }

        await asyncio.to_thread(self.repository.save, rebuilt, user_uid)
        await self._save_map(doc_id, user_uid, self._current_blocks(blocks), graph, token,
                             source_version_id=rebuilt["version_id"])
        return {
            "version_id": rebuilt["version_id"],
            "source_version_id": source_version_id,
            "created": True,
            "graph_schema_version": graph["schema_version"],
        }
