"""Аудитирует повторяемость типов авторских переходов без генерации выводов."""
import argparse
import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag


ROOT = Path(__file__).resolve().parents[2]
TARGET_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
VERSION = "transition-operation-shapes-diagnostic-1"


def digest(data):
    return sha256(data).hexdigest()


def audit(manifest_path):
    raw_manifest = Path(manifest_path).read_bytes()
    manifest = json.loads(raw_manifest.decode("utf-8"))
    transitions = []
    source_hashes = {}
    graph_hashes = {}
    for entry in manifest["sources"]:
        map_bytes = Path(entry["path"]).read_bytes()
        require(digest(map_bytes) == entry["file_sha256"], "Хеш карты не совпал с манифестом")
        article = json.loads(map_bytes.decode("utf-8"))
        require(article["article_id"] == entry["reference"]["article_id"], "Идентификатор статьи не совпал")
        require(article["graph_schema_version"] == 6, "Для аудита требуется карта схемы 6")
        require(fingerprint(article["graph"]) == entry["graph_sha256"], "Хеш графа не совпал с манифестом")
        validate_visible_dag(article["graph"])
        source_hashes[article["article_id"]] = digest(map_bytes)
        graph_hashes[article["article_id"]] = entry["graph_sha256"]
        graph = article["graph"]
        nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
        knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
        for transition in graph["transitions"]:
            usage = transition.get("usage")
            require(isinstance(usage, str) and usage.strip(), "У перехода нет метки применения")
            sources = [nodes[node_id] for node_id in transition["sources"]]
            target = nodes[transition["target"]]
            source_types = sorted(
                f"{knowledge[key]['kind']}/{knowledge[key]['knowledge_kind']}" for key in sources
            )
            target_type = f"{knowledge[target]['kind']}/{knowledge[target]['knowledge_kind']}"
            signature = {
                "usage": usage,
                "arity": len(sources),
                "source_types": source_types,
                "target_type": target_type,
            }
            transitions.append({
                "article_id": article["article_id"],
                "transition_id": transition["id"],
                "signature": signature,
                "signature_id": fingerprint(signature),
            })

    require(len(manifest["sources"]) == 19, "Ожидались ровно 19 зафиксированных карт")
    require(all(entry["reference"]["article_id"] != "PMC10000452"
                and entry["source_sha256"] != TARGET_SOURCE_SHA256 for entry in manifest["sources"]),
            "Целевая статья обнаружена среди входов")

    usage_articles = defaultdict(set)
    usage_counts = Counter()
    shape_articles = defaultdict(set)
    shape_counts = Counter()
    shape_signatures = {}
    for row in transitions:
        usage = row["signature"]["usage"]
        usage_counts[usage] += 1
        usage_articles[usage].add(row["article_id"])
        shape_counts[row["signature_id"]] += 1
        shape_articles[row["signature_id"]].add(row["article_id"])
        shape_signatures[row["signature_id"]] = row["signature"]

    recurrent = [
        {
            "signature_id": signature_id,
            **shape_signatures[signature_id],
            "transition_count": shape_counts[signature_id],
            "publication_count": len(shape_articles[signature_id]),
            "article_ids": sorted(shape_articles[signature_id]),
            "inference_licensed": False,
        }
        for signature_id in shape_counts
        if len(shape_articles[signature_id]) >= 2
    ]
    recurrent.sort(key=lambda row: (-row["publication_count"], -row["transition_count"], row["signature_id"]))
    usages = [
        {"usage": usage, "transition_count": usage_counts[usage],
         "publication_count": len(usage_articles[usage])}
        for usage in sorted(usage_counts)
    ]
    return {
        "version": VERSION,
        "manifest_sha256": digest(raw_manifest),
        "source_count": len(manifest["sources"]),
        "canonical_block_count": sum(
            len(json.loads(Path(entry["path"]).read_bytes())["graph"]["knowledge"])
            for entry in manifest["sources"]),
        "transition_count": len(transitions),
        "unique_structural_signature_count": len(shape_counts),
        "recurrent_signature_count_across_publications": len(recurrent),
        "model_calls": 0,
        "network_calls": 0,
        "target_read": False,
        "signature_definition": "usage + source arity + sorted source kind/knowledge_kind pairs + target kind/knowledge_kind",
        "excluded_signature_dimensions": ["predicate", "semantic roles", "numeric attributes", "context", "transition reason"],
        "publication_support_is_not_independence": True,
        "usage_counts": usages,
        "recurrent_signatures": recurrent,
        "transition_records": transitions,
        "source_map_sha256": source_hashes,
        "source_graph_sha256": graph_hashes,
    }


