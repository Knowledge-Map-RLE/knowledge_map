"""Готовит русский отчёт по запечатанным условным временным гипотезам."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.timed_protocol_hypotheses import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.timed_protocol_hypotheses import FileTimedHypothesisInputs
from tools.run_free_prediction import disable_network

REPORT_VERSION = "timed-protocol-hypothesis-report-3"


def _clock_text(days):
    return ", ".join(days) if days else "не установлено"


def _dose_text(dose):
    unit = {"microgram": "мкг", "mg/kg": "мг/кг"}.get(dose["unit"], dose["unit"])
    return f"{dose['value']} {unit}"


def _population_text(witness):
    if witness["source_key"] == "tros":
        return "мыши с трансгенным человеческим TNFR1 и дефицитом мышиного TNFR1, с MOG35–55-индуцированным EAE (PMC5651799)"
    if witness["source_key"] == "atros":
        return "самки мышей линии hTNFR1-K/I с MOG-индуцированным EAE (PMC8294390)"
    raise ValueError("Неизвестный источник популяции")


def build_report(result, review, clock):
    witnesses = {w["case_id"]: w for w in review["witnesses"]}
    proofs = {p["procedure"]: p for p in clock["clock_proofs"]}
    graph = result["modes"]["graph"]
    same = result["modes"]["same_facts_without_dependencies"]
    permuted = result["modes"]["permuted_dependencies"]
    lines = [
        "# Условные гипотезы из повторяющегося временного паттерна", "",
        f"Запуск `{result['run_id']}` использует {result['canonical_blocks']} канонических знаний и "
        f"{result['semantic_statements']} семантических утверждений всего корпуса. "
        f"Для генератора вручную лицензированы {result['licensed_source_cases']} прошлых опытных случая из двух первичных семейств.", "",
        "## Найденное сходство", "",
        "В двух ранее опубликованных опытах с экспериментальным аутоиммунным энцефаломиелитом (EAE) средняя клиническая оценка на рисунке ниже контроля "
        "в выбранной точке. Точка равна 17 дням после первого введения внутри своего собственного опыта: "
        "TROS — день 25 после иммунизации минус первое введение в день 8; Atrosimab — день 18 минус первое введение в день 1. "
        "Совпадает относительная координата, а не физический момент, препарат, популяция или шкала.", "",
        "| Происхождение дозы и курса | Доза | Курс относительно первого введения | Контроль из того же опыта |",
        "| --- | --- | --- | --- |",
    ]
    for w in review["witnesses"]:
        proof = proofs[w["procedure"]]
        schedule = [p["point"]["value"] for p in proof["relative_doses"]]
        dose = "; ".join(_dose_text(d) for d in w["dose_groups"])
        lines.append(f"| {w['intervention_label']} | {dose} | {_clock_text(schedule)} | {w['comparator_label']} |")
    lines += [
        "", "Это два вручную прочитанных графика, не автоматически снятые измерения. Точные значения средних и значимость выбранной точки не извлекались. "
        "Обе точки видны в прошлых источниках и использованы для разработки шаблона; они не являются независимыми или будущими контрольными случаями.", "",
        "## Сформированные кандидаты", "",
        f"Сценарий генератора нашёл {len(graph)} различных дозовых сочетания. Контроль с теми же знаниями и той же семантической проверкой, но без рёбер зависимостей, нашёл {len(same)}; "
        f"их идентификаторы {'совпадают' if {p['id'] for p in graph} == {p['id'] for p in same} else 'различаются'}. "
        f"Режим переставленных зависимостей нашёл {len(permuted)}. Пустой результат этого режима сам по себе не доказывает преимущество графа.", "",
    ]
    for index, proposal in enumerate(graph, 1):
        scenario = proposal["scenario"]
        donor = witnesses[scenario["intervention_source_case"]]
        recipient = witnesses[scenario["population_class_source_case"]]
        proof = proofs[donor["procedure"]]
        schedule = [p["point"]["value"] for p in proof["relative_doses"]]
        dose = scenario["dose"]
        population = _population_text(recipient)
        dose_text = _dose_text(dose)
        lines += [
            f"### Кандидат {index}", "",
            f"Предлагаемая доза — {dose_text}; курс — {_clock_text(schedule)} дней от первого введения. "
            f"Воздействие предлагается проверить в контексте модели и популяции, взятом из опыта {recipient['intervention_label']}: {population}. "
            f"Контроль предлагается сохранить из опыта-донора дозы: {donor['comparator_label']}. Оценка — через 17 дней после первого введения.", "",
            f"**Условное ожидаемое направление:** если такой опыт провести, средняя клиническая оценка в лечебной группе может быть ниже соответствующего контроля. "
            "Это гипотеза для проверки, не выполненное действие и не установленный результат.", "",
            "Использованные основания: источниковое функциональное свидетельство и совместимость домена мишени; перенос дозы и графика введений; "
            "контекст популяции и клинического измерения из второго опыта; общая точка оценки по относительному времени. "
            "Общая мишень и сходство грубых признаков применимости организуют аналогию, но не доказывают эффективность в новом сочетании.", "",
        ]
    lines += [
        "## Чем кандидаты ограничены", "",
        "Это **не подтверждённые новые научные прогнозы**. Перенос проводится между разными препаратами и экспериментальными контекстами. "
        "Остаются различия генетических конструкций, пола, возраста, индукции заболевания, контрольных вмешательств и шкал. "
        "Возможная совместимость человеческого внеклеточного домена TNFR1 не устанавливает ингибирование мишени в организме принимающей модели.", "",
        "Для проверки ещё требуется заранее задать численность и распределение животных по группам, точный протокол контроля, способ оценивания и статистический анализ. "
        "Нижнее среднее на порядковой шкале не гарантирует такой же порядок при произвольной перекодировке; графики не сообщают точные средние и p для выбранного дня. "
        "Поэтому величина эффекта, статистическая значимость, непрерывность эффекта и причинность не прогнозируются.", "",
        "Обнаружение общей точки было ручным поиском по двум источникам и только двум лицензированным случаям из корпуса 943 знаний. "
        "Покрытие паттернами всей карты не достигнуто. Отсутствие гипотезы в других знаниях этим опытом не оценивалось.", "",
        "## Что показывает сравнение структуры", "",
        f"При одинаковой проверке фактов граф и семантический контроль дали по {len(graph)} кандидата с одинаковыми идентификаторами. "
        f"Следовательно, в этом опыте рёбра зависимостей не добавили кандидатов. Переставленные связи дали {len(permuted)}, "
        "что диагностирует влияние конкретной процедуры отбора оснований, но ещё не устанавливает общее преимущество карты: источниковые примеры вручную отобраны, "
        "правило локально задано, исходов независимого опыта здесь нет.", "",
        "**Статус:** 0 квалифицированных новых научных прогнозов; критерий успеха не достигнут; преимущество графа не установлено. "
        "Внешние и локальные модельные вызовы, эмбеддинги и чтение будущей цели — 0.", "",
    ]
    return "\n".join(lines) + "\n"


def render_html(markdown, result):
    title = "Условные гипотезы временного паттерна"
    cards = []
    for index, proposal in enumerate(result["modes"]["graph"], 1):
        scenario = proposal["scenario"]
        dose = scenario["dose"]
        details = "".join(f"<li>{escape(value)}</li>" for value in proposal["unverified_changes_ru"])
        cards.append(
            f"<article><h2>Кандидат {index}</h2><p><strong>Протокол:</strong> {escape(_dose_text(dose))}; "
            f"оценка через 17 дней после первого введения.</p><p><strong>Гипотеза:</strong> средняя клиническая оценка в лечебной группе может быть ниже, чем в контрольной. "
            f"Статус: условная гипотеза, требующая опыта.</p><details><summary>Непроверенные переносы и ограничения</summary><ul>{details}</ul></details></article>"
        )
    comparison = (f"Граф: {len(result['modes']['graph'])}; без рёбер зависимостей: "
                  f"{len(result['modes']['same_facts_without_dependencies'])}; переставленные связи: "
                  f"{len(result['modes']['permuted_dependencies'])}.")
    body = "".join(cards)
    return (
        "<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{escape(title)}</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:940px;margin:2rem auto;padding:0 1rem;color:#17212b;background:#f5f7fa}}"
        "h1,h2{line-height:1.2}article{background:white;border:1px solid #d9e1ea;border-radius:12px;padding:1rem 1.3rem;margin:1rem 0}"
        "aside{background:#fff1dc;border-left:4px solid #be6d00;padding:1rem}table{border-collapse:collapse}td,th{border:1px solid #ccd4de;padding:.5rem}code{overflow-wrap:anywhere}</style>"
        f"<body><h1>{escape(title)}</h1><p>Запуск <code>{escape(result['run_id'])}</code>. {escape(comparison)}</p>"
        "<aside><strong>Исследовательские кандидаты, не установленные результаты.</strong> Общая относительная точка выбрана вручную в двух прошлых опытах; "
        "величина эффекта и значимость не выводятся. Критерий научного успеха не достигнут.</aside>"
        f"{body}<h2>Подробный русский отчёт</h2><pre>{escape(markdown)}</pre></body></html>\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--source-review", required=True)
    args = parser.parse_args()
    disable_network()
    run_dir = Path(args.run).resolve()
    store = FilePredictionStore(run_dir.parent)
    run_id = run_dir.name
    result = store.read_seal(run_id)
    require(result is not None and result["version"] == VERSION, "Unsupported or missing sealed timed hypothesis run")
    review, clock, functional, frozen, maps = FileTimedHypothesisInputs(args.source_review).load()
    expected = {
        "version": VERSION,
        "review_sha256": fingerprint(review),
        "clock_sha256": fingerprint(clock),
        "functional_sha256": fingerprint(functional),
        "frozen_sha256": fingerprint(frozen),
        "map_hashes": [fingerprint(m) for m in maps],
        "implementation": result["binding"]["implementation"],
    }
    require(result["run_id"] == fingerprint(result["binding"]) and result["binding"] == expected,
            "Run is not bound to these explicit source and corpus snapshots")
    require(result["model_calls"] == 0 and result["target_read"] is False, "Unexpected model or target access")
    for source, digest in result["binding"]["implementation"].items():
        snapshot = run_dir / "implementation" / source
        require(snapshot.is_file() and sha256(snapshot.read_bytes()).hexdigest() == digest,
                "Sealed implementation snapshot differs")
    markdown = build_report(result, review, clock)
    html = render_html(markdown, result)
    output = run_dir / "review-v2"
    write_immutable(output / "report.ru.md", markdown.encode("utf-8"))
    write_immutable(output / "report.html", html.encode("utf-8"))
    verification = {
        "version": REPORT_VERSION,
        "run_id": run_id,
        "prediction_sha256": fingerprint(result),
        "report_ru_sha256": sha256(markdown.encode("utf-8")).hexdigest(),
        "report_html_sha256": sha256(html.encode("utf-8")).hexdigest(),
        "renderer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_case_count": len(review["witnesses"]),
        "candidate_counts": {mode: len(items) for mode, items in result["modes"].items()},
        "graph_and_semantic_ids_equal": {p["id"] for p in result["modes"]["graph"]}
        == {p["id"] for p in result["modes"]["same_facts_without_dependencies"]},
        "qualified_new_scientific_forecasts": result["qualified_new_scientific_forecasts"],
        "graph_advantage_demonstrated": result["graph_advantage_demonstrated"],
        "model_calls": result["model_calls"],
        "target_read": result["target_read"],
    }
    write_immutable(output / "verification.json", (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
