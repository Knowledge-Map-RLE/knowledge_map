"""Составляет контекстный обзор предикатов без явной операторной маршрутизации."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import canonical, normalize
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import DICTIONARY_SHA256, PREDICATES, VERSION

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST = TRAINING / "training-corpus-manifest.json"
SEAL = TRAINING / "seal-receipt.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-predicate-census-v1" / "training21"
EXAMPLES_PER_PREDICATE = 3
REPORT_LIMIT = 30
EXCERPT_LIMIT = 520


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact(value, limit: int = EXCERPT_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def article_title(text: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return match.group(1).strip() if match else "Заголовок в источнике не найден"


def resolve_role(role: dict, concepts: dict, knowledge: dict) -> str:
    if role["concept_id"]:
        return concepts[role["concept_id"]]
    referenced = knowledge.get(role["knowledge_id"])
    return referenced["display_text"] if referenced else "[неизвестная ссылка]"


def main() -> None:
    require(not OUTPUT.exists(), "Выходной каталог уже существует; обзор не перезаписывает артефакты")
    manifest = load_json(MANIFEST)
    seal = load_json(SEAL)
    require(seal.get("sealed") is True and seal.get("training_count") == 21,
            "Ожидалась запечатанная обучающая выборка из 21 статьи")
    entries = manifest.get("sources", [])
    require(len(entries) == 21, "Манифест должен явно перечислять 21 карту")
    article_ids = [item["reference"]["article_id"] for item in entries]
    require(len(set(article_ids)) == 21 and "PMC10002471" not in " ".join(article_ids),
            "Цель не должна входить в обучающий реестр")

    grouped: dict[str, list[dict]] = defaultdict(list)
    source_hashes = {}
    graph_hashes = {}
    for entry in entries:
        path = Path(entry["path"]).resolve()
        raw = path.read_bytes()
        require(sha256(raw).hexdigest() == entry["file_sha256"], "Хеш карты не совпал с манифестом")
        snapshot = json.loads(raw)
        require(snapshot["article_id"] == entry["reference"]["article_id"]
                and snapshot["run_id"] == entry["reference"]["run_id"]
                and snapshot["pipeline_id"] == "text_reified", "Ссылка на запуск карты изменилась")
        graph = snapshot["graph"]
        require(graph.get("schema_version") == 6 and fingerprint(graph) == entry["graph_sha256"],
                "Схема или отпечаток графа изменились")
        validate_visible_dag(graph)
        source = snapshot["source"]
        require(sha256(source["text"].encode("utf-8")).hexdigest() == entry["source_sha256"],
                "Хеш полного текста источника не совпал")
        source_hashes[snapshot["article_id"]] = entry["source_sha256"]
        graph_hashes[snapshot["article_id"]] = entry["graph_sha256"]

        concepts = {item["id"]: item["display_text"] for item in graph["concepts"]}
        knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
        units = {item["id"]: item for item in source["units"]}
        title = article_title(source["text"])
        for item in graph["knowledge"]:
            for statement in item["semantic_frame"]["statements"]:
                predicate = canonical(statement["predicate"], "predicates")
                if predicate in PREDICATES:
                    continue
                excerpts = []
                for unit_id in statement["provenance"]["unit_ids"]:
                    unit = units.get(unit_id)
                    require(unit is not None, "Предикат ссылается на отсутствующий фрагмент источника")
                    require(source["text"][unit["start"]:unit["end"]] == unit["text"],
                            "Текст фрагмента не соответствует координатам источника")
                    excerpts.append(unit["text"])
                role_values = [
                    {"role": role["role"], "value": resolve_role(role, concepts, knowledge)}
                    for role in statement["roles"]
                ]
                grouped[predicate].append({
                    "article_id": snapshot["article_id"],
                    "title": title,
                    "knowledge_id": item["knowledge_id"],
                    "knowledge_text": item["display_text"],
                    "predicate": predicate,
                    "roles": role_values,
                    "negated": statement["negated"],
                    "quantifier": statement["quantifier"],
                    "modality": statement["modality"],
                    "time": statement["temporal_context"],
                    "conditions": statement["conditions"],
                    "attributes": statement["qualifiers"]["attributes"],
                    "source_excerpt": compact(" ".join(excerpts)),
                })

    records = []
    for predicate, examples in grouped.items():
        articles = sorted({row["article_id"] for row in examples})
        selected = []
        seen_articles = set()
        for row in examples:
            if row["article_id"] not in seen_articles:
                selected.append(row)
                seen_articles.add(row["article_id"])
                if len(selected) == EXAMPLES_PER_PREDICATE:
                    break
        records.append({
            "predicate": predicate,
            "occurrences": len(examples),
            "source_count": len(articles),
            "source_ids": articles,
            "examples": selected,
        })
    records.sort(key=lambda row: (-row["occurrences"], -row["source_count"], row["predicate"]))
    occurrence_count = sum(row["occurrences"] for row in records)
    require(occurrence_count == 1118 and len(records) == 717,
            "Количество неизвестных предикатов отличается от запечатанного аудита")

    data = {
        "version": "unregistered-predicate-semantic-census-1",
        "training_seal_run_id": seal["run_id"],
        "training_manifest_sha256": file_sha(MANIFEST),
        "routing_version": VERSION,
        "routing_dictionary_sha256": DICTIONARY_SHA256,
        "source_count": len(entries),
        "target_map_read": False,
        "model_calls": 0,
        "network_calls": 0,
        "unregistered_occurrences": occurrence_count,
        "unique_unregistered_predicates": len(records),
        "source_sha256": source_hashes,
        "graph_sha256": graph_hashes,
        "predicates": records,
    }
    data_raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    top_rows = []
    for row in records[:REPORT_LIMIT]:
        example = row["examples"][0]
        role_text = "; ".join(f"{item['role']}: {item['value']}" for item in example["roles"])
        top_rows.append(
            f"| `{row['predicate']}` | {row['occurrences']} | {row['source_count']} | "
            f"{compact(example['knowledge_text'], 180)} | {compact(role_text, 180)} |"
        )
    report = "\n".join([
        "# Контекст неизвестных предикатов в обучающих картах",
        "",
        "Этот аудит показывает, какие смысловые предикаты не попали в явный словарь операторных семейств и как они употреблены в самих картах. Он не меняет маршрутизацию, карты, обучающие примеры или прогнозы.",
        "",
        f"Проверено {len(entries)} запечатанных карт схемы 6. Найдено {occurrence_count} вхождений {len(records)} различных предикатов без маршрута. В таблице показаны первые {min(REPORT_LIMIT, len(records))} по частоте.",
        "",
        "| Предикат | Вхождений | Источников | Пример блока | Роли |",
        "|---|---:|---:|---|---|",
        *top_rows,
        "",
        "Полные контексты для трёх разных источников на предикат, включая исходный фрагмент, отрицание, время, условия, модальность и атрибуты, находятся в `data.json`. Одинаковая формулировка предиката сама по себе не доказывает семантическую эквивалентность. Предикаты частотой и контекстом нужно разбирать до включения в словарь.",
        "",
        "Проверка целостности подтвердила хеши карт, источников и графов; все графы прошли проверку DAG. Целевая PMC10002471 не читалась. Внешних и локальных модельных вызовов и сетевых запросов не было.",
        "",
    ]).encode("utf-8")
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "data.json").write_bytes(data_raw)
    (OUTPUT / "report.ru.md").write_bytes(report)
    verification = {
        "version": data["version"],
        "source_count": len(entries),
        "unregistered_occurrences": occurrence_count,
        "unique_unregistered_predicates": len(records),
        "all_maps_schema6_and_dag": True,
        "all_source_provenance_spans_verified": True,
        "target_map_read": False,
        "model_calls": 0,
        "network_calls": 0,
        "files": {
            "data.json": sha256(data_raw).hexdigest(),
            "report.ru.md": sha256(report).hexdigest(),
        },
    }
    (OUTPUT / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Источников: {len(entries)}; вхождений: {occurrence_count}; предикатов: {len(records)}")
    print(f"Выход: {OUTPUT.relative_to(ROOT)}")
    for row in records[:20]:
        print(f"{row['occurrences']:>3} | {row['source_count']:>2} | {row['predicate']}")


if __name__ == "__main__":
    main()