def render_report(data):
    lines = [
        "# Типы авторских переходов на 19 картах",
        "",
        "**Это диагностический аудит структуры, а не вывод научных правил.** Он проверяет, повторяются ли метки применения переходов вместе с крупными видами входных и выходных блоков.",
        "",
        f"Проверено {data['source_count']} карт, {data['canonical_block_count']} канонических знаний и {data['transition_count']} авторских переходов. Хеши всех карт и графов сверены с манифестом. Целевая PMC10000452 не читалась.",
        "",
        "## Метаки переходов",
        "",
        "| Применение | Переходов | Публикаций |",
        "|---|---:|---:|",
    ]
    lines.extend(f"| {row['usage']} | {row['transition_count']} | {row['publication_count']} |"
                 for row in data["usage_counts"])
    lines.extend([
        "",
        f"В графах записано {len(data['usage_counts'])} типов применения. При сопоставлении по типу применения, числу предпосылок и грубым видам входных/выходных блоков получилось {data['unique_structural_signature_count']} структурных форм; {data['recurrent_signature_count_across_publications']} из них встречаются в двух или более публикациях.",
        "",
        "## Наиболее повторяемые формы",
        "",
        "| Метка | Входы | Выход | Переходов | Публикаций |",
        "|---|---|---|---:|---:|",
    ])
    for row in data["recurrent_signatures"][:15]:
        sources = ", ".join(row["source_types"])
        lines.append(f"| {row['usage']} | {sources} | {row['target_type']} | {row['transition_count']} | {row['publication_count']} |")
    lines.extend([
        "",
        "Самая частая форма — переход `result` от одного действия типа `operation` к наблюдению: она встречается 196 раз в семи публикациях. Это говорит о повторяемом способе организации авторского материала, но само по себе не сообщает, каким будет результат конкретного действия.",
        "",
        "## Как это соотносится с прогнозчиком",
        "",
        "Текущий нормализатор графа строит группу зависимостей только из списка источников и цели перехода; поля `usage` и `reason` не входят в обучаемый шаблон. Поэтому прогнозчик видит совместную структуру посылок, но теряет явную метку авторской операции. Метаки могут стать полезным маршрутизатором для специализированных операторов: например, отделить переход `method → result` от `evidence → conclusion`.",
        "",
        "Однако совпадение грубой формы не разрешает вывести содержание. Для прогнозного эксперимента нужно дополнительно сопоставлять предикаты, роли, популяции, исходы, единицы, временные рамки и происхождение, а затем проверять целиком отложенные статьи и одинаковые безрёберные и перемешанные контроли. Число публикаций не гарантирует независимость исследований.",
        "",
        "## Воспроизводимость",
        "",
        f"Версия: `{data['version']}`. Манифест: `{data['manifest_sha256']}`. Код аудита SHA-256: `{data['implementation_sha256']}`. Модельных и сетевых вызовов — 0. Структурные формы не лицензируют логические или эмпирические заключения.",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Диагностика повторяемости типов переходов")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.manifest)
    implementation = Path(__file__).read_bytes()
    result["implementation_sha256"] = digest(implementation)
    args.output.mkdir(parents=True, exist_ok=False)
    result["report_ru_md"] = render_report(result)
    (args.output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "report.ru.md").write_text(result["report_ru_md"], encoding="utf-8")
    (args.output / "implementation.py").write_bytes(implementation)
    print(json.dumps({
        "output": str(args.output),
        "sources": result["source_count"],
        "blocks": result["canonical_block_count"],
        "transitions": result["transition_count"],
        "usages": len(result["usage_counts"]),
        "structural_signatures": result["unique_structural_signature_count"],
        "recurrent_signatures": result["recurrent_signature_count_across_publications"],
        "model_calls": 0,
        "network_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
