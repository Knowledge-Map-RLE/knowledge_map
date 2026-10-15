"""Офлайн-аудит влияния явных алиасов на межстатейное сопоставление schema 6."""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.concept_alias_resolution import derive_unambiguous_aliases, resolve_concept_label
from domain.article_comparison import compare_knowledge
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools.import_codex_article_map import prohibit_generation


BASE = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1"
TRAINING = BASE / "training21"
RUN_ID = "602cbbdec2262ce9aa704c9bdabde89f74e1f2f35a48f8e30df54de3fd7059b2"
TARGET_PATH = BASE / "runs" / "86f921d6-7bb9-5cd3-a84a-befdc0e83854" / "map.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "concept-alias-transfer-diagnostic-v1" / "training21-pmc10002471-v1"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _rewrite_nested_roles(value, alias_index):
    if not isinstance(value, dict):
        return value
    rewritten = copy.deepcopy(value)
    for statement in rewritten.get("statements", []):
        for role in statement.get("roles", []):
            nested = role.get("value")
            role["value"] = (_rewrite_nested_roles(nested, alias_index) if isinstance(nested, dict)
                             else resolve_concept_label(nested, alias_index) if isinstance(nested, str)
                             else nested)
    return rewritten


def normalize_with_training_aliases(snapshot: dict, alias_index: dict) -> list[dict]:
    """Нормализует карту и заменяет только значения ролей-понятий."""
    rows = normalize_map(snapshot)
    for knowledge in rows:
        for statement in knowledge["statements"]:
            for role in statement["roles"]:
                value = role["value"]
                if role.get("reference_kind") == "concept" and isinstance(value, str):
                    role["value"] = resolve_concept_label(value, alias_index)
                elif role.get("reference_kind") == "knowledge":
                    role["value"] = _rewrite_nested_roles(value, alias_index)
    return rows


def _relation_key(result):
    return tuple(result["relations"])


def _relation_rank(result):
    relations = set(result["relations"])
    if "equivalent" in relations:
        return 4
    if "partial" in relations:
        return 3
    if "template" in relations:
        return 2
    if "topical" in relations:
        return 1
    if "contradiction" in relations:
        return -1
    return 0


