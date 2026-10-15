"""Проверяет и публикует русский отчёт эксперимента EAE-1 для WHICAP."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines


EXPECTED_CHILDREN = {"C6", "C12", "C14", "C16", "C48", "C49"}
SUBTYPE_RU = {
    "MCI-amnestic": "амнестический MCI",
    "MCI-executive": "MCI с нарушением исполнительных функций",
    "MCI-language": "языковой MCI",
    "MCI-visuospatial": "зрительно-пространственный MCI",
    "MCI-MCDM": "MCI-MCDM",
    "MCI-MCDN": "MCI-MCDN",
}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _acyclic(nodes: set[str], edges: list[tuple[str, str]]) -> bool:
    outgoing = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for source, target in edges:
        require(source in nodes and target in nodes and source != target,
                "Visible WHICAP graph contains an invalid edge")
        if target not in outgoing[source]:
            outgoing[source].add(target)
            indegree[target] += 1
    queue = [node for node, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for target in outgoing[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited == len(nodes)


def _conclusion_key(candidate: dict) -> tuple:
    conclusion = candidate["conclusion"]
    return (conclusion["form"], conclusion["subject"], conclusion["object"],
            fingerprint(conclusion["scope"]))


def verify(run_root: Path) -> dict:
    result = _read(run_root / "predictions.json")
    manifest = _read(run_root / "source-manifest.json")
    reads = _read(run_root / "reads.json")
    license_audit = _read(run_root / "categorical-licenses.json")
    logic = result["licensed_categorical_inference"]
    manifest_sources = manifest["sources"]

    require(result["run_id"] == run_root.name, "Run directory and sealed result differ")
    require(len(manifest_sources) == 21, "Unexpected source count")
    require(not any(source["reference"]["article_id"].casefold() == "pmc10000452"
                    for source in manifest_sources), "Target article leaked into training")
    require(reads["network_disabled"] is True and reads["model_calls"] == 0
            and reads["target_read"] is False, "Network, model, or target access detected")
    require(license_audit["version"] == "source-bound-categorical-licenses-3"
            and license_audit["author"] == "Codex" and license_audit["model_calls"] == 0
            and license_audit["expert_validated"] is False,
            "Source-bound license provenance differs")

    maps_by_article = {
        source["reference"]["article_id"]: _read(Path(source["path"]))
        for source in manifest_sources
    }
    for entry in license_audit["entries"]:
        source_map = maps_by_article[entry["article_id"]]
        parent = next(item for item in source_map["graph"]["knowledge"]
                      if item["knowledge_id"] == entry["knowledge_id"])
        require(entry["run_id"] == source_map["run_id"]
                and entry["source_sha256"] == source_map["source"]["sha256"]
                and entry["graph_sha256"] == fingerprint(source_map["graph"])
                and entry["knowledge_sha256"] == fingerprint(parent),
                "Categorical license no longer matches its source map")
        text = source_map["source"]["text"]
        units = {unit["id"]: unit for unit in source_map["source"]["units"]}
        expected_units = {
            unit_id for statement in parent["semantic_frame"]["statements"]
            for unit_id in statement["provenance"]["unit_ids"]
        }
        quotes = {quote["unit_id"]: quote for quote in entry["evidence"]}
        require(set(quotes) == expected_units, "License evidence does not cover the complete parent frame")
        for unit_id, quote in quotes.items():
            unit = units[unit_id]
            actual = text[quote["start"]:quote["end"]]
            require(quote["start"] == unit["start"] and quote["end"] == unit["end"]
                    and quote["end"] <= source_map["source"]["content_end"]
                    and quote["text"] == actual == unit["text"]
                    and quote["sha256"] == sha256(actual.encode("utf-8")).hexdigest(),
                    "Licensed source quote differs from its Unicode coordinates")

    manly_source = next(source for source in manifest_sources
                        if source["reference"]["article_id"] == "manly2008-complete")
    manly = _read(Path(manly_source["path"]))
    graph = manly["graph"]
    node_by_knowledge = {node["knowledge_id"]: node["id"] for node in graph["nodes"]}
    transition_pairs = {
        (tuple(transition["sources"]), transition["target"])
        for transition in graph["transitions"]
        if transition.get("usage") == "definition"
    }
    graph_edges = [(edge["source"], edge["target"]) for edge in graph["edges"]]
    require(_acyclic({node["id"] for node in graph["nodes"]}, graph_edges),
            "WHICAP visible graph is not a DAG")

    graph_candidates = logic["consequences"]["graph"]
    graph_children = {
        candidate["conclusion"]["subject"].rsplit("::concept:", 1)[-1]
        for candidate in graph_candidates
    }
    require(graph_children == EXPECTED_CHILDREN and len(graph_candidates) == 6,
            "Graph mode did not produce exactly the six licensed subtype conclusions")
    proof_rows = []
    for candidate in graph_candidates:
        head = candidate["conclusion"]
        child_id = head["subject"].rsplit("::concept:", 1)[-1]
        parent = candidate["proof"]["premises"]
        premise_records = candidate["premises"]
        require(head["form"] == "E"
                and head["object"] == "manly2008-complete::concept:C76"
                and [premise["form"] for premise in parent] == ["E", "A"]
                and parent[0]["subject"] == "manly2008-complete::concept:C72"
                and parent[0]["object"] == "manly2008-complete::concept:C76"
                and parent[1]["subject"] == head["subject"]
                and parent[1]["object"] == "manly2008-complete::concept:C72",
                "Candidate is not the expected EAE-1 proof")
        require(candidate["proof"]["entailed"] and candidate["proof"]["premises_consistent"]
                and not candidate["proof"]["countermodels"]
                and candidate["proof"]["existence_conditions"] == []
                and candidate["proof_graph"]["visible_dag"] is True
                and candidate["status"] == "conditional_logical_consequence",
                "Formal proof or consequence status differs")
        require(len(premise_records) == 2
                and (premise_records[0]["article_id"], premise_records[0]["knowledge_id"],
                     premise_records[0]["statement_id"])
                == ("manly2008-complete", "K64", "K64S4"),
                "Shared WHICAP exclusion premise changed")
        subtype_premise = premise_records[1]
        require(subtype_premise["article_id"] == "manly2008-complete"
                and subtype_premise["statement_id"].endswith("S1")
                and subtype_premise["knowledge_id"] in {f"K{i}" for i in range(65, 71)},
                "Subtype premise does not reference a licensed WHICAP definition")
        subtype_knowledge_id = subtype_premise["knowledge_id"]
        license_entry = next(entry for entry in license_audit["entries"]
                             if entry["article_id"] == "manly2008-complete"
                             and entry["knowledge_id"] == subtype_knowledge_id)
        licensed_statement = next(statement for statement in license_entry["statements"]
                                  if statement["statement_id"] == subtype_premise["statement_id"])
        require(licensed_statement["decision"] == "license_definition"
                and licensed_statement["clause"]["form"] == "A"
                and licensed_statement["clause"]["subject"] == head["subject"],
                "Subtype inclusion is not bound to the predicted class")
        require((tuple([node_by_knowledge["K64"]]),
                 node_by_knowledge[subtype_knowledge_id]) in transition_pairs,
                "Proof premises are not directly connected by the source DAG")
        require(parent[0]["scope"] == parent[1]["scope"] == head["scope"],
                "Proof scope was changed between premises and conclusion")
        concept = next(item for item in graph["concepts"] if item["id"] == child_id)
        proof_rows.append({
            "concept_id": child_id,
            "subtype_en": concept["display_text"],
            "subtype_ru": SUBTYPE_RU.get(concept["display_text"], concept["display_text"]),
            "conclusion": head,
            "premises": premise_records,
            "proof": candidate["proof"],
            "proof_graph": candidate["proof_graph"],
            "source_transition": next(
                transition for transition in graph["transitions"]
                if transition.get("usage") == "definition"
                and transition["sources"] == [node_by_knowledge["K64"]]
                and transition["target"] == node_by_knowledge[subtype_knowledge_id]
            ),
        })

    modes = logic["consequences"]
    sets = {mode: {_conclusion_key(candidate) for candidate in candidates}
            for mode, candidates in modes.items()}
    require(sets["graph"] <= sets["without_dependencies"],
            "Graph outputs are not reproducible by the no-dependency semantic control")
    require({mode: len(values) for mode, values in modes.items()} == {
        "graph": 6, "without_dependencies": 8,
        "source_neighborhood": 2, "permuted_dependencies": 0,
    }, "Logical control counts differ from the sealed run")

    return {
        "run_id": result["run_id"],
        "corpus_sources": len(manifest_sources),
        "canonical_blocks": result["canonical_blocks"],
        "eligible_blocks": sum(item["eligible"] for item in result["coverage"]),
        "target_article_excluded": True,
        "target_read": False,
        "model_calls": reads["model_calls"],
        "network_disabled": reads["network_disabled"],
        "logical_counts": {mode: len(values) for mode, values in modes.items()},
        "graph_unique_conclusions_vs_no_dependencies": len(sets["graph"] - sets["without_dependencies"]),
        "no_dependency_only_conclusions": len(sets["without_dependencies"] - sets["graph"]),
        "licensed_parent_blocks": logic["licensed_parent_blocks"],
        "licensed_views": logic["licensed_views"],
        "eae1_proof_count": len(proof_rows),
        "all_visible_source_graphs_acyclic": True,
        "new_empirical_predictions": 0,
        "graph_advantage_demonstrated": False,
        "expert_validated": False,
        "conclusions": sorted(proof_rows, key=lambda row: row["subtype_en"]),
    }


def render_report(data: dict) -> str:
    lines = [
        "# Проверка логики по определениям WHICAP на 21 карте",
        "",
        "**Новых эмпирических прогнозов нет. Доказано шесть условных логических следствий из одного источника; преимущество зависимостей над теми же знаниями без рёбер не показано.**",
        "",
        f"Проверена {data['corpus_sources']} карта и {data['canonical_blocks']} канонических знаний; {data['eligible_blocks']} блоков допущены к общему анализу. PMC10000452 отсутствовала в тренировочном манифесте и не читалась оценщиком. Сетевые и модельные вызовы отключены.",
        "",
        "## Что лицензировано в источнике",
        "",
        "В статье Manly et al. 2008 для WHICAP явно заданы два положения. В блоке K64, statement K64S4, MCI-классификация требует отсутствия диагноза деменции на том же согласительном визите (фрагмент U23). В блоках K65–K70, statements S1, каждый из шести подтипов включён в локальный класс WHICAP MCI; полные составные блоки сохранены, а прочие части не преобразованы в посылки.",
        "",
        "Исходная карта содержит прямые связи-определения K64 → K65…K70. Они задают, какие локальные пары проверить; типизированные связи сами не интерпретируются как силлогистические отношения.",
        "",
        "## Шесть следствий EAE‑1",
        "",
        "Форма: **ни один M не P; все S — M; значит, ни один S не P**. Здесь M — класс WHICAP MCI, P — участники с диагнозом деменции на том же консенсусном визите, S — соответствующий WHICAP-подтип. Контекст обеих посылок совпадает; существование классов не домысливается.",
        "",
        "| Подтип | Полученное следствие | Посылки и ребро исходной карты |",
        "| --- | --- | --- |",
    ]
    for item in data["conclusions"]:
        premise_ids = ", ".join(premise["knowledge_id"] + "/" + premise["statement_id"]
                                 for premise in item["premises"])
        transition = item["source_transition"]
        lines.append(
            f"| {item['subtype_ru']} | Ни один участник этого подтипа не относится к классу диагнозов деменции на том же WHICAP-визите | {premise_ids}; {transition['id']} ({transition['usage']}) |"
        )
    lines += [
        "",
        "Для каждой строки проверены модели: посылки совместимы, контрмоделей нет, каждая посылка необходима. Результат условен относительно формализации исходных определений и не представляет новый клинический результат.",
        "",
        "## Контроли",
        "",
        "| Режим поиска посылок | Следствий |",
        "| --- | ---: |",
        f"| Прямые зависимости исходного DAG | {data['logical_counts']['graph']} |",
        f"| Те же лицензированные знания без зависимостей | {data['logical_counts']['without_dependencies']} |",
        f"| Соседство в статье | {data['logical_counts']['source_neighborhood']} |",
        f"| Переставленные зависимости | {data['logical_counts']['permuted_dependencies']} |",
        "",
        "Все шесть графовых следствий также найдены режимом без рёбер. В нём есть ещё два следствия из определения и подтипов PMC6416157. Поэтому исходные связи здесь не добавили уникального вывода и не превзошли безрёберный поиск; они выбрали только прямые пары WHICAP-определений. Ноль при перемешивании показывает чувствительность к этим конкретным связям, но сам по себе не доказывает преимущество карты.",
        "",
        "## Общий свободный прогноз",
        "",
        "В том же запуске частотный обучаемый модуль на этих 21 картах не нашёл повторяемых межстатейных правил и не выдал новых кандидатов ни в режиме исходного графа, ни в трёх контрольных режимах. По 20 результатов объединения известных знаний и частотного списка — это выбранные существующие блоки, не 20 совпадений. 151 численный вывод — вычисления из уже опубликованных величин, не независимые прогнозы.",
        "",
        "## Проверки и границы",
        "",
        "74 теста категориальной логики и лицензирования прошли через Poetry. Проверена ацикличность всех 21 исходных графов; каждый вывод ссылается на исходные блоки, точные statements и прямую связь. Лицензии и переводы классов подготовлены Codex без LLM; экспертная научная проверка не выполнялась.",
        "",
        f"Запуск: `{data['run_id']}`. Родителей определения: {data['licensed_parent_blocks']}; отдельных лицензированных фрагментов: {data['licensed_views']}. Формат доказательства: категорическая логика с проверкой моделей; применена только одна из 24 классических форм — EAE‑1. Это не частотный паттерн и не причинный перенос.",
        "",
        "Следующий содержательный шаг — искать во всей карте корректно формализуемые межстатейные эмпирические отношения с сохранением участников, знака, чисел, единиц и контекста. Текущий тест закрывает только узкий канал определений; критерий успеха свободного научного прогноза остаётся недостигнутым.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run_root = Path(args.run).resolve()
    data = verify(run_root)
    report = render_report(data)
    html = (
        '<!doctype html><html lang="ru"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width"><title>Логический тест WHICAP</title>'
        '<style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1150px;padding:0 20px;background:#f4f6f9;color:#172435}'
        'main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}.table{overflow:auto}'
        'table{border-collapse:collapse;width:100%}td,th{padding:11px;border:1px solid #ccd7e5;text-align:left;vertical-align:top}'
        'th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>'
        + render_lines(report.splitlines()) + "</main></html>"
    )
    review = run_root / "review-v2"
    review.mkdir(parents=True, exist_ok=True)
    files = {
        "report.ru.md": report.encode("utf-8"),
        "report.html": html.encode("utf-8"),
        "data.json": (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    for name, content in files.items():
        write_immutable(review / name, content)
    input_hashes = {
        name: sha256((run_root / name).read_bytes()).hexdigest()
        for name in ("predictions.json", "source-manifest.json", "reads.json", "categorical-licenses.json")
    }
    verification = {
        "run_id": data["run_id"],
        "input_sha256": input_hashes,
        "report_sha256": {name: sha256(content).hexdigest() for name, content in files.items()},
        "source_count": data["corpus_sources"],
        "target_excluded_and_unread": data["target_article_excluded"] and not data["target_read"],
        "model_calls": data["model_calls"],
        "network_disabled": data["network_disabled"],
        "eae1_proof_count": data["eae1_proof_count"],
        "control_counts": data["logical_counts"],
        "graph_advantage_demonstrated": data["graph_advantage_demonstrated"],
        "expert_validated": data["expert_validated"],
    }
    write_immutable(review / "verification.json",
                    (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"run_id": data["run_id"], "review": str(review),
                      "logical_counts": data["logical_counts"],
                      "graph_unique_vs_no_edges": data["graph_unique_conclusions_vs_no_dependencies"],
                      "proofs_verified": data["eae1_proof_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
