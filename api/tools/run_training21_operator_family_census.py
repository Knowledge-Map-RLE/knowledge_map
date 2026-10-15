"""Проверяет повторяемость семейств операторов только на 21 обучающей карте."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map, VERSION as NORMALIZER_VERSION
from domain.operator_frame_routing import (DICTIONARY_SHA256 as ROUTING_SHA256,
                                           PREDICATES, VERSION as ROUTING_VERSION)
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools.import_codex_article_map import prohibit_generation


BASE = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1"
TRAINING = BASE / "training21"
MANIFEST_PATH = TRAINING / "training-corpus-manifest.json"
SEAL_PATH = TRAINING / "seal-receipt.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-family-census-v1" / "training21"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path):
    return sha256(path.read_bytes()).hexdigest()


def pattern_key(statement, knowledge, predicate):
    return fingerprint({
        "predicate_or_family": predicate,
        "kind": knowledge["kind"],
        "action_status": knowledge["action_status"],
        "roles": sorted(role["role"] for role in statement["roles"]),
        "negated": statement["negated"],
        "logic": knowledge["logic"],
    })


def eligible_signature(statement, knowledge, predicate, article_id):
    scope = {"scope": statement["scope"], "attributes": statement["attributes"],
             "action_status": knowledge["action_status"], "logic": knowledge["logic"]}
    if scope["scope"]["study_group"] is not None:
        scope["scope"]["study_group"] = "source-local-cohort-variable"
    return fingerprint({
        "predicate_or_family": predicate,
        "kind": knowledge["kind"],
        "roles": sorted(role["role"] for role in statement["roles"]),
        "scope": scope,
        "negated": statement["negated"],
    })


def summarize_support(sources):
    return {
        "form_count": len(sources),
        "form_support_ge_2": sum(len(ids) >= 2 for ids in sources.values()),
        "form_support_ge_3": sum(len(ids) >= 3 for ids in sources.values()),
        "support_distribution": {
            str(n): sum(len(ids) == n for ids in sources.values())
            for n in sorted({len(ids) for ids in sources.values()})
        },
    }


def main():
    prohibit_generation()
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    require(seal["sealed"] is True and seal["training_count"] == 21, "Ожидался запечатанный корпус из 21 источника")
    require(seal["source_manifest_sha256"] == digest(source_manifest), "Исходный манифест источников изменился")
    require(seal["training_manifest_sha256"] == digest(MANIFEST_PATH), "Обучающий манифест изменился")
    require(seal["target_map_read"] is False and seal["target_map_path_passed"] is False,
            "Карта цели была доступна при прогнозе")
    require(seal["model_calls"] == 0, "Запечатанный прогноз содержит модельные вызовы")

    repository = FileForecastMaps(manifest["sources"])
    refs = [item["reference"] for item in manifest["sources"]]
    snapshots = [repository.get(ref["article_id"], ref["pipeline_id"], repository.owner, ref["run_id"])
                 for ref in refs]
    require(len(snapshots) == 21 and all(item is not None for item in snapshots), "Не все обучающие карты загружены")

    predicate_sources = defaultdict(set)
    family_sources = defaultdict(set)
    exact_skeleton_sources = defaultdict(set)
    family_skeleton_sources = defaultdict(set)
    family_skeleton_predicate_sources = defaultdict(lambda: defaultdict(set))
    family_skeleton_examples = defaultdict(list)
    exact_eligible_sources = defaultdict(set)
    family_eligible_sources = defaultdict(set)
    routed_statement_count = changed_statement_count = total_statements = eligible_count = 0
    per_family_counts = defaultdict(lambda: {"statement_count": 0, "source_ids": set(), "predicates": set()})

    for snapshot in snapshots:
        article_id = snapshot["article_id"]
        for knowledge in normalize_map(snapshot):
            for statement in knowledge["statements"]:
                total_statements += 1
                predicate = statement["predicate"]
                family = PREDICATES.get(predicate)
                routed = "operator-family:" + family if family else "unrouted:" + predicate
                predicate_sources[predicate].add(article_id)
                family_sources[routed].add(article_id)
                exact_key = pattern_key(statement, knowledge, predicate)
                family_key = pattern_key(statement, knowledge, routed)
                exact_skeleton_sources[exact_key].add(article_id)
                family_skeleton_sources[family_key].add(article_id)
                family_skeleton_predicate_sources[family_key][predicate].add(article_id)
                if (len(family_skeleton_examples[family_key]) < 8
                        and not any(row["article_id"] == article_id for row in family_skeleton_examples[family_key])):
                    family_skeleton_examples[family_key].append({
                        "article_id": article_id, "knowledge_id": knowledge["id"],
                        "text": knowledge["text"], "predicate": predicate,
                        "operator_family": family, "roles": sorted(role["role"] for role in statement["roles"]),
                        "kind": knowledge["kind"], "action_status": knowledge["action_status"],
                        "negated": statement["negated"], "logic": knowledge["logic"],
                        "unknown_context": statement["unknown_context"],
                        "scope": statement["scope"], "attributes": statement["attributes"],
                    })
                if family:
                    routed_statement_count += 1
                    changed_statement_count += int(routed != predicate)
                    row = per_family_counts[family]
                    row["statement_count"] += 1
                    row["source_ids"].add(article_id)
                    row["predicates"].add(predicate)
                if statement["unknown_context"] or knowledge["logic"] not in {"single", "conjunction"}:
                    continue
                eligible_count += 1
                exact_eligible_sources[eligible_signature(statement, knowledge, predicate, article_id)].add(article_id)
                family_eligible_sources[eligible_signature(statement, knowledge, routed, article_id)].add(article_id)

    exact_skeleton_summary = summarize_support(exact_skeleton_sources)
    family_skeleton_summary = summarize_support(family_skeleton_sources)
    exact_eligible_summary = summarize_support(exact_eligible_sources)
    family_eligible_summary = summarize_support(family_eligible_sources)
    repeated_family_skeletons = []
    family_induced_repeats = 0
    for key, source_ids in family_skeleton_sources.items():
        if len(source_ids) >= 2:
            exact_predicate_support = {
                predicate: sorted(ids) for predicate, ids in family_skeleton_predicate_sources[key].items()
            }
            if not any(len(ids) >= 2 for ids in family_skeleton_predicate_sources[key].values()):
                family_induced_repeats += 1
            repeated_family_skeletons.append({"signature": key, "source_ids": sorted(source_ids),
                                              "support": len(source_ids),
                                              "exact_predicate_support": exact_predicate_support,
                                              "family_induced": not any(
                                                  len(ids) >= 2 for ids in family_skeleton_predicate_sources[key].values()),
                                              "examples": family_skeleton_examples[key][:6]})
    repeated_family_skeletons.sort(key=lambda row: (-row["support"], row["signature"]))

    # Считаем точные формы, которые стали межстатейными только после семейной маршрутизации.
    added_repeated_skeleton_count = family_induced_repeats
    result = {
        "audit_version": "operator-family-census-training21-1",
        "training_manifest_sha256": digest(MANIFEST_PATH),
        "source_manifest_sha256": digest(source_manifest),
        "forecast_run_id": seal["run_id"],
        "forecast_seal_prediction_sha256": seal["prediction_sha256"],
        "target_article_id": "PMC10002471",
        "target_map_read": False,
        "source_count": len(snapshots),
        "statement_count": total_statements,
        "eligible_statement_count": eligible_count,
        "normalizer_version": NORMALIZER_VERSION,
        "operator_routing_version": ROUTING_VERSION,
        "operator_routing_dictionary_sha256": ROUTING_SHA256,
        "routed_statement_count": routed_statement_count,
        "routed_statement_fraction": round(routed_statement_count / total_statements, 6),
        "registered_family_count_used": len(per_family_counts),
        "family_summary": {name: {**row, "source_ids": sorted(row["source_ids"]), "predicates": sorted(row["predicates"])}
                           for name, row in sorted(per_family_counts.items())},
        "predicate_type_support": summarize_support(predicate_sources),
        "routed_family_support": summarize_support(family_sources),
        "exact_structural_skeleton_support": exact_skeleton_summary,
        "operator_family_structural_skeleton_support": family_skeleton_summary,
        "exact_eligible_signature_support": exact_eligible_summary,
        "operator_family_eligible_signature_support": family_eligible_summary,
        "added_repeated_skeleton_count": added_repeated_skeleton_count,
        "repeated_family_skeletons": repeated_family_skeletons,
        "model_calls": 0,
        "network_calls": 0,
        "scientific_predictions_generated": False,
        "interpretation_ru": "Семейство оператора группирует форму; не доказывает эквивалентность фактов и не разрешает перенос."}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    data_path = OUTPUT / "data.json"
    data_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "# Повторяемость семейств операторов в 21 обучающей карте",
        "",
        "Аудит читает только явные источники запечатанного обучения. Удержанная карта PMC10002471 не открывалась. Зарегистрированное семейство используется как группировка формы, а не как доказательство равенства утверждений.",
        "",
        f"- Источников: {len(snapshots)}; утверждений: {total_statements:,}; допустимых по контексту и логике: {eligible_count:,}.",
        f"- Маршрутизовано в семейства: {routed_statement_count:,} ({result['routed_statement_fraction']:.1%}); семейств встретилось: {len(per_family_counts)}.",
        f"- Точные структурные формы с поддержкой минимум двух источников: {exact_skeleton_summary['form_support_ge_2']} из {exact_skeleton_summary['form_count']:,}.",
        f"- После свёртки зарегистрированных предикатов в семейства: {family_skeleton_summary['form_support_ge_2']} из {family_skeleton_summary['form_count']:,}.",
        f"- Строгие формы с контекстом, числами и атрибутами, повторившиеся между источниками: {exact_eligible_summary['form_support_ge_2']} точных; {family_eligible_summary['form_support_ge_2']} семейных.",
        f"- Новых повторяющихся структурных форм после маршрутизации: {added_repeated_skeleton_count}.",
        "",
        "## Семейства и охват",
        "",
        "| Семейство | Утверждений | Источников | Исходных предикатов |",
        "|---|---:|---:|---:|",
    ]
    for family, row in sorted(per_family_counts.items(), key=lambda item: (-item[1]["statement_count"], item[0])):
        report.append(f"| `{family}` | {row['statement_count']} | {len(row['source_ids'])} | {len(row['predicates'])} |")
    report += ["", "## Повторившиеся формы после маршрутизации", ""]
    if not repeated_family_skeletons:
        report.append("Ни одна форма с сохранением ролей, вида знания, статуса действия, отрицания и логики не повторилась в нескольких источниках.")
    else:
        for item in repeated_family_skeletons[:20]:
            example = item["examples"][0]
            family_name = example["operator_family"] or "без зарегистрированного семейства"
            role_names = ", ".join(example["roles"])
            origin = "новый повтор только после группировки" if item["family_induced"] else "точный повтор уже был"
            report.append(f"### `{family_name}` · {example['kind']} · роли: {role_names} · поддержка {item['support']} · {origin}")
            report.append("")
            for predicate, ids in sorted(item["exact_predicate_support"].items()):
                report.append(f"- Предикат `{predicate}`: {len(ids)} источник(а/ов) — {', '.join(ids)}.")
            for example in item["examples"]:
                report.append(f"- {example['article_id']} / {example['knowledge_id']} — предикат `{example['predicate']}`, роли `{', '.join(example['roles'])}`: {example['text']}")
            report.append("")
    report += [
        "## Вывод и границы",
        "",
        "Рост повторяемости после маршрутизации означает только, что разные предикаты попали в одну заранее зарегистрированную категорию. Он не устанавливает, что отношения, исходы, роли, единицы, популяции и сроки взаимозаменяемы. Эти совпадения могут подсказать кандидатов для отдельной проверки, но до такой проверки они не являются правилами прогноза.",
        "",
        "Прогноз и карты не изменялись. Модельных и сетевых вызовов нет. Квитанция seal, оба манифеста, версии карт и происхождение проверены перед чтением.",
    ]
    report_path = OUTPUT / "report.ru.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    receipt = {
        "audit_version": result["audit_version"],
        "builder_sha256": digest(Path(__file__)),
        "files": {name: digest(OUTPUT / name) for name in ("data.json", "report.ru.md")},
        "forecast_seal_verified": True,
        "target_map_read": False,
        "model_calls": 0,
        "network_calls": 0,
    }
    (OUTPUT / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "source_count", "statement_count", "eligible_statement_count", "routed_statement_count",
        "registered_family_count_used", "predicate_type_support", "routed_family_support",
        "exact_structural_skeleton_support", "operator_family_structural_skeleton_support",
        "exact_eligible_signature_support", "operator_family_eligible_signature_support",
        "added_repeated_skeleton_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