def main():
    prohibit_generation()
    manifest_path = TRAINING / "training-corpus-manifest.json"
    seal_path = TRAINING / "seal-receipt.json"
    evaluation_path = TRAINING / "evaluation-receipt.json"
    prediction_path = TRAINING / "sealed" / RUN_ID / "predictions.json"
    manifest = _load_json(manifest_path)
    seal = _load_json(seal_path)
    evaluation = _load_json(evaluation_path)
    require(seal["sealed"] is True and seal["run_id"] == RUN_ID, "Прогноз не запечатан ожидаемым запуском")
    source_manifest_path = Path(manifest["metadata"]["source_manifest_path"])
    require(seal["source_manifest_sha256"] == _sha(source_manifest_path), "Манифест источников изменился после seal")
    require(seal["training_manifest_sha256"] == _sha(manifest_path), "Обучающий манифест изменился после seal")
    require(seal["prediction_sha256"] == fingerprint(_load_json(prediction_path)), "Запечатанный прогноз изменился")
    require(evaluation["run_id"] == RUN_ID and evaluation["target"]["article_id"] == "PMC10002471",
            "Квитанция оценки не соответствует удержанной статье")
    require(evaluation["target_file_sha256"] == _sha(TARGET_PATH), "Карта цели не совпадает с оценённой ревизией")
    require(evaluation["model_calls"] == 0 and seal.get("model_calls") == 0, "В квитанции обнаружен модельный вызов")

    repository = FileForecastMaps(manifest["sources"])
    sources = []
    for entry in manifest["sources"]:
        ref = entry["reference"]
        item = repository.get(ref["article_id"], ref["pipeline_id"], repository.owner, ref["run_id"])
        require(item is not None, "Источник отсутствует в явном манифесте")
        sources.append(item)
    target = _load_json(TARGET_PATH)
    require(target["article_id"] == "PMC10002471" and target["run_id"] == evaluation["target"]["run_id"],
            "Идентификатор карты цели изменился")

    # Индекс выводится исключительно из обучающих карт. Карта цели используется только оценщиком.
    alias_index = derive_unambiguous_aliases(sources)
    baseline_target = normalize_map(target)
    alias_target = normalize_with_training_aliases(target, alias_index)
    baseline_sources = [row for source in sources for row in normalize_map(source)]
    alias_sources = [row for source in sources for row in normalize_with_training_aliases(source, alias_index)]
    require(len(baseline_target) == len(alias_target), "Нормализация алиасов потеряла блоки цели")
    require(len(baseline_sources) == len(alias_sources), "Нормализация алиасов потеряла блоки источников")

    baseline_counts, alias_counts = Counter(), Counter()
    improvements, degradations, relation_changes = [], [], Counter()
    for left_base, left_alias in zip(baseline_target, alias_target):
        for right_base, right_alias in zip(baseline_sources, alias_sources):
            base = compare_knowledge(left_base, right_base)
            aliased = compare_knowledge(left_alias, right_alias)
            base_key, alias_key = _relation_key(base), _relation_key(aliased)
            baseline_counts["|".join(base_key)] += 1
            alias_counts["|".join(alias_key)] += 1
            if base_key != alias_key:
                relation_changes[f"{'|'.join(base_key)} -> {'|'.join(alias_key)}"] += 1
            delta = _relation_rank(aliased) - _relation_rank(base)
            record = {
                "target_article_id": left_base["article_id"],
                "target_knowledge_id": left_base["id"],
                "target_text": left_base["text"],
                "source_article_id": right_base["article_id"],
                "source_knowledge_id": right_base["id"],
                "source_text": right_base["text"],
                "baseline_relations": list(base_key),
                "alias_relations": list(alias_key),
                "baseline_score": base["semantic_score"],
                "alias_score": aliased["semantic_score"],
                "baseline_coverage_left": base["coverage_left"],
                "alias_coverage_left": aliased["coverage_left"],
                "statement_matches": aliased["statement_matches"],
                "delta_rank": delta,
            }
            if delta > 0:
                improvements.append(record)
            elif delta < 0:
                degradations.append(record)

    improvements.sort(key=lambda row: (-row["delta_rank"], -row["alias_score"], row["target_knowledge_id"], row["source_article_id"]))
    degradations.sort(key=lambda row: (row["delta_rank"], row["target_knowledge_id"], row["source_article_id"]))
    data = {
        "audit_version": "training-only-explicit-alias-transfer-1",
        "forecast_run_id": RUN_ID,
        "forecast_sealed": True,
        "prediction_sha256": seal["prediction_sha256"],
        "training_manifest_sha256": seal["source_manifest_sha256"],
        "target_file_sha256": evaluation["target_file_sha256"],
        "target_map_read_by_predictor": False,
        "target_map_used_by_this_post_seal_evaluator": True,
        "source_count": len(sources),
        "target_knowledge_count": len(baseline_target),
        "source_knowledge_count": len(baseline_sources),
        "pair_count": len(baseline_target) * len(baseline_sources),
        "alias_index": alias_index,
        "baseline_relation_counts": dict(sorted(baseline_counts.items())),
        "alias_relation_counts": dict(sorted(alias_counts.items())),
        "relation_changes": dict(sorted(relation_changes.items())),
        "improved_pair_count": len(improvements),
        "improved_target_count": len({row["target_knowledge_id"] for row in improvements}),
        "strict_positive_pair_count": sum(1 for row in improvements if any(r in row["alias_relations"] for r in ("equivalent", "partial"))),
        "strict_positive_target_count": len({row["target_knowledge_id"] for row in improvements if any(r in row["alias_relations"] for r in ("equivalent", "partial"))}),
        "degraded_pair_count": len(degradations),
        "improved_examples": improvements[:100],
        "degraded_examples": degradations[:30],
        "model_calls": 0,
        "network_calls": 0,
        "expert_validated": False,
        "interpretation_ru": "Послезапечатанный диагностический сравнитель; не является обученным свободным прогнозом."
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data_path = OUTPUT / "data.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "# Диагностика: явные алиасы понятий в межстатейном сопоставлении",
        "",
        "Это послезапечатанная оценка на прежнем корпусе; она не меняет и не переобучает сохранённый свободный прогноз.",
        "Индекс алиасов построен только по 21 обучающей карте. Карта PMC10002471 открыта лишь оценщиком после проверки seal.",
        "",
        f"- Запечатанный прогноз: `{RUN_ID}`; SHA-256: `{seal['prediction_sha256']}`.",
        f"- Пары: {data['pair_count']:,} ({data['target_knowledge_count']} знаний цели × {data['source_knowledge_count']} знаний источников).",
        f"- Обучающих источников: {len(sources)}; модельных и сетевых вызовов: 0.",
        f"- Однозначно объединённых компонентов подписей: {len(alias_index['merged_components'])}; неоднозначных алиасов: {len(alias_index['ambiguous_aliases'])}.",
        f"- Изменившихся пар: {sum(relation_changes.values()):,}; пар с ростом отношения: {len(improvements):,}; ухудшившихся: {len(degradations):,}.",
        f"- Улучшившихся до `partial` или `equivalent`: {data['strict_positive_pair_count']} пар в {data['strict_positive_target_count']} знаниях цели.",
        "",
        "## Распределение отношений до и после алиасов",
        "",
        "| Отношение | До | После |",
        "|---|---:|---:|",
    ]
    for relation in sorted(set(baseline_counts) | set(alias_counts)):
        report.append(f"| `{relation}` | {baseline_counts[relation]:,} | {alias_counts[relation]:,} |")
    report += ["", "## Новые положительные пары", ""]
    if not improvements:
        report.append("Явные обучающие алиасы не улучшили ни одной пары.")
    else:
        report += ["| Целевое знание | Источник | Отношение до → после | Оценки |", "|---|---|---|---:|"]
        for row in improvements[:30]:
            report.append(f"| {row['target_knowledge_id']}: {row['target_text']} | {row['source_article_id']} / {row['source_knowledge_id']}: {row['source_text']} | {', '.join(row['baseline_relations'])} → {', '.join(row['alias_relations'])} | {row['baseline_score']:.3f} → {row['alias_score']:.3f} |")
    report += [
        "",
        "## Ограничения",
        "",
        "Алиасы не являются независимым подтверждением факта. Положительная пара требует проверки ролей, отрицания, модальности, времени, чисел и исследовательской группы; сам рост сходства не считается успешным научным прогнозом. Целевая карта была вручную подготовлена Codex после чтения статьи, поэтому оценка не является слепой валидацией.",
        "",
        "Сравнение использует сохранённые карты schema 6 и детерминированные нормализатор/сравнитель. Оригинальные карты, запечатанный прогноз и их версии не изменялись.",
    ]
    report_path = OUTPUT / "report.ru.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    receipt = {
        "audit_version": data["audit_version"],
        "builder_sha256": _sha(Path(__file__)),
        "files": {name: _sha(OUTPUT / name) for name in ("data.json", "report.ru.md")},
        "model_calls": 0,
        "network_calls": 0,
        "forecast_seal_verified": True,
        "target_read_by_predictor": False,
    }
    (OUTPUT / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: data[k] for k in (
        "source_count", "target_knowledge_count", "source_knowledge_count", "pair_count",
        "improved_pair_count", "improved_target_count", "strict_positive_pair_count",
        "strict_positive_target_count", "degraded_pair_count", "relation_changes")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
