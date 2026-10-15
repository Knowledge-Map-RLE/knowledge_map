"""Разбирает совпавшие формы переходов и проверяет их семантическое усиление."""
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
from domain.development_prediction import validate_visible_dag
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_operator_transition_lopo as family_audit
from tools import run_training21_role_type_transition_lopo as role_audit

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
FAMILY_DIR = ROOT / "eval" / "whole_map_forecast" / "operator-transition-family-lopo-v1" / "training21"
ROLE_DIR = ROOT / "eval" / "whole_map_forecast" / "operator-role-type-transition-lopo-v1" / "training21"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-family-content-audit-v1" / "training21"
MANIFEST_PATH = TRAINING / "training-corpus-manifest.json"
SEAL_PATH = TRAINING / "seal-receipt.json"
FAMILY_DATA = FAMILY_DIR / "data.json"
ROLE_DATA = ROLE_DIR / "data.json"
IMPLEMENTATION = (
    Path(__file__),
    Path(__file__).with_name("run_training21_operator_transition_lopo.py"),
    Path(__file__).with_name("run_training21_role_type_transition_lopo.py"),
    ROOT / "api" / "domain" / "operation_role_bindings.py",
)
TOP_K = 20


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_receipt(directory: Path, data_name: str = "data.json") -> dict:
    receipt = load_json(directory / "verification.json")
    data = load_json(directory / data_name)
    expected = receipt.get("artifacts_sha256", receipt.get("files", {})).get(data_name)
    require(expected and file_sha(directory / data_name) == expected, "Артефакт аудита не совпадает с квитанцией")
    require(receipt.get("parent_seal_verified") is True and receipt.get("target_map_read") is False
            and receipt.get("model_calls") == 0 and receipt.get("network_calls") == 0,
            "Квитанция аудита не подтверждает seal и запрет вызовов")
    return data


def knowledge_description(article: dict, knowledge_id: str, normalized: dict) -> dict:
    item = article["knowledge"][knowledge_id]
    frame = normalized[knowledge_id]
    return {
        "knowledge_id": knowledge_id,
        "display_text_en": item["display_text"],
        "knowledge_kind": item["knowledge_kind"],
        "kind": item["kind"],
        "logic": frame["logic"],
        "statements": [{
            "predicate": statement["predicate"],
            "roles": [{"role": role["role"], "value": role["value"]} for role in statement["roles"]],
            "negated": statement["negated"],
            "scope": statement["scope"],
        } for statement in frame["statements"]],
    }


def transition_rows(snapshot: dict) -> tuple[dict, list[dict]]:
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    typed, catalog = family_audit.type_shapes(snapshot)
    role_typed, _, _ = role_audit.role_type_shapes(typed, catalog)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    normalized = {item["id"]: item for item in family_audit.normalize_map(snapshot)}
    nodes = {item["id"]: item["knowledge_id"] for item in graph["nodes"]}
    rows = []
    for ordinal, transition in enumerate(graph["transitions"]):
        source_ids = [nodes[node_id] for node_id in transition["sources"]]
        target_id = nodes[transition["target"]]
        if len(source_ids) > family_audit.MAXIMUM_ARITY:
            continue
        family_shape = family_audit.shape(
            [typed["block_types"]["operator_family"][key] for key in source_ids],
            typed["block_types"]["operator_family"][target_id],
        )
        role_shape = family_audit.shape(
            [role_typed["block_types"]["role_types"][key] for key in source_ids],
            role_typed["block_types"]["role_types"][target_id],
        )
        exact_role_shape = family_audit.shape(
            [typed["block_types"]["operator_roles"][key] for key in source_ids],
            typed["block_types"]["operator_roles"][target_id],
        )
        rows.append({
            "transition_ordinal": ordinal,
            "family_shape": family_shape,
            "family_shape_id": family_audit.shape_id(family_shape),
            "role_type_shape": role_shape,
            "role_type_shape_id": family_audit.shape_id(role_shape),
            "exact_role_shape": exact_role_shape,
            "exact_role_shape_id": family_audit.shape_id(exact_role_shape),
            "source_knowledge": [knowledge_description({"knowledge": knowledge}, key, normalized) for key in source_ids],
            "target_knowledge": knowledge_description({"knowledge": knowledge}, target_id, normalized),
        })
    return {"article_id": snapshot["article_id"], "title": family_audit.citation_keys(snapshot)["title"],
            "source_sha256": snapshot["source"]["sha256"]}, rows


