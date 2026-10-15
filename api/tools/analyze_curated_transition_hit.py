"""Раскрывает контексты единственной грубой формы, совпавшей на удержанной цели."""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag
from tools import run_training21_operator_transition_lopo as baseline
from tools.operator_route_experiment import shape, shape_id

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST = TRAINING / "training-corpus-manifest.json"
TARGET_META = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "heldout-target.json"
TARGET_MAP = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "runs" / "86f921d6-7bb9-5cd3-a84a-befdc0e83854" / "map.json"
SEALED_DIR = ROOT / "eval" / "whole_map_forecast" / "curated-operator-route-v1" / "pmc10002471" / "sealed" / "5424c1da25628b4d64117970bac19c99fde27949e26b24c0851d79254ff134d5"
EVAL_DIR = ROOT / "eval" / "whole_map_forecast" / "curated-operator-route-v1" / "pmc10002471" / "evaluation" / "5424c1da25628b4d64117970bac19c99fde27949e26b24c0851d79254ff134d5"
OUTPUT = EVAL_DIR / "qualitative-shape-hit"
TARGET_BUDGET = "50"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def title(snapshot: dict) -> str:
    for line in snapshot["source"]["text"].splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return snapshot["article_id"]


def transition_rows(snapshot: dict) -> list[dict]:
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    rows = []
    for transition in graph["transitions"]:
        source_ids = [nodes[key] for key in transition["sources"]]
        target_id = nodes[transition["target"]]
        if len(source_ids) > 3:
            continue
        source_types = [knowledge[key]["kind"] + "/" + knowledge[key]["knowledge_kind"]
                        for key in source_ids]
        target_type = knowledge[target_id]["kind"] + "/" + knowledge[target_id]["knowledge_kind"]
        rows.append({
            "shape": shape(source_types, target_type),
            "sources": [{"knowledge_id": key, "text": knowledge[key]["display_text"]}
                        for key in source_ids],
            "target": {"knowledge_id": target_id, "text": knowledge[target_id]["display_text"]},
        })
    return rows


def render_transition(item: dict, article_id: str, article_title: str) -> dict:
    return {
        "article_id": article_id,
        "title": article_title,
        "sources": item["sources"],
        "target": item["target"],
    }


