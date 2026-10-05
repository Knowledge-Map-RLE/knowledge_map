"""Явные контрольные точки CLI: связывание ответа с источником и полным запросом."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from domain.article_maps import digest, require


def metadata_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".metadata.json")


def write_checkpoint(path: Path, raw: str, system: str, user: str, source_sha256: str,
                     model_call: dict, *, stage: str = "extraction") -> None:
    metadata = {"version": 1, "stage": stage, "source_sha256": source_sha256,
                "prompt_sha256": digest(system), "request_sha256": digest(user),
                "response_sha256": digest(raw), "model_call": copy.deepcopy(model_call)}
    metadata_path(path).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


class ExtractionCheckpointModel:
    """Повторно использует только явно выбранный ответ; LLM-зависимости запускаются заново."""

    def __init__(self, path: Path, source_sha256: str):
        self.path, self.source_sha256 = path, source_sha256
        self.last_call = {}

    async def __call__(self, system: str, user: str) -> str:
        metadata = json.loads(metadata_path(self.path).read_text(encoding="utf-8"))
        raw = self.path.read_text(encoding="utf-8")
        require(metadata.get("version") == 1 and metadata.get("stage") == "extraction",
                "Not an extraction checkpoint")
        require(metadata.get("source_sha256") == self.source_sha256, "Checkpoint source changed")
        require(metadata.get("prompt_sha256") == digest(system), "Checkpoint prompt changed")
        require(metadata.get("request_sha256") == digest(user), "Checkpoint request changed")
        require(metadata.get("response_sha256") == digest(raw), "Checkpoint response changed")
        require(isinstance(metadata.get("model_call"), dict) and bool(metadata["model_call"]),
                "Checkpoint model metadata is missing")
        self.last_call = copy.deepcopy(metadata["model_call"]) | {
            "checkpoint_replayed": True, "checkpoint_response_sha256": digest(raw)}
        # Полный доменный контроль извлечения остаётся в production-сценарии TextToMap.
        return raw
