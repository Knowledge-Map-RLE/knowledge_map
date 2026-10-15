"""Двуязычный автономный отчёт об опубликованности предсказанных результатов."""
import argparse
import json
from pathlib import Path

from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--review-name", default="review-v1")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = FilePredictionStore(root / "runs").read_seal(args.run_id)
    require(result is not None, "Control audit seal required")
    screening = json.loads((root / "prepared/screening.json").read_text(encoding="utf8"))
    labels = json.loads((root / "prepared/labels.en.json").read_text(encoding="utf8"))
    require(screening["forecast_run_id"] == result["inputs"]["forecast"]["run_id"], "Screening belongs to another forecast")
    for row in screening["records"]:
        require(row["status"] in labels["reasons"], "English screening label missing")
        row["reason_en"] = labels["reasons"][row["status"]]
    control = result["inputs"]["control"]
    # Полный защищённый источник не копируется в HTML; доступны координаты и ссылка.
    public_control = {key: control[key] for key in ("doi", "url", "title", "publication_date", "cohort_ids", "anchors", "selection_status", "selection_limit")}
    data = {"run_id": result["run_id"], "forecast_run_id": screening["forecast_run_id"],
            "audit": result["audit"], "control": public_control, "screening": screening,
            "context_limits_en": labels["context_limits"], "model_calls": 0}
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True).replace("<", "\\u003c").replace("&", "\\u0026")
    template = (Path(__file__).resolve().parents[1] / "infrastructure/transfer_control_report.html").read_text(encoding="utf8")
    require(args.review_name in {"review-v1", "review-v2"}, "Unknown review revision")
    out = root / args.review_name
    write_immutable(out / "report.html", template.replace("__DATA__", payload).encode("utf8"))
    write_immutable(out / "data.json", (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf8"))
    markdown = f'''# Проверка независимого источника ROSMAP

Две гипотезы остаются зафиксированными. В полном тексте нового источника **не найдено сопоставимого опубликованного результата**: возраст и образование используются в модели, но нужные коэффициенты не представлены; немнестический MCI отдельно не выделен. Приложение содержит только схему переходов с числами участников.

**Проверяемых предсказанных связей: 0. Совпадений: 0. Несовпадений: 0.** Это отсутствие возможности оценки, а не отрицательный результат исследования. Доля верных прогнозов не определена. Критерий успеха не достигнут.

## Проверенный источник

[Zammit et al. — ROSMAP](https://academic.oup.com/biomedgerontology/article/80/1/glae275/7900996), DOI `10.1093/gerona/glae275`, опубликован онлайн 15 ноября 2024 года. Проверены полный научный текст, три таблицы, подписи двух основных рисунков, текст и встроенный рисунок приложения. Страничная вёрстка DOCX не рендерилась; исходный TIFF просмотрен непосредственно. Общая численность в методах — 1255, исходная когниция нормальная; модель — Cox с несколькими состояниями. Индивидуальные реестры участников не проверялись, независимость от обучения установлена на уровне разных когорт.

Возрастные средние групп не заменяют hazard-контраст. Использование фактора как поправки не означает положительный коэффициент. Общий MCI не заменяет немнестический подтип. Обнаружение паркинсонизма до MCI — другой фактор и не засчитывается как совпадение.

## Базовые режимы

| Режим | Кандидаты | Проверяемые результаты | Совпадения |
| --- | ---: | ---: | ---: |
| Семантический перенос | 2 | 0 | 0 |
| Известные знания | 17 | 0 | 0 |
| Частотная база | 11 | 0 | 0 |

Число кандидатов — объём прогнозного списка, а не число совпадений. Преимущество графа над базовыми режимами здесь не измерено.

## Реестр отбора

Исходный нечёткий поиск Crossref дал 19 кандидатов. После фиксации гипотез добавлен нейтральный поиск статей об инцидентном MCI: 39 записей. Всего 55 уникальных метаданных. Реестр содержит причины исключений и уровень проверки; метаданные не означают наличие подходящего полного исследования. Поиск не исчерпывающий, окончательный первый оцениваемый контроль не выбран: остаются нерешённые доступ, пожилые подгруппы и даты. ROSMAP проверен как доступный независимый кандидат, не выбран по удобству его исхода.

Проверено важное расхождение дат: BMI-статья `10.1093/gerona/glad263` вышла онлайн 14 ноября 2023 года, хотя номер журнала датирован 2024. Она не является публикацией после обучающего среза. Публикация ROSMAP датирована 15 ноября 2024; даты индекса и выпуска отличаются.

PATH использует OR в дискретном анализе, Otassha — логистическую модель и MMSE-критерий, китайская статья анализирует факторы исходного диагноза отдельно от инцидентности. Эти результаты не подменяют зафиксированные hazard-утверждения.

## Следующий необходимый полный текст

TARCC: **DOI `10.1176/appi.neuropsych.20230180`**, An 11-Fold Higher Risk of Incident Mild Cognitive Impairment With Hispanic Ethnicity and Baseline Neuropsychiatric Symptoms. По аннотации есть Cox-анализ инцидентного MCI, но полный текст сервером не выдан (403). Наличие нужных коэффициентов неизвестно. Контактировать с авторами не будем. Другие кандидаты с нерешёнными возрастными подгруппами не объявлены окончательно непригодными.

## Сохранность и ограничения

Прогноз `{screening['forecast_run_id']}` не пересчитывался и не редактировался. Аудит `{result['run_id']}` хранится отдельно. Проверяются хеши полного источника, приложения, разметки и Unicode-координат; сеть в оценщике выключена. GOLD, Neo4j, прежние карты и сервисы не изменены. Модельные вызовы, эмбеддинги и переводчик: 0. Русский и английский подготовлены Codex; расход токенов сессии не измерен.

Это исторический контроль, проведённый после публикации статей; он не является прогнозом до их выхода. Параметрическое незнание Codex не удостоверено, программный генератор новые источники не читает. Автоматическая техническая проверка не заменяет экспертную научную проверку.
'''
    write_immutable(out / "report.ru.md", markdown.encode("utf8"))
    print(json.dumps({"report": str(out / "report.html"), "run_id": result["run_id"]}))


if __name__ == "__main__":
    main()
