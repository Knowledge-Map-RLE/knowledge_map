"""Считает эффект двух частичных карт на тех же 21 целевых фолдах."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "eval" / "whole_map_forecast" / "partial-map-expansion-v1" / "training21-plus-two"
OUTPUT = INPUT / "paired-targets-v1"
MODES = ("coarse", "operator_family", "operator_roles")
CONTROLS = ("graph", "cooccurrence")


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    data_path = INPUT / "data.json"
    report_path = INPUT / "report.ru.md"
    verification = load_json(INPUT / "verification.json")
    if file_sha(data_path) != verification["files"]["data.json"]:
        raise RuntimeError("Хеш исходных метрик не совпадает с квитанцией")
    if file_sha(report_path) != verification["files"]["report.ru.md"]:
        raise RuntimeError("Хеш исходного отчёта не совпадает с квитанцией")

    source = load_json(data_path)
    base = {fold["target_article_id"]: fold for fold in source["base_folds"]}
    expanded = {fold["target_article_id"]: fold for fold in source["expanded_folds"]}
    common_ids = sorted(set(base) & set(expanded))
    new_ids = sorted(set(expanded) - set(base))
    if len(common_ids) != 21 or len(new_ids) != 2 or len(base) != 21 or len(expanded) != 23:
        raise RuntimeError("Состав целевых фолдов изменился")

    comparisons = {}
    for mode in MODES:
        comparisons[mode] = {}
        for control in CONTROLS:
            before = after = improved = declined = same = 0
            fold_deltas = []
            for article_id in common_ids:
                left = int(base[article_id]["scores"][mode][control]["20"]["matched_shape_count"])
                right = int(expanded[article_id]["scores"][mode][control]["20"]["matched_shape_count"])
                before += left
                after += right
                improved += right > left
                declined += right < left
                same += right == left
                if left != right:
                    fold_deltas.append({"article_id": article_id, "before": left, "after": right, "delta": right - left})
            comparisons[mode][control] = {"hits_before": before, "hits_after": after,
                                          "improved_folds": improved, "declined_folds": declined,
                                          "same_folds": same, "fold_deltas": fold_deltas}

    new_targets = []
    for article_id in new_ids:
        fold = expanded[article_id]
        new_targets.append({
            "article_id": article_id,
            "coarse_graph_hits_at_20": fold["scores"]["coarse"]["graph"]["20"]["matched_shape_count"],
            "coarse_noedge_hits_at_20": fold["scores"]["coarse"]["cooccurrence"]["20"]["matched_shape_count"],
            "operator_family_graph_hits_at_20": fold["scores"]["operator_family"]["graph"]["20"]["matched_shape_count"],
            "operator_family_noedge_hits_at_20": fold["scores"]["operator_family"]["cooccurrence"]["20"]["matched_shape_count"],
            "operator_roles_graph_hits_at_20": fold["scores"]["operator_roles"]["graph"]["20"]["matched_shape_count"],
            "operator_roles_noedge_hits_at_20": fold["scores"]["operator_roles"]["cooccurrence"]["20"]["matched_shape_count"],
        })

    result = {"audit_version": "partial-map-expansion-common-target-review-1",
              "input_data_sha256": file_sha(data_path), "common_target_count": len(common_ids),
              "new_target_ids": new_ids, "top_k": 20,
              "comparisons": comparisons, "new_target_folds": new_targets,
              "model_calls": 0, "network_calls": 0,
              "scientific_content_prediction": False}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT / "data.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    labels = {"coarse": "Грубые виды знаний", "operator_family": "Семейства операторов",
              "operator_roles": "Семейства, роли и логические ограничения"}
    report = [
        "# Парная проверка эффекта расширения корпуса",
        "",
        "Сравнены те же 21 целевая статья до и после добавления PMC4242065 и PMC6376919 в обучение. Два новых целевых фолда показаны отдельно. Лимит выдачи — 20 форм переходов на статью.",
        "",
        "## Общие 21 целевых фолда",
        "",
        "| Представление | Режим | До расширения | После расширения | Фолды: улучшились / ухудшились / равны |",
        "|---|---|---:|---:|---:|",
    ]
    for mode in MODES:
        for control, control_label in (("graph", "По рёбрам"), ("cooccurrence", "Без рёбер")):
            item = comparisons[mode][control]
            report.append(f"| {labels[mode]} | {control_label} | {item['hits_before']} | {item['hits_after']} | {item['improved_folds']} / {item['declined_folds']} / {item['same_folds']} |")
    report += ["", "При грубой типизации добавление источников не помогло на общих целях: попадания графа изменились с 64 до 62; граф улучшился только в одном фолде, ухудшился в трёх. Для семейств операторов попадания графа снизились с 21 до 19. При сохранении ролей и логических признаков совпадений не было до и после расширения. Следовательно, видимое изменение агрегированных результатов полного 23-карточного набора не является улучшением на прежних целях.",
               "", "## Два новых целевых фолда", "",
               "| PMCID | Грубая форма: граф / без рёбер | Семейства: граф / без рёбер | Роли и логика: граф / без рёбер |",
               "|---|---:|---:|---:|"]
    for row in new_targets:
        report.append(f"| {row['article_id']} | {row['coarse_graph_hits_at_20']} / {row['coarse_noedge_hits_at_20']} | {row['operator_family_graph_hits_at_20']} / {row['operator_family_noedge_hits_at_20']} | {row['operator_roles_graph_hits_at_20']} / {row['operator_roles_noedge_hits_at_20']} |")
    report += ["", "Для PMC4242065 совпадений формы не было. Для PMC6376919 грубая структура дала 2 совпадения у графа и 1 без рёбер; после учёта операторных семейств совпадений не осталось. Обе карты неполны, поэтому этот результат является диагностическим и не считается успехом свободного научного прогноза.",
               "", "Модельных и сетевых вызовов не было. Целевые карты использовались только оценщиком после построения фолдовых прогнозов; результат ретроспективный и не слепой для автора."]
    out_report = OUTPUT / "report.ru.md"
    out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    receipt = {"audit_version": result["audit_version"], "builder_sha256": file_sha(Path(__file__)),
               "input_data_sha256": file_sha(data_path),
               "input_verification_sha256": file_sha(INPUT / "verification.json"),
               "model_calls": 0, "network_calls": 0,
               "files": {name: file_sha(OUTPUT / name) for name in ("data.json", "report.ru.md")}}
    (OUTPUT / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "comparisons": comparisons, "new_targets": new_targets}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
