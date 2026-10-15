"""Строит неизменяемый реестр для проверки только явных переходов результата."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_result_transfer import VERSION, extract_map
from domain.cohort_operation_transfer import extract_map as extract_all_usage_map
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7/source-manifest.json"
OUTPUT = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/result-usage-lopo-v1"
HELD_OUT_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def main() -> None:
    disable_network()
    base_raw = BASE_MANIFEST.read_bytes()
    base = json.loads(base_raw)
    require(len(base.get("sources", [])) == 16, "Ожидались 16 сохранённых источников")
    sources = []
    for entry in base["sources"]:
        path = Path(entry["map_path"])
        raw = path.read_bytes()
        require(_sha(raw) == entry["map_sha256"], "Хеш исходной карты изменился")
        snapshot = json.loads(raw)
        require(snapshot["article_id"] == entry["article_id"], "Идентификатор карты изменился")
        require(snapshot["source"]["sha256"] == entry["source_sha256"] != HELD_OUT_SOURCE_SHA256,
                "Обнаружен неверный источник или целевая статья")
        all_usage = extract_all_usage_map(snapshot)
        result_usage = extract_map(snapshot)
        require({tuple(pair) for pair in result_usage["graph_links"]}
                <= {tuple(pair) for pair in all_usage["graph_links"]},
                "Фильтр результата добавил недоказанную связь")
        sources.append({
            **entry,
            "all_usage_graph_link_count": len(all_usage["graph_links"]),
            "result_usage_graph_link_count": len(result_usage["graph_links"]),
            "transition_usage_filter": "result",
        })

    result = {
        "protocol": VERSION,
        "base_manifest_sha256": _sha(base_raw),
        "minimum_publication_support": 2,
        "target_source_sha256_excluded": HELD_OUT_SOURCE_SHA256,
        "transition_usage_filter": "result",
        "sources": sources,
        "implementation_sha256": {
            "result_adapter": _sha((ROOT / "api/domain/cohort_operation_result_transfer.py").read_bytes()),
            "base_adapter": _sha((ROOT / "api/domain/cohort_operation_transfer.py").read_bytes()),
            "forecast": _sha((ROOT / "api/domain/sealed_operation_result_forecast.py").read_bytes()),
            "runner": _sha(Path(__file__).read_bytes()),
        },
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "expert_validated": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_immutable(OUTPUT / "source-manifest.json", _json_bytes(result))
    print(json.dumps({"output": str(OUTPUT / "source-manifest.json"),
                      "source_count": len(sources),
                      "all_usage_links": sum(row["all_usage_graph_link_count"] for row in sources),
                      "result_usage_links": sum(row["result_usage_graph_link_count"] for row in sources),
                      "model_calls": 0, "network_disabled": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
