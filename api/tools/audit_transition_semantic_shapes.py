"""Сравнивает повторяемость авторских переходов при сохранении семантических ролей."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import canonical, normalize
from domain.development_prediction import validate_visible_dag


VERSION = "transition-semantic-shapes-diagnostic-1"
ROOT = Path(__file__).resolve().parents[2]
TARGET_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _knowledge_profile(item: dict) -> dict:
    frame = item["semantic_frame"]
    statements = []
    for statement in frame["statements"]:
        roles = sorted([
            {"role": canonical(role["role"], "roles"),
             "reference_type": "concept" if role["concept_id"] else "knowledge"}
            for role in statement["roles"]
        ], key=fingerprint)
        statements.append({
            "predicate": canonical(statement["predicate"], "predicates"),
            "roles": roles,
            "negated": statement["negated"],
            "quantifier": normalize(statement["quantifier"]) if statement["quantifier"] else None,
            "modality": normalize(statement["modality"]) if statement["modality"] else None,
        })
    return {
        "kind": item["kind"],
        "knowledge_kind": item["knowledge_kind"],
        "action_status": item["action_status"],
        "logic": frame["logic"],
        "statements": sorted(statements, key=fingerprint),
    }


def audit(manifest_path: Path) -> dict:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    require(len(manifest["sources"]) == 19, "Ожидались ровно 19 карт схемы 6")
    coarse, semantic, records = [], [], []
    source_map_hashes, graph_hashes = {}, {}
    article_ids = set()

    for entry in manifest["sources"]:
        map_bytes = Path(entry["path"]).read_bytes()
        require(digest(map_bytes) == entry["file_sha256"], "Хеш карты не совпал с манифестом")
        article = json.loads(map_bytes.decode("utf-8"))
        article_id = article["article_id"]
        require(article_id == entry["reference"]["article_id"], "Идентификатор карты не совпал")
        require(article_id not in article_ids, "Повторная статья в манифесте")
        article_ids.add(article_id)
        require(article["graph_schema_version"] == 6, "Аудит поддерживает только схему 6")
        graph = article["graph"]
        require(fingerprint(graph) == entry["graph_sha256"], "Хеш графа не совпал с манифестом")
        validate_visible_dag(graph)
        source_map_hashes[article_id] = digest(map_bytes)
        graph_hashes[article_id] = entry["graph_sha256"]

        nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
        knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
        profiles = {key: _knowledge_profile(item) for key, item in knowledge.items()}
        for transition in graph["transitions"]:
            usage = transition.get("usage")
            require(isinstance(usage, str) and usage.strip(), "У перехода отсутствует метка операции")
            source_ids = [nodes[node_id] for node_id in transition["sources"]]
            target_id = nodes[transition["target"]]
            source_types = sorted(
                f"{knowledge[key]['kind']}/{knowledge[key]['knowledge_kind']}" for key in source_ids
            )
            target_type = f"{knowledge[target_id]['kind']}/{knowledge[target_id]['knowledge_kind']}"
            coarse_signature = {
                "usage": usage,
                "arity": len(source_ids),
                "source_types": source_types,
                "target_type": target_type,
            }
            semantic_signature = {
                "usage": usage,
                "arity": len(source_ids),
                "source_profiles": sorted((profiles[key] for key in source_ids), key=fingerprint),
                "target_profile": profiles[target_id],
            }
            coarse.append((article_id, fingerprint(coarse_signature), coarse_signature))
            semantic.append((article_id, fingerprint(semantic_signature), semantic_signature))
            records.append({
                "article_id": article_id,
                "transition_id": transition["id"],
                "coarse_signature_id": fingerprint(coarse_signature),
                "semantic_signature_id": fingerprint(semantic_signature),
                "source_ids": source_ids,
                "target_id": target_id,
                "usage": usage,
            })

    require(all(entry["reference"]["article_id"] != "PMC10000452"
                and entry["source_sha256"] != TARGET_SOURCE_SHA256 for entry in manifest["sources"]),
            "Целевая статья найдена среди обучающих карт")

    summaries = {}
    signature_values = {}
    for level, rows in (("coarse", coarse), ("semantic", semantic)):
        counts, supporting_articles = Counter(), defaultdict(set)
        for article_id, signature_id, signature in rows:
            counts[signature_id] += 1
            supporting_articles[signature_id].add(article_id)
            signature_values[signature_id] = signature
        recurring = []
        for signature_id, count in counts.items():
            supporters = sorted(supporting_articles[signature_id])
            if len(supporters) < 2:
                continue
            recurring.append({
                "signature_id": signature_id,
                "signature": signature_values[signature_id],
                "transition_count": count,
                "article_count": len(supporters),
                "article_ids": supporters,
                "inference_licensed": False,
            })
        recurring.sort(key=lambda item: (-item["article_count"], -item["transition_count"], item["signature_id"]))
        summaries[level] = {
            "transition_count": len(rows),
            "unique_signature_count": len(counts),
            "recurrent_signature_count": len(recurring),
            "recurrent_signatures": recurring,
        }

    return {
        "version": VERSION,
        "manifest_sha256": digest(manifest_bytes),
        "source_count": len(article_ids),
        "canonical_knowledge_count": sum(
            len(json.loads(Path(entry["path"]).read_bytes())["graph"]["knowledge"])
            for entry in manifest["sources"]),
        "transition_count": len(records),
        "model_calls": 0,
        "network_calls": 0,
        "target_read": False,
        "semantic_signature_dimensions": [
            "usage", "premise arity", "knowledge kind", "action status", "frame logic",
            "normalized predicates", "semantic role names", "negation", "quantifier", "modality",
        ],
        "omitted_dimensions": [
            "participant identities", "context", "time", "conditions", "numeric values", "units",
            "study design", "population", "transition reason", "provenance independence",
        ],
        "publication_count_is_not_independence": True,
        "levels": summaries,
        "transition_records": records,
        "source_map_sha256": source_map_hashes,
        "source_graph_sha256": graph_hashes,
    }


def render_report(data: dict) -> str:
    coarse = data["levels"]["coarse"]
    semantic = data["levels"]["semantic"]
    lines = [
        "# Повторяемость авторских переходов с учётом семантических ролей",
        "",
        "**Это диагностический поиск операторных форм, а не прогноз научных результатов.** Сравнение показывает, сохраняются ли повторения после добавления видов знаний, действий, логики, нормализованных предикатов и ролей.",
        "",
        f"Проверено {data['source_count']} карт, {data['canonical_knowledge_count']} знаний и {data['transition_count']} переходов. Хеши карт и графов сверены с манифестом; целевая PMC10000452 не читалась.",
        "",
        "| Уровень сигнатуры | Разных форм | Форм повторяется в ≥2 статьях |",
        "|---|---:|---:|",
        f"| Грубый: метка операции, число входов и виды знаний | {coarse['unique_signature_count']} | {coarse['recurrent_signature_count']} |",
        f"| Семантический: дополнительно действия, логика, предикаты, роли, отрицания, кванторы и модальность | {semantic['unique_signature_count']} | {semantic['recurrent_signature_count']} |",
        "",
        "Семантическая сигнатура намеренно не включает тождества участников, популяции, время, условия, числа, единицы, дизайн или независимость первичных данных. Поэтому даже её повтор не разрешает переносить содержательный вывод.",
        "",
        "## Повторяемые семантические формы",
        "",
        "| Метка | Входы | Выход | Переходов | Статей |",
        "|---|---|---|---:|---:|",
    ]
    for row in semantic["recurrent_signatures"][:20]:
        signature = row["signature"]
        source_labels = []
        for profile in signature["source_profiles"]:
            predicates = ", ".join(sorted({statement["predicate"] for statement in profile["statements"]}))
            roles = ", ".join(sorted({role["role"] for statement in profile["statements"] for role in statement["roles"]}))
            source_labels.append(f"{profile['knowledge_kind']}: {predicates}; роли: {roles}")
        target = signature["target_profile"]
        target_predicates = ", ".join(sorted({statement["predicate"] for statement in target["statements"]}))
        target_roles = ", ".join(sorted({role["role"] for statement in target["statements"] for role in statement["roles"]}))
        lines.append(
            f"| {signature['usage']} | {'<br>'.join(source_labels)} | {target['knowledge_kind']}: {target_predicates}; роли: {target_roles} | {row['transition_count']} | {row['article_count']} |"
        )
    if not semantic["recurrent_signatures"]:
        lines.append("| — | Нет форм с повтором в нескольких статьях | — | 0 | 0 |")
    lines.extend([
        "",
        "## Интерпретация",
        "",
        f"При грубом сравнении повторялись {coarse['recurrent_signature_count']} формы. После сохранения нормализованного содержания фреймов осталось {semantic['recurrent_signature_count']}. Это число — число шаблонов организации переходов, не число подтверждённых научных правил.",
        "",
        "Следующий тест для любого оставшегося мотива должен удерживать целиком статьи или семейства источников, раскрывать контексты только оценщику, сравнивать исходный DAG с теми же знаниями без рёбер и контролем с переставленными зависимостями. Числа и условия применимости нужно проверять отдельно; публикации, описывающие одну когорту, не считать независимыми подтверждениями.",
        "",
        "## Воспроизводимость",
        "",
        f"Версия: `{data['version']}`. Манифест SHA-256: `{data['manifest_sha256']}`. Модельных и сетевых вызовов — 0. Все сигнатуры помечены `inference_licensed=false`.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Диагностика повторяемости семантических форм переходов")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = audit(args.manifest)
    implementation = Path(__file__).read_bytes()
    data["implementation_sha256"] = digest(implementation)
    args.output.mkdir(parents=True, exist_ok=False)
    data["report_ru_md"] = render_report(data)
    (args.output / "audit.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "report.ru.md").write_text(data["report_ru_md"], encoding="utf-8")
    (args.output / "implementation.py").write_bytes(implementation)
    print(json.dumps({
        "output": str(args.output), "sources": data["source_count"],
        "transitions": data["transition_count"],
        "coarse_recurrent": data["levels"]["coarse"]["recurrent_signature_count"],
        "semantic_recurrent": data["levels"]["semantic"]["recurrent_signature_count"],
        "model_calls": 0, "network_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
