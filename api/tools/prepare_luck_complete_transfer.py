"""Готовит отдельную ревизию диагностики с расширенной картой Luck 2010."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
import sys

from domain.article_maps import require
from infrastructure.immutable_files import write_immutable


OLD_EXPERIMENT = Path("eval/whole_map_forecast/manly-complete-map-v1/updated-transfer-diagnostic-v1")
NEW_EXPERIMENT = Path("eval/whole_map_forecast/research-corpus-extension-v1/luck-complete-transfer-v3")
LUCK_RUN = Path("eval/whole_map_forecast/luck2010-complete-map-v1/runs/0249331c-b60f-5e92-84cc-11d62142796e")


def prepare(root: Path) -> Path:
    old_root = root / OLD_EXPERIMENT
    new_root = root / NEW_EXPERIMENT
    manifest = json.loads((old_root / "inputs.json").read_text(encoding="utf-8"))
    require(manifest["protocol_version"] == "manly-updated-operator-transfer-diagnostic-1",
            "Ожидался проверенный манифест операторного переноса")
    map_path = root / LUCK_RUN / "map.json"
    raw_map = map_path.read_bytes()
    map_value = json.loads(raw_map)
    require(map_value["article_id"] == "luck2010" and map_value["pipeline_id"] == "text_reified",
            "Ожидалась отдельная карта Luck 2010 из полного текста")
    require(map_value["source"]["sha256"] == "d5e15ac426b3c43e116dfa0ef038992c8aa104ffcb588b36419fa8685ccb8cd3",
            "Хеш исходного текста Luck 2010 изменился")
    require(map_value["graph_schema_version"] == 6 and map_value["needs_expert_review"] is True,
            "Ожидалась карта схемы 6 со статусом экспертной проверки")
    rows = [row for row in manifest["sources"] if row["article_id"] == "luck2010"]
    require(len(rows) == 1, "В старом корпусе должна быть ровно одна карта Luck 2010")
    row = rows[0]
    row.update({
        "run_id": map_value["run_id"], "path": str(map_path),
        "file_sha256": sha256(raw_map).hexdigest(), "source_sha256": map_value["source"]["sha256"],
    })
    manifest["purpose"] = (
        "Leave-one-publication-out diagnostic after replacing the earlier 8-knowledge Luck 2010 map "
        "with a separate 38-knowledge manual full-text draft; all target publications remain held out per fold."
    )
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    old_runner = (old_root / "run_experiment.py").read_text(encoding="utf-8")
    runner = old_runner.replace(
        "Офлайн-проверка переноса операторных мотивов после обновления карты Manly.",
        "Офлайн-проверка переноса операторных мотивов после замены карты Luck 2010.",
    ).replace(
        "# Проверка операторных паттернов после расширения карты WHICAP",
        "# Проверка операторных паттернов после замены карты Luck 2010",
    ).replace(
        "Старая короткая карта Manly 2008 заменена новой Codex-картой полного текста и таблиц. ",
        "Предыдущая короткая карта Luck 2010 заменена отдельным ручным черновиком из полного текста и выбранных строк таблиц. ",
    ).replace(
        'graph = next(item for item in snapshots if item["article_id"] == "manly2008-complete")["graph"]',
        'graph = next(item for item in snapshots if item["article_id"] == "luck2010")["graph"]',
    ).replace(
        'manly_coverage = next(item for item in snapshots if item["article_id"] == "manly2008-complete")',
        'luck_coverage = next(item for item in snapshots if item["article_id"] == "luck2010")',
    )
    limitation_start = runner.index('        "Обновлённая Manly')
    limitation_end = runner.index('        "",', limitation_start)
    runner = runner[:limitation_start] + (
        '        "Новая карта Luck 2010 остаётся частичным исследовательским черновиком: 20 из 44 единиц источника представлены знаниями, "\n'
        '        "полное семантическое покрытие и исчерпывающая формализация таблиц не заявлены. Экспертная научная проверка отсутствует.",\n'
    ) + runner[limitation_end:]
    overclaim = (
        '        "Поэтому этот запуск может показать, добавила ли полная карта новые структурные совпадения в текущем корпусе, "\n'
    )
    require(overclaim in runner, "Не найдена формулировка, требующая уточнения полноты карты")
    runner = runner.replace(
        overclaim,
        '        "Поэтому этот диагностический запуск на расширенной, но частичной карте показывает совпадения только для "\n'
        '        "одно-предпосылочных операторных паттернов и не оценивает многопредпосылочные группы Luck 2010, "\n'
    )
    report_anchor = (
        '    lines += [\n'
        '        "",\n'
        '        "## Интерпретация и ограничения",'
    )
    require(report_anchor in runner, "Не найден раздел интерпретации для диагностики карты Luck 2010")
    luck_section = (
        '    target_id = "luck2010"\n'
        '    luck_map = next(item for item in snapshots if item["article_id"] == target_id)\n'
        '    arities = Counter(len(item["sources"]) for item in luck_map["graph"]["transitions"])\n'
        '    lines += ["", "### Отложенная карта Luck 2010", "",\n'
        '              "| Режим | Кандидатов | Оцениваемых одно-предпосылочных переходов | Совпадений |",\n'
        '              "|---|---:|---:|---:|"]\n'
        '    for mode, label in (("graph", "Авторские зависимости"),\n'
        '                        ("semantic_without_dependencies", "Без зависимостей")):\n'
        '        item = modes[mode][target_id]\n'
        '        lines.append(f"| {label} | {item[\'candidate_count\']} | {item[\'target_transition_count\']} | "\n'
        '                     f"{item[\'unique_patterns_hit\']} |")\n'
        '    lines += ["",\n'
        '              f"В карте 38 знаний и {len(luck_map[\'graph\'][\'transitions\'])} групп зависимостей: "\n'
        '              f"{arities.get(2, 0)} с двумя входами, {arities.get(3, 0)} с тремя, "\n'
        '              f"{sum(count for arity, count in arities.items() if arity > 3)} с более чем тремя. "\n'
        '              "Оценщик учитывает только один вход, поэтому для этой цели он не измеряет перенос "\n'
        '              "ни по одной из 14 групп. Нулевое число совпадений здесь означает отсутствие оцениваемых "\n'
        '              "переходов, а не опровержение многопредпосылочных паттернов.", ""]\n'
    )
    runner = runner.replace(report_anchor, luck_section + report_anchor)
    for expected in ("Офлайн-проверка переноса операторных мотивов после замены карты Luck 2010.",
                     "# Проверка операторных паттернов после замены карты Luck 2010",
                     "Предыдущая короткая карта Luck 2010 заменена отдельным ручным черновиком",
                     'item["article_id"] == "luck2010")["graph"]',
                     "20 из 44 единиц источника представлены знаниями",
                     "### Отложенная карта Luck 2010",
                     "не измеряет перенос"):
        require(expected in runner, f"Не удалось подготовить независимую версию отчёта: {expected}")
    require("добавила ли полная карта новые структурные совпадения" not in runner,
            "В новом отчёте осталась недостоверная формулировка о полноте карты")
    require("146 из 186" not in runner, "В новом отчёте осталась диагностика старой карты Manly")
    write_immutable(new_root / "inputs.json", manifest_bytes)
    write_immutable(new_root / "run_experiment.py", runner.encode("utf-8"))
    write_immutable(new_root / "preparation.json", json.dumps({
        "protocol": "leave-one-publication-out operator transfer",
        "replaced_article_id": "luck2010",
        "new_map_run_id": map_value["run_id"],
        "new_map_file_sha256": sha256(raw_map).hexdigest(),
        "target_article_source_sha256_excluded": manifest["excluded_target_source_sha256"],
        "model_calls": 0, "network_disabled": True,
    }, ensure_ascii=False, indent=2).encode("utf-8"))
    return new_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    output = prepare(args.root.resolve())
    print(output)


if __name__ == "__main__":
    main()