def shape_support(rows: dict[str, list[dict]], key_name: str, allowed_ids: set[str]) -> dict[str, set[str]]:
    support = defaultdict(set)
    for article_id in sorted(allowed_ids):
        for item in rows[article_id]:
            support[item[key_name]].add(article_id)
    return support


def rank_of(shape_id: str, support: dict[str, set[str]]) -> tuple[int | None, int]:
    eligible = {key: len(value) for key, value in support.items()
                if len(value) >= family_audit.MINIMUM_SUPPORT}
    order = sorted(eligible, key=lambda key: (-eligible[key], key))
    try:
        return order.index(shape_id) + 1, eligible[shape_id]
    except ValueError:
        return None, len(support.get(shape_id, set()))


def write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def main() -> None:
    require(not OUTPUT.exists(), "Выходная папка существует; неизменяемый аудит не перезаписывается")
    family_data = verify_receipt(FAMILY_DIR)
    role_data = verify_receipt(ROLE_DIR)
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    require(seal["sealed"] and seal["training_count"] == 21
            and seal["prediction_sha256"] == family_data["forecast_parent_sha256"],
            "Общий запечатанный родительский прогон не совпадает")
    require(family_data["training_manifest_sha256"] == role_data["training_manifest_sha256"]
            == file_sha(MANIFEST_PATH),
            "Аудиты используют разные обучающие манифесты")
    require(family_data["source_count"] == role_data["source_count"] == 21,
            "Аудиты используют разные размеры корпуса")

    repository = FileForecastMaps(manifest["sources"])
    metadata = {}
    transitions_by_article = {}
    snapshots_by_article = {}
    for entry in manifest["sources"]:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None, "Карта обучающего списка не найдена")
        require(snapshot["run_id"] == reference["run_id"]
                and snapshot["source"]["sha256"] == entry["source_sha256"]
                and fingerprint(snapshot["graph"]) == entry["graph_sha256"]
                and file_sha(Path(entry["path"])) == entry["file_sha256"],
                "Карта, источник или граф не совпадают с манифестом")
        article, transitions = transition_rows(snapshot)
        metadata[article["article_id"]] = article
        transitions_by_article[article["article_id"]] = transitions
        snapshots_by_article[article["article_id"]] = snapshot
    require(len(metadata) == 21, "Нужны 21 уникальная карта")

    family_support_all = shape_support(transitions_by_article, "family_shape_id", set(metadata))
    role_support_all = shape_support(transitions_by_article, "role_type_shape_id", set(metadata))
    exact_support_all = shape_support(transitions_by_article, "exact_role_shape_id", set(metadata))
    matches = []
    fold_hit_total = 0
    role_hit_total = 0
    exact_role_hit_total = 0
    for fold in family_data["folds"]:
        target_id = fold["target_article_id"]
        role_fold = next(item for item in role_data["folds"] if item["target_article_id"] == target_id)
        require(fold["training_article_ids"] == role_fold["training_article_ids"],
                "Состав обучающих источников различается между аудитами")
        training_ids = set(fold["training_article_ids"])
        family_prediction = fold["scores"]["operator_family"]["graph"][str(TOP_K)]["selected"]
        predicted_ids = {family_audit.shape_id(item["shape"]) for item in family_prediction}
        family_training_support = shape_support(transitions_by_article, "family_shape_id", training_ids)
        role_training_support = shape_support(transitions_by_article, "role_type_shape_id", training_ids)
        exact_training_support = shape_support(transitions_by_article, "exact_role_shape_id", training_ids)
        target_transitions = transitions_by_article[target_id]
        target_hits = [item for item in target_transitions if item["family_shape_id"] in predicted_ids]
        unique_hit_ids = sorted({item["family_shape_id"] for item in target_hits})
        fold_hit_total += len(unique_hit_ids)
        role_predicted = {
            family_audit.shape_id(item["shape"])
            for item in role_fold["scores"]["role_types"]["graph"][str(TOP_K)]["selected"]
        }
        exact_role_predicted = {
            family_audit.shape_id(item["shape"])
            for item in family_data["folds"][family_data["folds"].index(fold)]
            ["scores"]["operator_roles"]["graph"][str(TOP_K)]["selected"]
        }
        for family_id in unique_hit_ids:
            target_edges = [item for item in target_hits if item["family_shape_id"] == family_id]
            family_examples = []
            for article_id in sorted(training_ids):
                source_edges = [item for item in transitions_by_article[article_id]
                                if item["family_shape_id"] == family_id]
                if source_edges:
                    family_examples.append({
                        "article_id": article_id,
                        "title": metadata[article_id]["title"],
                        "transition": source_edges[0],
                    })
                if len(family_examples) == 3:
                    break
            for target_edge in target_edges:
                role_count = len(role_training_support.get(target_edge["role_type_shape_id"], set()))
                exact_count = len(exact_training_support.get(target_edge["exact_role_shape_id"], set()))
                role_rank, _ = rank_of(target_edge["role_type_shape_id"], role_training_support)
                exact_rank, _ = rank_of(target_edge["exact_role_shape_id"], exact_training_support)
                role_hit_total += target_edge["role_type_shape_id"] in role_predicted
                exact_role_hit_total += target_edge["exact_role_shape_id"] in exact_role_predicted
                matches.append({
                    "target_article_id": target_id,
                    "target_title": metadata[target_id]["title"],
                    "family_shape_id": family_id,
                    "family_support_publications": len(family_training_support.get(family_id, set())),
                    "family_support_article_ids": sorted(family_training_support.get(family_id, set())),
                    "target_transition": target_edge,
                    "training_examples": family_examples,
                    "role_type_support_publications": role_count,
                    "role_type_candidate_rank": role_rank,
                    "role_type_in_top20": target_edge["role_type_shape_id"] in role_predicted,
                    "exact_role_support_publications": exact_count,
                    "exact_role_candidate_rank": exact_rank,
                    "exact_role_in_top20": target_edge["exact_role_shape_id"] in exact_role_predicted,
                })

    require(fold_hit_total == family_data["mode_summaries"]["operator_family"]["graph"]["20"]["matched_shape_count"],
            "Повторно рассчитанные семейные попадания не совпали с исходным отчётом")
    data = {
        "audit_version": "operator-family-content-audit-training21-1",
        "parent_family_audit_sha256": file_sha(FAMILY_DATA),
        "parent_role_audit_sha256": file_sha(ROLE_DATA),
        "training_manifest_sha256": file_sha(MANIFEST_PATH),
        "source_count": len(metadata),
        "top_k": TOP_K,
        "family_hit_shapes": fold_hit_total,
        "role_type_hit_transitions": role_hit_total,
        "exact_role_hit_transitions": exact_role_hit_total,
        "matches": matches,
        "model_calls": 0,
        "network_calls": 0,
        "target_map_read": False,
        "interpretation_ru": "Постфактум-анализ совпадений структурных форм; он не является новым запечатанным прогнозом и не подтверждает научную эквивалентность.",
    }
    training_manifest_raw = MANIFEST_PATH.read_bytes()
    report = [
        "# Семантическая проверка структурных попаданий",
        "",
        "Этот постфактум-аудит разбирает совпадения из удержанного прогноза форм переходов на 21 статье. Он не меняет предсказания и не переобучает правила. Карта PMC10002471 не входит в обучающий список.",
        "",
        f"- Проверено источников: {len(metadata)}; общий обучающий манифест: {file_sha(MANIFEST_PATH)}.",
        f"- Семейных форм-попаданий на лимите @20: {fold_hit_total}.",
        f"- Удержанных переходов среди них, чья типизированная роль-схема тоже вошла в топ-20: {role_hit_total}.",
        f"- Переходов, чья точная роль-схема вошла в топ-20: {exact_role_hit_total}.",
        "- Прямые цитаторы цели исключены по обучающим спискам исходного удержанного аудита.",
        "- Модельных и сетевых вызовов: 0.",
        "",
        "## Примеры совпавшей формы и её семантическая проверка",
        "",
        "| Цель | Форма совпала при поддержке | Типизированные роли: поддержка / ранг | Точная схема ролей: поддержка / ранг |",
        "|---|---:|---:|---:|",
    ]
    for item in matches[:30]:
        role_rank = str(item["role_type_candidate_rank"]) if item["role_type_candidate_rank"] is not None else "нет поддержки"
        exact_rank = str(item["exact_role_candidate_rank"]) if item["exact_role_candidate_rank"] is not None else "нет поддержки"
        report.append(
            f"| {item['target_article_id']} | {item['family_support_publications']} публикаций | "
            f"{item['role_type_support_publications']} / {role_rank} | "
            f"{item['exact_role_support_publications']} / {exact_rank} |"
        )
    report += [
        "",
        "## Что именно совпало",
        "",
        "Полные блоки-участники, предикаты, роли, отрицания, кванторы, модальность и области действия сохранены в data.json для каждого совпадения и до трёх обучающих примеров. Они нужны для ручной проверки того, является ли общая форма полезной аналогией или только одинаковым расположением типов узлов.",
        "",
        "Переход на семейный уровень сам по себе не означает совпадения утверждений. Предварительная типизация ролей не должна превращаться в вывод научного факта; отдельные показатели, выборки, времена и условия остаются обязательными для проверки.",
        "",
        "## Ограничения",
        "",
        "Это ретроспективная диагностика уже известных карт. Она не является слепым или перспективным прогнозом. Карты и фрагменты требуют экспертной проверки; успешность формы нельзя экстраполировать на точность содержания всей Карты Знаний.",
        "",
        "## Воспроизводимость",
        "",
        f"Хеш исходного аудита семейств: {file_sha(FAMILY_DATA)}.",
        f"Хеш аудита типизированных ролей: {file_sha(ROLE_DATA)}.",
        "Манифест, код, прежние карты и предсказания сохранены отдельно; новый результат опубликован только в этой папке.",
    ]
    report_raw = ("\n".join(report) + "\n").encode("utf-8")
    data_raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    write_new(OUTPUT / "training-corpus-manifest.json", training_manifest_raw)
    for path in IMPLEMENTATION:
        write_new(OUTPUT / "implementation" / path.relative_to(ROOT), path.read_bytes())
    write_new(OUTPUT / "data.json", data_raw)
    write_new(OUTPUT / "report.ru.md", report_raw)
    receipt = {
        "audit_version": data["audit_version"],
        "parent_family_audit_verified": True,
        "parent_role_audit_verified": True,
        "training_manifest_sha256": file_sha(MANIFEST_PATH),
        "implementation_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in IMPLEMENTATION},
        "artifacts_sha256": {
            "training-corpus-manifest.json": file_sha(OUTPUT / "training-corpus-manifest.json"),
            "data.json": file_sha(OUTPUT / "data.json"),
            "report.ru.md": file_sha(OUTPUT / "report.ru.md"),
        },
        "target_map_read": False,
        "model_calls": 0,
        "network_calls": 0,
    }
    write_new(OUTPUT / "verification.json",
              (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    require(file_sha(OUTPUT / "report.ru.md") == receipt["artifacts_sha256"]["report.ru.md"],
            "Хеш отчёта не совпал")
    print(json.dumps({
        "family_hit_shapes": fold_hit_total,
        "role_type_top20_hits": role_hit_total,
        "exact_role_top20_hits": exact_role_hit_total,
        "match_rows": len(matches),
        "output": str(OUTPUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