def main() -> None:
    require(not OUTPUT.exists(), "Контекстная проверка уже создана и не перезаписывается")
    predictions_path = SEALED_DIR / "predictions.json"
    seal = load_json(SEALED_DIR / "seal-receipt.json")
    predictions_raw = predictions_path.read_bytes()
    predictions = json.loads(predictions_raw)
    require(seal["sealed"] and seal["prediction_sha256"] == sha256(predictions_raw).hexdigest()
            and predictions["target_map_read"] is False,
            "Запечатанный прогноз не прошёл проверку перед анализом попадания")
    target_meta = load_json(TARGET_META)
    target_raw = TARGET_MAP.read_bytes()
    require(sha256(target_raw).hexdigest() == target_meta["file_sha256"],
            "Хеш карты цели изменился")
    target = json.loads(target_raw)
    require(target["article_id"] == "PMC10002471"
            and target["run_id"] == target_meta["reference"]["run_id"],
            "Карта цели имеет другой идентификатор")

    selected = predictions["modes"]["coarse"]["graph"][TARGET_BUDGET]
    predicted = {shape_id(item["shape"]): item for item in selected}
    target_rows = transition_rows(target)
    target_hits = [row for row in target_rows if shape_id(row["shape"]) in predicted]
    # Берётся единственная форма, отмеченная оценщиком как совпавшая при @50.
    hit_ids = {shape_id(row["shape"]) for row in target_hits}
    expected = {
        shape_id({"arity": 3,
                  "source_types": ["state/limitation", "state/result", "state/result"],
                  "target_type": "state/conclusion"})
    }
    require(hit_ids == expected, "Качественный hit не совпал с зафиксированной сводкой оценки")

    manifest = load_json(MANIFEST)
    training_examples = []
    for entry in manifest["sources"]:
        reference = entry["reference"]
        path = Path(entry["path"])
        raw = path.read_bytes()
        require(sha256(raw).hexdigest() == entry["file_sha256"], "Изменилась обучающая карта")
        snapshot = json.loads(raw)
        require(fingerprint(snapshot["graph"]) == entry["graph_sha256"], "Изменился граф обучающей карты")
        for transition in transition_rows(snapshot):
            if shape_id(transition["shape"]) == next(iter(expected)):
                training_examples.append(render_transition(
                    transition, reference["article_id"], title(snapshot)))

    target_examples = [render_transition(row, target["article_id"], title(target))
                       for row in target_hits]
    require(len({item["article_id"] for item in training_examples}) >= 2,
            "Предсказанный структурный шаблон не имеет межстатейной поддержки")
    data = {
        "version": "curated-transition-hit-context-review-1",
        "forecast_run_id": seal["run_id"],
        "forecast_sha256": seal["prediction_sha256"],
        "target_map_sha256": target_meta["file_sha256"],
        "target_was_previously_read_by_codex": True,
        "prediction_budget": int(TARGET_BUDGET),
        "matched_shape": {
            "arity": 3,
            "source_types": ["state/limitation", "state/result", "state/result"],
            "target_type": "state/conclusion",
        },
        "target_matches": target_examples,
        "training_support": training_examples,
        "unique_supporting_articles": len({item["article_id"] for item in training_examples}),
        "model_calls": 0,
        "network_calls": 0,
    }

    def md(value: str) -> str:
        return " ".join(value.split()).replace("|", "\\|")

    lines = [
        "# Качественный разбор единственного грубого совпадения",
        "",
        "Прогноз при @50 совпал с одной формой перехода цели: **три входа — одно ограничение и два результата — ведут к заключению**. Эта форма поддержана в обучении несколькими разными статьями.",
        "",
        f"Целевая статья: **{title(target)}** (`PMC10002471`). Карта цели была открыта после проверки seal, но Codex ранее читал статью, чтобы вручную составить её карту; оценка алгоритмическая, не слепая для автора карты.",
        "",
        "## Целевой переход",
        "",
    ]
    for item in target_examples:
        for source in item["sources"]:
            lines.append(f"- Предпосылка ({source['knowledge_id']}): {md(source['text'])}")
        lines.append(f"- Заключение ({item['target']['knowledge_id']}): {md(item['target']['text'])}")
    lines += ["", "## Поддержавшие переходы в обучении", ""]
    for item in training_examples:
        lines.append(f"### {item['title']} (`{item['article_id']}`)")
        for source in item["sources"]:
            lines.append(f"- Предпосылка ({source['knowledge_id']}): {md(source['text'])}")
        lines.append(f"- Заключение ({item['target']['knowledge_id']}): {md(item['target']['text'])}")
        lines.append("")
    lines += [
        "## Интерпретация",
        "",
        "Совпадение подтверждает перенос только **композиции аргумента**: автор ограничивает интерпретацию, приводит несколько результатов и формулирует заключение. Поддерживающие переходы могут отличаться по теме, измерениям и содержанию. Поэтому это полезный шаблон структуры научного рассуждения, но он не предсказывает, какое именно ограничение или результат будет в новой статье.",
        "",
        "При @20 совпадений этого типа не было; при @50 грубый режим дал 1 из 50 форм, а режим без рёбер — 0 из 50. Точность равна 2%; перестановочный контроль для уточнённых операторных семейств дал 0 совпадений и не относится напрямую к этому грубому типу. После добавления предикатов и формы ролей совпадений не осталось. Значит, наблюдение поддерживает общую структуру аргумента, но не показывает преимуществ семантической Карты в прогнозировании научных знаний.",
        "",
        "Модельных и сетевых вызовов — 0. Исходные карты не изменены.",
        "",
    ]
    report_raw = "\n".join(lines).encode("utf-8")
    data_raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "report.ru.md").write_bytes(report_raw)
    (OUTPUT / "data.json").write_bytes(data_raw)
    verification = {
        "version": data["version"],
        "forecast_seal_valid": True,
        "target_match_reconciled_with_evaluation": True,
        "supporting_training_maps_hash_checked": True,
        "model_calls": 0,
        "network_calls": 0,
        "files": {"report.ru.md": sha256(report_raw).hexdigest(),
                  "data.json": sha256(data_raw).hexdigest()},
    }
    (OUTPUT / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"qualitative_support={len({item['article_id'] for item in training_examples})} articles")
    print(f"analysis={OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
