"""Контрольная точка не допускает подмены источника, промпта или ответа."""
import json

import pytest

from domain.article_maps import ArticleMapError
from infrastructure.article_map_checkpoint import ExtractionCheckpointModel, metadata_path, write_checkpoint


@pytest.mark.asyncio
async def test_explicit_checkpoint_retains_original_model_metadata(tmp_path):
    path = tmp_path / "extraction.json"
    path.write_text('{"original":true}', encoding="utf-8")
    write_checkpoint(path, '{"original":true}', "prompt", "request", "source-hash",
                     {"model": "configured-profile", "usage": {"completion_tokens": 5}})
    model = ExtractionCheckpointModel(path, "source-hash")
    assert await model("prompt", "request") == '{"original":true}'
    assert model.last_call["model"] == "configured-profile"
    assert model.last_call["checkpoint_replayed"] is True


@pytest.mark.parametrize("field,value", [
    ("version", 2), ("stage", "dependencies"), ("source_sha256", "changed"),
    ("prompt_sha256", "changed"), ("request_sha256", "changed"),
    ("response_sha256", "changed"), ("model_call", {}),
])
@pytest.mark.asyncio
async def test_checkpoint_rejects_any_changed_binding(tmp_path, field, value):
    path = tmp_path / "extraction.json"
    path.write_text("{}", encoding="utf-8")
    write_checkpoint(path, "{}", "prompt", "request", "source", {"model": "configured"})
    metadata = json.loads(metadata_path(path).read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path(path).write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ArticleMapError):
        await ExtractionCheckpointModel(path, "source")("prompt", "request")
