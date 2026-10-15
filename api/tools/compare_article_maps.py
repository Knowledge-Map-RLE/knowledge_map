"""Административное сравнение только явно перечисленных запусков, без AI-клиентов."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import sys
from hashlib import sha256
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import require, fingerprint
from application.compare_article_maps import CompareArticleMaps
from infrastructure.article_comparison_controls import FixedComparisonControls
from infrastructure.article_comparison_offline import render_comparison
from tools.import_codex_article_map import prohibit_generation


def report(result):
    lines = ["# Сравнение PMC10000452 с пятью картами схемы 6", "", "Карты и сравнение подготовлены Codex без внешних/локальных LLM, переводчика и эмбеддингов. Этот сценарий выполняет сравнение; отдельный предиктор не входит в его вычисления. Разметка контрольных пар требует экспертной проверки; автоматические отношения не устанавливают научную корректность.", "",
        "Сравнение использует только перечисленные неизменяемые запуски. Источник PMC10000452 и утверждённый запуск не исправлялись. Видимые правила графа: KM.TEXT_TO_MAP v3, зависимости v15; все полные источники подтверждены, предыдущие версии сохранены.", "",
        "| Статья / документ | Запуск | Знания | Утверждения | Стрелки | Слои |", "|---|---|---:|---:|---:|---:|"]
    for m in result["maps"]:
        a = m["graph"]["analysis"]
        lines.append(f'| {m["article_id"]} | {m["run_id"]} | {len(m["graph"]["knowledge"])} | {a["statement_count"]} | {len(m["graph"]["edges"])} | {a["depth"]} |')
    unique = result["summary"]["unique_target_knowledge_by_relation"]
    lines += ["", "## Уникальные знания цели", "",
        f'Полное совпадение: {len(unique["equivalent"])}; частичное сходство: {len(unique["partial"])}; общий шаблон: {len(unique["template"])}; тематическое сходство: {len(unique["topical"])}.',
        f'Совпавшие параметры: {len(result["summary"]["shared_attribute_targets"])} блоков. Категории могут пересекаться. Параметр или общий шаблон не означает покрытия всего знания.', "",
        f'Описательная копия текста отделена от фактических атрибутов в {result["summary"]["auxiliary_description_count"]} утверждениях цели. Она сохранена в auxiliary_attributes сравнительного JSON. Числовые диапазоны с явно указанными границами нормализованы одинаково. Исходные карты не изменены.', "",
        "Сравнение остаётся строгим к контексту: общая часть составного блока и целый блок учитываются раздельно. Неполная атомизация в исходном semantic_frame остаётся ограничением; свободный текст не объявляется набором независимо доказанных фактов автоматически."]
    lines += ["", f'Всего {result["analysis"]["pair_count"]} пар канонических знаний. Нормализатор: {result["analysis"]["normalizer_version"]}; сравнитель: {result["analysis"]["comparator_version"]}. Словарь, контрольный набор, карты и источники связаны хешами в JSON.', "",
        "BM25 использует только тексты блоков с лексической нормализацией. Семантический режим сопоставляет отдельные утверждения, роли, ограничения и размерности. Совместный режим объединяет ранги по RRF с k=60. Равные баллы имеют стабильные фактические позиции, поэтому top-k соответствует показанной выдаче. DOI, PMCID и номера ссылок исключены из признаков.", "",
        "Отдельно показаны общие предикатные шаблоны и трёхуровневые сигнатуры DAG с сохранением совместных предпосылок/альтернативных групп. Их сходство не делает факты эквивалентными. Покрытие в обе стороны требует совместимых утверждений и известного контекста; составные блоки сопоставляются по утверждениям, включая соответствия нескольким блокам.", "",
        "## Диагностика семи мест цитирования", "", "Контрольные фрагменты найдены Codex в полных текстах и зафиксированы до первого вычисления баллов. Проверены исходные XML-xref, Unicode-координаты и хеши. Ссылки 3/5/6/17 имеют по одному месту, 41 — три. Цитирование не считается доказательством эквивалентности.", "", "| Режим | Top-1 | Top-5 | Top-10 |", "|---|---:|---:|---:|"]
    for mode, metrics in result["evaluation"]["retrieval_at_k"].items():
        lines.append("| " + mode + " | " + " | ".join(f'{metrics[str(k)]["found"]}/{metrics[str(k)]["total"]}' for k in (1, 5, 10)) + " |")
    for observation in result["evaluation"]["observations"]:
        lines += ["", f'### {observation["id"]}', "", observation["rationale_ru"], "",
            f'Ранги: {observation["ranks"]}. Найденные отношения: {observation["retrieved_relations"]}. Поля расхождений: {observation["detected_difference_fields"]}.']
    lines += ["", "## Ограничения и следующий разбор", "",
        "Обязательное расхождение [6]: проценты 22,5/60,1 в PMC10000452 против частот на 1000 человеко-лет в PMC6416157. Исходные формулировки обеих карт сохранены. Из-за неизвестного/разного контекста высокие текстовые оценки не подтверждают эквивалентность. Сыворотка и плазма не автоматически синонимы; число вопросов сна, фазы, выборки и длительность записей различаются.", "",
        "Нормализация намеренно консервативна: точные алиасы словаря, явные размерности и безопасное раскрытие локальных ссылок, включая циклы скрытой семантики. Свободные описания контекста и неоднозначные величины не угадываются. В составном блоке одна часть может совпасть, другая — расходиться. Отсутствие эквивалентности не означает, что факт ложен; небольшой контрольный набор не оценивает качество на всём корпусе.", "",
        f'Эквивалентных пар: {result["summary"]["equivalent_pairs"]}. Отношения всех пар: {result["summary"]["relations"]}.', "",
        "Полные причины исходных числовых расхождений, покрытие таблиц и ограничения каждой карты находятся в её отдельном русском отчёте. Исходные GOLD-эталоны и накопительный эксперимент не изменены. Модельные вызовы: 0; расход токенов сессии Codex не доступен и не выдумывался.", "",
        "JSON содержит все пары, карты и исходные фрагменты. Автономный HTML включает весь набор, поиск/фильтры, страницы по десять, две карты, панорамирование/масштаб и отдельные готовые русские подписи. Следующий шаг — совместный экспертный разбор, без запуска предиктора и без пересборки остальных статей."]
    return "\n".join(lines) + "\n"


def run(references_file, output):
    prohibit_generation()
    from infrastructure.config import settings
    from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
    from infrastructure.neo4j.article_comparisons_repository import Neo4jArticleComparisonsRepository
    references = json.loads(references_file.read_text(encoding="utf-8"))
    require(set(references) == {"target", "sources"}, "Explicit target and source runs required")
    maps = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    try:
        owners = []
        with maps.driver.session() as session:
            for ref in [references["target"], *references["sources"]]:
                row = session.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=ref["article_id"]).single()
                require(row is not None and bool(row["owner"]), "Selected article owner missing")
                owners.append(row["owner"])
        require(len(set(owners)) == 1, "CLI comparison requires a common owner for all selected articles")
        repository = Neo4jArticleComparisonsRepository(maps)
        result = CompareArticleMaps(maps, repository, FixedComparisonControls()).execute(references["target"], references["sources"], owners[0])
        result["pairs"] = repository.export_pairs(result["comparison_id"], owners[0])
        require(len(result["pairs"]) == result["analysis"]["pair_count"], "Stored comparison is incomplete")
        folder = output / result["comparison_id"]
        folder.mkdir(parents=True, exist_ok=True)
        def write(name, value):
            data = value.encode("utf-8")
            path = folder / name
            if path.exists(): require(path.read_bytes() == data, "Immutable comparison artifact differs")
            else:
                with path.open("xb") as f: f.write(data)
        write("comparison.json", json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        write("comparison.html", render_comparison(result))
        write("report.ru.md", report(result))
        write("controls.frozen.json", json.dumps(result["controls"], ensure_ascii=False, indent=2))
        write("normalization.json", json.dumps(result["normalization"], ensure_ascii=False, indent=2))
        write("manifest.json", json.dumps({"comparison_id": result["comparison_id"], "binding": result["binding"],
            "model_calls": 0, "expert_validated": False, "files": {name: sha256((folder/name).read_bytes()).hexdigest()
                for name in ("comparison.json", "comparison.html", "report.ru.md", "controls.frozen.json", "normalization.json")}}, ensure_ascii=False, indent=2))
        require(not any(n.startswith("infrastructure.article_map_model") for n in sys.modules), "Unexpected AI gateway import")
        print(json.dumps({"saved": True, "folder": str(folder), "comparison_id": result["comparison_id"],
            "pairs": result["analysis"]["pair_count"], "retrieval_at_k": result["evaluation"]["retrieval_at_k"], "model_calls": 0}), flush=True)
    finally:
        maps.close()


if __name__ == "__main__":
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required by AGENTS.md")
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.references.resolve(), args.output.resolve())
