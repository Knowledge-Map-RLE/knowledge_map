"""Создаёт выборочные ручные карты двух ранее просмотренных когортных статей."""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pypdfium2 as pdfium

ROOT = Path(r"D:\Knowledge_Map")
sys.path.insert(0, str(ROOT / "api"))

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import DEPENDENCY_PROMPT_PATH, PROMPT_PATH
from domain.article_maps import digest, prepare_source, require
from domain.empirical_evidence_eligibility import audit as audit_evidence_origin
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


SOURCE_ROOT = ROOT / "eval/free_prediction/primary-pdf-cohort-v1/sources"
OUTPUT_ROOT = ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs"
ARTICLES = {
    "roberts2012": {
        "doi": "10.1212/wnl.0b013e3182452862",
        "title": "The incidence of MCI differs by subtype and is higher in men: The Mayo Clinic Study of Aging",
        "title_ru": "Частота MCI различается по подтипам и выше у мужчин: исследование старения клиники Mayo",
        "pdf_sha256": "af6ad3363c94bb252575fe84a39701fdd8fa8bac0673ed5f090d0ba75715d873",
        "layout_sha256": "44072bfc76b4bd62470235c20d5dbb02d54c13cc14aedacfa04f57819a609f56",
        "pages": 12,
        "visually_reviewed_pages": list(range(1, 13)),
        "table_pages": [5, 6],
    },
    "katz2012": {
        "doi": "10.1097/wad.0b013e31823dbcfc",
        "title": "Age-specific and sex-specific prevalence and incidence of mild cognitive impairment, dementia, and Alzheimer dementia in blacks and whites: A report from the Einstein Aging Study",
        "title_ru": "Распространённость и частота MCI, деменции и болезни Альцгеймера по возрасту и полу: исследование старения Эйнштейна",
        "pdf_sha256": "915a34e119b2d384669ebeccc3ed519603ee0d462a823b688a6edff03f0321ab",
        "layout_sha256": "12c2142aa2283aa776e19e6af035bf7d995ca04ac70dba78764ae10585e912ed",
        "pages": 9,
        "visually_reviewed_pages": list(range(1, 10)),
        "table_pages": [3, 4, 6, 7],
    },
}


def _normalize(value: str) -> str:
    value = re.sub(r"[\-\u00ad\x02\u2010-\u2015]", "", value.casefold())
    return " ".join(value.split())


def extract_pdf(pdf_path: Path) -> tuple[str, list[tuple[int, int]], list[str]]:
    """Извлекает текст постранично и сохраняет координаты страниц в кодовых точках."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="pypdfium2")
        document = pdfium.PdfDocument(str(pdf_path))
        pages = []
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            text = text_page.get_text_range()
            text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
            text = "\n\n".join(line.strip() for line in text.splitlines() if line.strip())
            require(bool(text), f"PDF page {index + 1} has no extractable text")
            pages.append(text)
            text_page.close()
            page.close()
        document.close()
    page_ranges = []
    cursor = 0
    for page in pages:
        page_ranges.append((cursor, cursor + len(page)))
        cursor += len(page) + 2
    return "\n\n".join(pages), page_ranges, pages


def source_unit(source: dict, page_ranges: list[tuple[int, int]], page: int, anchor: str) -> list[str]:
    """Находит исходные единицы по проверенной странице и фразе из PDF."""
    start, end = page_ranges[page - 1]
    needle = _normalize(anchor)
    candidates = [unit for unit in source["units"]
                  if unit["start"] < end and unit["end"] > start]
    parts = []
    cursor = 0
    normalized_units = []
    for item in candidates:
        normalized = _normalize(item["text"])
        if not normalized:
            continue
        normalized_units.append(normalized)
        parts.append((item["id"], cursor, cursor + len(normalized)))
        cursor += len(normalized) + 1
    joined = " ".join(normalized_units)
    match_start = joined.find(needle)
    require(match_start >= 0, f"Reviewed source anchor not found on page {page}: {anchor}")
    match_end = match_start + len(needle)
    return [unit_id for unit_id, part_start, part_end in parts
            if part_start < match_end and part_end > match_start]


def validate_authored_polarity(authored: dict) -> None:
    """Отклоняет двойное кодирование отрицания в предикате и отдельном флаге."""
    for item in authored["knowledge"]:
        claims = item.get("claims") or [item]
        for claim in claims:
            predicate = claim.get("predicate", item.get("predicate", ""))
            negated = claim.get("negated", item.get("negated", False))
            require(not (negated and re.search(r"\b(?:no|not|never|without)\b", predicate, re.IGNORECASE)),
                    f"Negation is encoded twice in {item['key']}: {predicate}")


def build_authored(article_id: str, source: dict, page_ranges: list[tuple[int, int]]) -> dict:
    records = []
    transitions = []

    def unit(page: int, anchor: str) -> list[str]:
        return source_unit(source, page_ranges, page, anchor)

    def add(key: str, en: str, ru: str, predicate: str, refs: list[tuple[int, str]], roles: dict,
            *, attrs: dict | None = None, kind: str = "state", knowledge_type: str = "result",
            claims: list[dict] | None = None, logic: str = "single", conditions: list[str] | None = None,
            time: str | None = None, modality: str | None = None) -> None:
        unit_ids = list(dict.fromkeys(uid for page, anchor in refs for uid in unit(page, anchor)))
        record = {"key": key, "en": en, "ru": ru, "predicate": predicate, "units": unit_ids,
                  "roles": roles, "attrs": attrs or {}, "kind": kind, "type": knowledge_type,
                  "logic": logic, "time": time, "conditions": conditions or [], "modality": modality}
        if claims:
            record["claims"] = claims
        records.append(record)
        return record

    def transition(sources: list[str], target: str, usage: str, reason: str,
                   refs: list[tuple[int, str]]) -> None:
        knowledge_units = {item["key"]: item["units"] for item in records}
        endpoint_units = [unit_id for key in [*sources, target]
                          for unit_id in knowledge_units[key]]
        cited_units = [unit_id for page, anchor in refs for unit_id in unit(page, anchor)]
        transitions.append({"sources": sources, "target": target, "usage": usage,
                            "reason": reason,
                            "units": list(dict.fromkeys([*endpoint_units, *cited_units]))})

    common_conditions = ["This is an observational cohort result; it does not establish causation."]
    if article_id == "roberts2012":
        add("study-design",
            "The Mayo Clinic Study of Aging was a population-based prospective cohort of Olmsted County residents aged 70–89 years on October 1, 2004.",
            "Исследование старения Mayo Clinic было популяционной проспективной когортой жителей округа Олмстед в возрасте 70–89 лет на 1 октября 2004 года.",
            "prospective cohort design", [(1, "population-based prospective cohort"), (2, "70 – 89 years on October")],
            {"study": "Mayo Clinic Study of Aging", "population": "Olmsted County residents aged 70–89 years", "setting": "Olmsted County, Minnesota"},
            knowledge_type="method", attrs={"design": {"value": "prospective population-based cohort", "unit": None},
            "age_range": {"value": "70–89", "unit": "years"}, "baseline_date": {"value": "2004-10-01", "unit": None}},
            time="Baseline October 1, 2004")
        add("diagnostic-criteria",
            "MCI classification required cognitive concern, impairment in at least one of four cognitive domains, preserved or minimally impaired daily function, and no dementia.",
            "Для классификации MCI требовались когнитивная жалоба, нарушение как минимум в одной из четырёх когнитивных областей, сохранная или минимально нарушенная повседневная функция и отсутствие деменции.",
            "study-defined MCI criteria", [(2, "cognitive concern by subject"), (2, "impairment in 1 or more of the 4 cognitive domains")],
            {"classification": "MCI under Mayo Clinic Study of Aging criteria", "participant": "cohort participant"},
            knowledge_type="definition", logic="conjunction", claims=[
                {"predicate": "requires cognitive concern", "roles": {"criterion": "participant, informant, nurse, or physician concern"}},
                {"predicate": "requires domain impairment", "roles": {"criterion": "at least one of four cognitive domains"}},
                {"predicate": "requires preserved function", "roles": {"criterion": "preserved or minimally impaired daily function"}},
                {"predicate": "requires absence of dementia", "roles": {"criterion": "no dementia diagnosis"}},
            ], conditions=["Criteria are the study's operational classification rules."])
        add("subtype-definitions",
            "Amnestic MCI required memory-domain impairment; nonamnestic MCI required no memory impairment and impairment in at least one other domain. Each subtype was further classified as single-domain or multidomain.",
            "Амнестический MCI требовал нарушения памяти; неамнестический MCI — отсутствия нарушения памяти и нарушения как минимум в другой области. Каждый подтип дополнительно делили на однодоменный и многодоменный.",
            "MCI subtype definitions", [(2, "aMCI if the memory domain was impaired"), (2, "naMCI if the memory domain was not impaired")],
            {"classification": "MCI subtype", "parent_definition": "@diagnostic-criteria"},
            knowledge_type="definition", logic="contrast", claims=[
                {"predicate": "amnestic subtype", "roles": {"criterion": "memory domain impaired"}},
                {"predicate": "nonamnestic subtype", "roles": {"criterion": "memory domain not impaired and at least one other domain impaired"}},
                {"predicate": "subtype domain count", "roles": {"classification": "single-domain or multidomain"}},
            ])
        add("assessment-schedule",
            "Participants underwent baseline and approximately 15-month interval evaluations; incident MCI onset was assigned to the midpoint between the last cognitively normal assessment and the first MCI assessment.",
            "Участников обследовали исходно и далее с интервалами около 15 месяцев; начало MCI приписывали середине между последним нормальным обследованием и первым обследованием с MCI.",
            "assessment and onset timing", [(1, "15-month interval evaluations"), (2, "midpoint between the last assessment as cognitively normal")],
            {"cohort": "Mayo Clinic Study of Aging", "assessment": "serial cognitive evaluation", "onset_time": "incident MCI"},
            knowledge_type="method", attrs={"assessment_interval": {"value": 15, "unit": "months"},
            "onset_assignment": {"value": "midpoint between last normal and first MCI assessment", "unit": None}})
        add("primary-risk-set",
            "The primary incidence analysis included 1,450 participants who were cognitively normal at baseline; 296 developed MCI over 4,512.9 person-years, with median follow-up of 3.4 years.",
            "В основной анализ частоты включили 1 450 участников с нормальными когнитивными функциями на исходном этапе; у 296 развился MCI за 4 512,9 человеко-лет при медиане наблюдения 3,4 года.",
            "primary incidence cohort", [(1, "Among 1,450 subjects who were cognitively normal"), (3, "296 incident cases of MCI"), (3, "4,512.9 person-years" )],
            {"study": "Mayo Clinic Study of Aging", "risk_set": "cognitively normal participants at baseline", "outcome": "incident MCI"},
            knowledge_type="observation", attrs={"baseline_risk_set": {"value": 1450, "unit": "participants"},
            "incident_cases": {"value": 296, "unit": "cases"}, "person_time": {"value": 4512.9, "unit": "person-years"},
            "median_follow_up": {"value": 3.4, "unit": "years"}}, time="Baseline to incident MCI, dementia, censoring, or last follow-up")
        add("overall-incidence-rate",
            "The age- and sex-standardized incidence rate of MCI was 63.6 per 1,000 person-years (95% CI 49.2–78.1).",
            "Стандартизованная по возрасту и полу частота MCI составила 63,6 на 1 000 человеко-лет (95% ДИ 49,2–78,1).",
            "incident MCI rate", [(1, "63.6"), (5, "63.6")],
            {"cohort": "Mayo Clinic Study of Aging", "population": "primary cognitively normal cohort", "outcome": "incident MCI"},
            knowledge_type="result", attrs={"incidence_rate": {"value": 63.6, "unit": "per 1,000 person-years"},
            "confidence_interval": {"value": "49.2–78.1", "unit": "95% CI"}}, conditions=common_conditions)
        add("sex-stratified-any-mci",
            "The age-standardized incidence rate of any MCI was higher in men than women: 72.4 versus 57.3 per 1,000 person-years.",
            "Стандартизованная по возрасту частота любого MCI была выше у мужчин, чем у женщин: 72,4 против 57,3 на 1 000 человеко-лет.",
            "sex-stratified incident MCI rate", [(1, "72.4"), (5, "72.4")],
            {"cohort": "Mayo Clinic Study of Aging", "outcome": "any incident MCI", "measure": "incidence per 1,000 person-years"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "incidence rate", "roles": {"sex": "men"}, "attrs": {"rate": {"value": 72.4, "unit": "per 1,000 person-years"}}},
                {"predicate": "incidence rate", "roles": {"sex": "women"}, "attrs": {"rate": {"value": 57.3, "unit": "per 1,000 person-years"}}},
            ], conditions=common_conditions)
        add("subtype-incidence-rates",
            "The age- and sex-standardized incidence rate was 37.7 per 1,000 person-years for amnestic MCI and 14.7 for nonamnestic MCI.",
            "Стандартизованная по возрасту и полу частота составила 37,7 на 1 000 человеко-лет для амнестического MCI и 14,7 для неамнестического MCI.",
            "MCI subtype incidence rates", [(1, "37.7"), (1, "14.7"), (5, "37.7"), (5, "14.7")],
            {"cohort": "Mayo Clinic Study of Aging", "outcome": "incident MCI subtype", "measure": "incidence per 1,000 person-years"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "incidence rate", "roles": {"subtype": "amnestic MCI"}, "attrs": {"rate": {"value": 37.7, "unit": "per 1,000 person-years"}}},
                {"predicate": "incidence rate", "roles": {"subtype": "nonamnestic MCI"}, "attrs": {"rate": {"value": 14.7, "unit": "per 1,000 person-years"}}},
            ], conditions=common_conditions)
        add("sex-by-subtype-rates",
            "Incidence rates were higher in men than women for both amnestic MCI (43.9 vs 33.3) and nonamnestic MCI (20.0 vs 10.9) per 1,000 person-years.",
            "Частоты были выше у мужчин, чем у женщин, для амнестического MCI (43,9 против 33,3) и неамнестического MCI (20,0 против 10,9) на 1 000 человеко-лет.",
            "sex-by-subtype incidence comparison", [(5, "43.9"), (5, "20.0")],
            {"cohort": "Mayo Clinic Study of Aging", "outcome": "incident MCI subtype", "measure": "incidence per 1,000 person-years"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "amnestic MCI incidence rate", "roles": {"sex": "men"}, "attrs": {"rate": {"value": 43.9, "unit": "per 1,000 person-years"}}},
                {"predicate": "amnestic MCI incidence rate", "roles": {"sex": "women"}, "attrs": {"rate": {"value": 33.3, "unit": "per 1,000 person-years"}}},
                {"predicate": "nonamnestic MCI incidence rate", "roles": {"sex": "men"}, "attrs": {"rate": {"value": 20.0, "unit": "per 1,000 person-years"}}},
                {"predicate": "nonamnestic MCI incidence rate", "roles": {"sex": "women"}, "attrs": {"rate": {"value": 10.9, "unit": "per 1,000 person-years"}}},
            ], conditions=common_conditions)
        add("age-and-education-patterns",
            "MCI incidence generally increased with age and declined with increasing education; age-related increases were observed for all four subtypes and were most marked for single-domain amnestic MCI.",
            "Частота MCI в целом повышалась с возрастом и снижалась с увеличением образования; возрастной рост наблюдался для всех четырёх подтипов и был наиболее выражен для однодоменного амнестического MCI.",
            "age and education incidence patterns", [(4, "increased with increasing age"), (4, "declined with increasing levels of education")],
            {"cohort": "Mayo Clinic Study of Aging", "outcome": "incident MCI", "modifiers": "age, education, and subtype"},
            knowledge_type="comparison", logic="conjunction", conditions=[*common_conditions,
            "The article reports stratified rates; the pattern is not a causal effect estimate."])
        add("adjusted-sex-hazard-ratios",
            "In adjusted cohort models, male sex was associated with higher hazards of any MCI (HR 1.40, 95% CI 1.11–1.76), amnestic MCI (HR 1.40, 1.05–1.87), and nonamnestic MCI (HR 2.06, 1.27–3.34).",
            "В скорректированных моделях мужской пол был связан с более высокими рисками любого MCI (HR 1,40; 95% ДИ 1,11–1,76), амнестического MCI (HR 1,40; 1,05–1,87) и неамнестического MCI (HR 2,06; 1,27–3,34).",
            "sex-associated adjusted MCI hazard", [(6, "1.40"), (6, "2.06")],
            {"cohort": "Mayo Clinic Study of Aging", "exposure": "male sex", "reference": "women", "outcome": "incident MCI subtype"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "adjusted hazard ratio", "roles": {"outcome": "any MCI"}, "attrs": {"HR": {"value": 1.40, "unit": "95% CI 1.11–1.76"}, "p": {"value": 0.004, "unit": "P"}}},
                {"predicate": "adjusted hazard ratio", "roles": {"outcome": "amnestic MCI"}, "attrs": {"HR": {"value": 1.40, "unit": "95% CI 1.05–1.87"}, "p": {"value": 0.02, "unit": "P"}}},
                {"predicate": "adjusted hazard ratio", "roles": {"outcome": "nonamnestic MCI"}, "attrs": {"HR": {"value": 2.06, "unit": "95% CI 1.27–3.34"}, "p": {"value": 0.003, "unit": "P"}}},
            ], conditions=[*common_conditions, "Cox proportional hazards models adjusted for age, education, and baseline nonparticipation where applicable."])
        add("education-hazard-ratios",
            "Compared with more than 16 years of education, 9–12 years and fewer than 9 years were associated with higher hazards of any MCI (HR 2.05 and 2.07, respectively).",
            "По сравнению с образованием более 16 лет, 9–12 лет и менее 9 лет были связаны с более высокими рисками любого MCI (HR соответственно 2,05 и 2,07).",
            "education-associated incident MCI hazard", [(6, "2.05"), (6, "2.07")],
            {"cohort": "Mayo Clinic Study of Aging", "exposure": "years of education", "outcome": "any incident MCI", "reference_group": ">16 years"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "adjusted hazard ratio", "roles": {"education": "9–12 years"}, "attrs": {"HR": {"value": 2.05, "unit": "95% CI 1.36–3.09"}, "p": {"value": 0.001, "unit": "P"}}},
                {"predicate": "adjusted hazard ratio", "roles": {"education": "<9 years"}, "attrs": {"HR": {"value": 2.07, "unit": "95% CI 1.26–3.40"}, "p": {"value": 0.004, "unit": "P"}}},
            ], conditions=[*common_conditions, "The model used >16 years of education as the reference category."])
        add("mci-diagnostic-stability",
            "Among 148 participants with at least one follow-up after incident MCI, 98 remained MCI or progressed to dementia and 50 reverted to normal at the first subsequent follow-up.",
            "Среди 148 участников как минимум с одним повторным обследованием после нового MCI у 98 MCI сохранился или прогрессировал до деменции, а у 50 при первом последующем визите классификация вернулась к норме.",
            "MCI follow-up classification", [(4, "148 had at least one subsequent follow-up"), (4, "50 reverted to"), (7, "33.8%")],
            {"cohort": "Mayo Clinic Study of Aging", "population": "participants with incident MCI and subsequent follow-up", "outcome": "next observed cognitive classification"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "remained MCI or progressed to dementia", "roles": {"participants": "98 of 148"}, "attrs": {"proportion": {"value": 66.2, "unit": "percent"}}},
                {"predicate": "reverted to normal", "roles": {"participants": "50 of 148"}, "attrs": {"proportion": {"value": 33.8, "unit": "percent"}}},
            ], conditions=["The article reports the first subsequent observed classification; it does not imply permanent reversion."])
        add("author-interpretation",
            "The authors concluded that risk factors should be investigated separately by MCI subtype and sex because pooled analyses may dilute subtype- and sex-specific associations.",
            "Авторы заключили, что факторы риска следует изучать отдельно по подтипу MCI и полу, поскольку объединённый анализ может сглаживать специфичные для подтипа и пола связи.",
            "author recommendation on stratified analysis", [(1, "risk factors for MCI should be investigated separately"), (8, "pool men with women and aMCI with naMCI")],
            {"authors": "Roberts et al.", "recommendation": "stratify by MCI subtype and sex"},
            knowledge_type="conclusion", modality="author recommendation")
        add("selection-and-generalizability-limitation",
            "The authors noted that nonparticipation and loss to follow-up could affect estimated incidence; baseline nonparticipation was addressed using reciprocal-probability weighting.",
            "Авторы отметили, что неучастие и потеря наблюдения могли повлиять на оценку частоты; исходное неучастие учитывали обратным взвешиванием вероятности.",
            "incidence selection limitation", [(2, "nonparticipation at baseline"), (8, "nonparticipation bias")],
            {"study": "Mayo Clinic Study of Aging", "estimate": "incident MCI"},
            knowledge_type="limitation", modality="possible bias")

        add("incidence-estimation-operation",
            "Estimate age-, sex-, education-, and marital-status-specific MCI incidence by incidence-density methods using cases per 1,000 person-years; directly standardize by age and sex and adjust baseline nonparticipation with reciprocal-probability weighting in Poisson regression.",
            "Рассчитать частоту MCI по возрасту, полу, образованию и семейному положению методом плотности заболеваемости — число случаев на 1 000 человеко-лет; стандартизировать по возрасту и полу и учитывать исходное неучастие обратным взвешиванием вероятности в регрессии Пуассона.",
            "estimate incidence rate", [(2, "We estimated incidence rates by age, sex, education"),
                (2, "incidence density methods"), (2, "directly standardized by age and sex"),
                (2, "reciprocal probability weighting in Poisson regression")],
            {"risk_set": "@primary-risk-set", "case_definition": "@diagnostic-criteria",
             "method": "incidence-density calculation with direct standardization and reciprocal-probability weighting",
             "outcome": "incident MCI"}, kind="action", knowledge_type="operation", logic="conjunction",
            conditions=[*common_conditions, "The reported rate is observational and is not a causal effect."])
        add("fit-adjusted-hazard-models",
            "Fit multivariable proportional-hazards models with age as the time scale to estimate demographic associations with incident MCI; adjust for sex, education, and baseline nonparticipation using reciprocal-probability weighting.",
            "Построить многомерные модели пропорциональных рисков со временем возраста для оценки связей демографических факторов с новым MCI; учитывать пол, образование и исходное неучастие с помощью обратного взвешивания вероятности.",
            "fit Cox proportional-hazards model", [(2, "We used multivariable proportional hazards models"),
                (2, "age as the time scale"), (2, "All models included sex, education"),
                (2, "reciprocal probability weighting")],
            {"risk_set": "@primary-risk-set", "outcome_definition": "@diagnostic-criteria",
             "subtype_definition": "@subtype-definitions", "analysis_model": "Cox proportional hazards",
             "time_scale": "age"}, kind="action", knowledge_type="operation", logic="conjunction",
            conditions=[*common_conditions, "Adjusted associations do not establish causation."])

        transition(["study-design"], "primary-risk-set", "method", "The cohort design, baseline status, and eligibility rules define the primary incidence risk set.", [(1, "cognitively normal at baseline"), (3, "Primary incidence analyses")])
        transition(["primary-risk-set", "diagnostic-criteria"], "incidence-estimation-operation", "method", "The at-risk cohort and operational MCI criteria are inputs to the source-described incidence-density analysis.", [(2, "incidence density methods"), (2, "cases per 1,000 person-years")])
        transition(["incidence-estimation-operation"], "overall-incidence-rate", "result", "The article reports the standardized incidence estimate produced by this procedure.", [(2, "directly standardized by age and sex"), (5, "63.6")])
        transition(["incidence-estimation-operation", "subtype-definitions"], "subtype-incidence-rates", "result", "The incidence procedure is applied to the operationally defined MCI subtypes.", [(2, "aMCI if the memory domain was impaired"), (5, "37.7")])
        transition(["primary-risk-set", "diagnostic-criteria", "subtype-definitions"], "fit-adjusted-hazard-models", "method", "The risk set and operational endpoint definitions are analyzed by the source-described adjusted proportional-hazards procedure.", [(2, "We used multivariable proportional hazards models"), (2, "age as the time scale")])
        transition(["fit-adjusted-hazard-models"], "adjusted-sex-hazard-ratios", "result", "The adjusted model reports sex-associated hazard estimates for the defined incident MCI outcomes.", [(2, "associations of demographic factors with incident MCI"), (6, "1.40")])
        transition(["fit-adjusted-hazard-models"], "education-hazard-ratios", "result", "The adjusted model reports education-associated hazard estimates for incident MCI.", [(2, "associations of demographic factors with incident MCI"), (6, "2.05")])
        transition(["sex-stratified-any-mci", "subtype-incidence-rates", "adjusted-sex-hazard-ratios"], "author-interpretation", "result", "The authors use the observed subtype and sex differences to recommend stratified risk-factor analyses.", [(4, "antagonistic interaction"), (8, "risk factors for MCI")])
        transition(["primary-risk-set"], "selection-and-generalizability-limitation", "condition", "The authors discuss selection and follow-up as limits on incidence estimates from this cohort.", [(8, "nonparticipation bias")])
    elif article_id == "katz2012":
        add("study-design",
            "The Einstein Aging Study used systematic community-based recruitment of Bronx residents aged 70 years or older; 1,944 individuals were enrolled.",
            "В Einstein Aging Study применяли систематический набор жителей Бронкса из общины в возрасте 70 лет и старше; всего включили 1 944 человека.",
            "community cohort design", [(1, "1944 adults aged 70 or older"), (2, "systematic recruiting methods")],
            {"study": "Einstein Aging Study", "population": "Bronx residents aged 70 years or older", "setting": "community-based Bronx cohort"},
            knowledge_type="method", attrs={"sample_size": {"value": 1944, "unit": "participants"}, "minimum_age": {"value": 70, "unit": "years"}},
            time="Enrollment 1993–2004")
        add("mci-definition",
            "Study-defined amnestic MCI required memory impairment and objective memory impairment, without dementia; nonamnestic MCI required impairment in at least one nonmemory domain and no memory impairment.",
            "Для амнестического MCI по критериям исследования требовались нарушение памяти и объективное нарушение памяти при отсутствии деменции; для неамнестического MCI требовалось нарушение как минимум одной области вне памяти без нарушения памяти.",
            "study-defined MCI subtype criteria", [(3, "classified as having aMCI"), (3, "naMCI")],
            {"classification": "MCI subtype under Einstein Aging Study criteria", "participant": "participant free of dementia"},
            knowledge_type="definition", logic="contrast", claims=[
                {"predicate": "amnestic MCI criterion", "roles": {"criterion": "memory impairment with objective impairment; no dementia"}},
                {"predicate": "nonamnestic MCI criterion", "roles": {"criterion": "at least one nonmemory domain impaired; memory not impaired; no dementia"}},
            ], conditions=["The paper notes that subtype definitions and operational criteria can vary across studies."])
        add("follow-up-risk-set",
            "Incidence analyses included 1,168 participants who were free of dementia at baseline and completed at least two clinic evaluations; mean follow-up was 3.9 years (range 1–16 years).",
            "В анализ частоты включили 1 168 участников без деменции на исходном этапе, прошедших как минимум два обследования; среднее наблюдение составило 3,9 года (диапазон 1–16 лет).",
            "incidence analysis risk set", [(4, "1168 participants"), (4, "average of 3.9 years")],
            {"study": "Einstein Aging Study", "population": "baseline dementia-free participants with follow-up", "outcomes": "incident dementia and MCI"},
            knowledge_type="observation", attrs={"risk_set": {"value": 1168, "unit": "participants"},
            "mean_follow_up": {"value": 3.9, "unit": "years"}, "follow_up_range": {"value": "1–16", "unit": "years"}},
            time="Baseline through last follow-up")
        add("baseline-prevalence",
            "At baseline, dementia prevalence was 6.5% and Alzheimer dementia prevalence was 4.9%; among the remaining 1,818 participants, amnestic MCI prevalence was 11.6% and nonamnestic MCI prevalence was 9.9%.",
            "Исходная распространённость деменции составляла 6,5%, болезни Альцгеймера — 4,9%; среди оставшихся 1 818 участников распространённость амнестического MCI составляла 11,6%, неамнестического — 9,9%.",
            "baseline cognitive-status prevalence", [(1, "6.5%"), (1, "4.9% AD"), (4, "1818 remaining"), (4, "11.6%"), (4, "9.9%")],
            {"cohort": "Einstein Aging Study", "timepoint": "baseline", "population": "community-dwelling participants aged 70 years or older"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "prevalence", "roles": {"status": "all-cause dementia"}, "attrs": {"proportion": {"value": 6.5, "unit": "percent"}, "denominator": {"value": 1944, "unit": "participants"}}},
                {"predicate": "prevalence", "roles": {"status": "Alzheimer dementia"}, "attrs": {"proportion": {"value": 4.9, "unit": "percent"}, "denominator": {"value": 1944, "unit": "participants"}}},
                {"predicate": "prevalence", "roles": {"status": "amnestic MCI"}, "attrs": {"proportion": {"value": 11.6, "unit": "percent"}, "denominator": {"value": 1818, "unit": "participants"}}},
                {"predicate": "prevalence", "roles": {"status": "nonamnestic MCI"}, "attrs": {"proportion": {"value": 9.9, "unit": "percent"}, "denominator": {"value": 1818, "unit": "participants"}}},
            ], conditions=["Baseline prevalence and incidence rates are different measures and are kept separate."])
        add("incident-event-counts",
            "During follow-up, the cohort recorded 130 incident dementia cases, 127 incident amnestic MCI cases, and 132 incident nonamnestic MCI cases.",
            "За период наблюдения в когорте зарегистрировали 130 новых случаев деменции, 127 случаев амнестического MCI и 132 случая неамнестического MCI.",
            "incident cognitive outcome counts", [(4, "130 incident dementia cases"), (4, "127 incident aMCI cases"), (4, "132 incident naMCI cases")],
            {"cohort": "Einstein Aging Study", "population": "incidence analysis risk set", "time": "follow-up"},
            knowledge_type="observation", logic="partition", claims=[
                {"predicate": "incident case count", "roles": {"outcome": "dementia"}, "attrs": {"cases": {"value": 130, "unit": "cases"}}},
                {"predicate": "incident case count", "roles": {"outcome": "amnestic MCI"}, "attrs": {"cases": {"value": 127, "unit": "cases"}}},
                {"predicate": "incident case count", "roles": {"outcome": "nonamnestic MCI"}, "attrs": {"cases": {"value": 132, "unit": "cases"}}},
            ], time="Follow-up")
        add("dementia-incidence-rates",
            "The overall incidence rate was 2.89 per 100 person-years for all-cause dementia and 2.26 per 100 person-years for Alzheimer dementia.",
            "Общая частота составила 2,89 на 100 человеко-лет для деменции любой причины и 2,26 на 100 человеко-лет для болезни Альцгеймера.",
            "dementia incidence rate", [(4, "2.89"), (4, "2.26")],
            {"cohort": "Einstein Aging Study", "population": "dementia-free incidence cohort", "measure": "incidence per 100 person-years"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "incidence rate", "roles": {"outcome": "all-cause dementia"}, "attrs": {"rate": {"value": 2.89, "unit": "per 100 person-years"}}},
                {"predicate": "incidence rate", "roles": {"outcome": "Alzheimer dementia"}, "attrs": {"rate": {"value": 2.26, "unit": "per 100 person-years"}}},
            ], conditions=common_conditions)
        add("mci-subtype-incidence-rates",
            "The overall incidence rates were 3.79 per 100 person-years for amnestic MCI and 3.94 for nonamnestic MCI.",
            "Общие частоты составили 3,79 на 100 человеко-лет для амнестического MCI и 3,94 для неамнестического MCI.",
            "MCI subtype incidence rates", [(4, "3.79"), (4, "3.94"), (6, "3.79"), (6, "3.94")],
            {"cohort": "Einstein Aging Study", "population": "incidence analysis risk set", "measure": "incidence per 100 person-years"},
            knowledge_type="comparison", logic="partition", claims=[
                {"predicate": "incidence rate", "roles": {"outcome": "amnestic MCI"}, "attrs": {"rate": {"value": 3.79, "unit": "per 100 person-years"}}},
                {"predicate": "incidence rate", "roles": {"outcome": "nonamnestic MCI"}, "attrs": {"rate": {"value": 3.94, "unit": "per 100 person-years"}}},
            ], conditions=common_conditions)
        add("age-patterns-cognitive-outcomes",
            "Dementia and Alzheimer dementia incidence increased with age; amnestic MCI rates increased with age, whereas nonamnestic MCI rates did not show a significant age trend in this cohort.",
            "Частота деменции и болезни Альцгеймера повышалась с возрастом; частота амнестического MCI также росла, тогда как для неамнестического MCI в этой когорте значимого возрастного тренда не выявили.",
            "age patterns in incident cognitive outcomes", [(4, "As age increases"), (5, "aMCI increased with age"), (1, "naMCI incidence did not increase with age")],
            {"cohort": "Einstein Aging Study", "modifier": "age", "outcomes": "dementia, Alzheimer dementia, amnestic MCI, nonamnestic MCI"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "incidence increases with age", "roles": {"outcome": "dementia and Alzheimer dementia"}},
                {"predicate": "incidence increases with age", "roles": {"outcome": "amnestic MCI"}},
                # Предикат положительный; отрицание отсутствия статистической значимости хранится отдельно.
                {"predicate": "statistically significant age trend", "roles": {"outcome": "nonamnestic MCI"}, "negated": True},
            ], conditions=[*common_conditions, "A non-significant trend is not evidence that age has no effect."])
        add("adjusted-demographic-associations",
            "In adjusted Cox models, Black race was associated with higher nonamnestic MCI hazard (HR 2.04, 95% CI 1.39–3.01), while each additional year of education was associated with a lower hazard (HR 0.95, 0.90–0.997).",
            "В скорректированных моделях Кокса чернокожее происхождение было связано с более высоким риском неамнестического MCI (HR 2,04; 95% ДИ 1,39–3,01), а каждый дополнительный год образования — с более низким риском (HR 0,95; 0,90–0,997).",
            "adjusted demographic associations with nonamnestic MCI", [(7, "2.04"), (7, "0.95")],
            {"cohort": "Einstein Aging Study", "outcome": "incident nonamnestic MCI", "model": "Cox proportional hazards"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "adjusted hazard ratio", "roles": {"factor": "Black race vs White reference"}, "attrs": {"HR": {"value": 2.04, "unit": "95% CI 1.39–3.01"}, "p": {"value": 0.0003, "unit": "P"}}},
                {"predicate": "adjusted hazard ratio", "roles": {"factor": "each additional year of education"}, "attrs": {"HR": {"value": 0.95, "unit": "95% CI 0.90–0.997"}, "p": {"value": 0.04, "unit": "P"}}},
            ], conditions=[*common_conditions, "The table models included sex, education, race, and chronological age as the time scale."])
        add("demographic-null-results",
            "The adjusted models did not identify statistically significant associations of sex, education, or race with dementia or amnestic MCI; these non-significant estimates do not establish absence of effects.",
            "В скорректированных моделях не выявили статистически значимых связей пола, образования или происхождения с деменцией или амнестическим MCI; отсутствие значимости не доказывает отсутствие эффектов.",
            "non-significant demographic associations", [(7, "Dementia"), (7, "aMCI")],
            {"cohort": "Einstein Aging Study", "outcomes": "dementia and amnestic MCI", "factors": "sex, education, race"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "statistically significant adjusted association reported", "roles": {"outcome": "dementia", "factors": "sex, education, race"}, "negated": True},
                {"predicate": "statistically significant adjusted association reported", "roles": {"outcome": "amnestic MCI", "factors": "sex, education, race"}, "negated": True},
            ], conditions=["This records the table's non-significant tests; it does not assert a null effect."])
        add("race-prevalence-contrast",
            "Overall prevalent MCI was reported in 21.5% of the cohort; prevalence was 27.3% in Black participants and 19.1% in White participants, with the difference attributed to higher nonamnestic MCI prevalence among Black participants.",
            "Общая исходная распространённость MCI составила 21,5%; распространённость равнялась 27,3% у чернокожих и 19,1% у белых участников. Разницу авторы связывали с более высокой распространённостью неамнестического MCI у чернокожих участников.",
            "race-stratified prevalent MCI comparison", [(7, "21.5% at baseline"), (7, "19.1% vs. 27.3%")],
            {"cohort": "Einstein Aging Study", "timepoint": "baseline", "outcome": "prevalent MCI"},
            knowledge_type="comparison", logic="contrast", claims=[
                {"predicate": "prevalence", "roles": {"race": "Black participants"}, "attrs": {"rate": {"value": 27.3, "unit": "percent"}}},
                {"predicate": "prevalence", "roles": {"race": "White participants"}, "attrs": {"rate": {"value": 19.1, "unit": "percent"}}},
                {"predicate": "difference attributed to higher nonamnestic MCI prevalence", "roles": {"group": "Black participants"}},
            ])
        add("incidence-limitations",
            "The authors cautioned that dementia prevalence may be underestimated because institutionalized people and people with severe dementia were not represented; incidence may also be underestimated because loss to follow-up was associated with lower education and poorer global cognitive performance.",
            "Авторы предупредили, что распространённость деменции могла быть недооценена, поскольку институционализированные люди и люди с тяжёлой деменцией не были представлены; частота новых случаев также могла быть занижена, потому что выбывшие участники имели меньше образования и худшие показатели общей когнитивной функции.",
            "cohort selection and censoring limitations", [(8, "institutionalized were not included"), (8, "lower education"), (8, "incidence rates we reported may be underestimates")],
            {"study": "Einstein Aging Study", "estimates": "dementia prevalence and incident cognitive outcomes"},
            knowledge_type="limitation", modality="possible underestimation")

        add("calculate-person-time",
            "Calculate each participant's person-time from the baseline clinic visit until the final follow-up examination, an incident event, or death, whichever occurs first; allocate cases and person-time to the appropriate age range for age-specific rates.",
            "Рассчитать человеко-время каждого участника от исходного визита до итогового обследования, нового события или смерти — что наступит раньше; для возрастных частот отнести случаи и человеко-время к соответствующему возрастному интервалу.",
            "calculate person-time", [(3, "Person-years of follow-up were calculated as the time between the baseline clinic visit"),
                (3, "both cases and person-time were allocated to the appropriate age range")],
            {"risk_set": "@follow-up-risk-set", "time_origin": "baseline clinic visit",
             "censoring_events": "final examination, incident event, or death",
             "output_measure": "person-years"}, kind="action", knowledge_type="operation", logic="conjunction")
        add("calculate-incidence-rates",
            "Calculate incidence rates as incident cases per 100 person-years among participants free of the outcome at baseline; estimate confidence intervals with overdispersed Poisson regression.",
            "Рассчитать частоты новых случаев на 100 человеко-лет среди участников без соответствующего исхода на исходном этапе; оценить доверительные интервалы регрессией Пуассона со сверхдисперсией.",
            "estimate incidence rate", [(3, "Incidence rates were calculated as estimates of cases/100 person-years"),
                (3, "Confidence intervals (CI) were calculated using overdispersed Poisson regression models")],
            {"risk_set": "@follow-up-risk-set", "event_counts": "@incident-event-counts",
             "person_time": "@calculate-person-time", "method": "cases per 100 person-years with overdispersed Poisson confidence intervals"},
            kind="action", knowledge_type="operation", logic="conjunction",
            conditions=[*common_conditions, "The article's incidence rates are not baseline prevalence proportions."])
        add("fit-adjusted-cox-models",
            "Fit Cox proportional-hazards models with chronological age as the time scale to estimate associations of incident dementia, Alzheimer dementia, and MCI with education, sex, and race; test the proportional-hazards assumption using weighted residuals.",
            "Построить модели пропорциональных рисков Кокса со временем хронологического возраста для оценки связей деменции, болезни Альцгеймера и MCI с образованием, полом и происхождением; проверить предположение пропорциональности взвешенными остатками.",
            "fit Cox proportional-hazards model", [(3, "Cox proportional hazards models with chronological age as the time scale"),
                (3, "The proportional hazards assumption was tested for these models")],
            {"risk_set": "@follow-up-risk-set", "outcome_definition": "@mci-definition",
             "analysis_model": "Cox proportional hazards", "time_scale": "chronological age",
             "candidate_factors": "education, sex, and race"}, kind="action", knowledge_type="operation", logic="conjunction",
            conditions=[*common_conditions, "Adjusted associations do not establish causation."])

        transition(["study-design"], "follow-up-risk-set", "method", "The study's eligibility and follow-up rules define the population used for incidence analyses.", [(2, "eligibility"), (4, "incidence rates were estimated")])
        transition(["follow-up-risk-set"], "calculate-person-time", "method", "The article defines person-time from baseline to the earliest follow-up endpoint or death.", [(3, "Person-years of follow-up were calculated as the time between the baseline clinic visit"), (3, "incident event, or death")])
        transition(["follow-up-risk-set", "incident-event-counts", "calculate-person-time"], "calculate-incidence-rates", "method", "The risk set, event counts, and calculated person-time are the inputs to the incidence-rate procedure.", [(3, "Incidence rates were calculated as estimates of cases/100 person-years"), (3, "person-years of follow-up")])
        transition(["calculate-incidence-rates", "mci-definition"], "mci-subtype-incidence-rates", "result", "The rate procedure reports MCI subtype incidences under the study's operational definitions.", [(3, "classified as having aMCI"), (4, "3.79")])
        transition(["calculate-incidence-rates"], "dementia-incidence-rates", "result", "The same incidence procedure reports dementia outcomes under the follow-up risk set.", [(3, "Incidence rates were calculated as estimates of cases/100 person-years"), (4, "2.89")])
        transition(["mci-subtype-incidence-rates"], "age-patterns-cognitive-outcomes", "result", "The article compares age-stratified subtype rates and reports different age patterns for aMCI and naMCI.", [(5, "Rates increased with age"), (7, "naMCI incidence rates")])
        transition(["follow-up-risk-set", "mci-definition"], "fit-adjusted-cox-models", "method", "The risk set and operational endpoint definitions are analyzed by the source-described Cox procedure.", [(3, "Cox proportional hazards"), (3, "chronological age as the time scale")])
        transition(["fit-adjusted-cox-models"], "adjusted-demographic-associations", "result", "The adjusted Cox procedure yields the reported demographic hazard associations.", [(3, "estimate the association"), (7, "2.04")])
        transition(["baseline-prevalence"], "race-prevalence-contrast", "result", "The discussion compares baseline MCI prevalence by race and attributes the difference to naMCI prevalence.", [(7, "21.5% at baseline"), (7, "27.3%")])
        transition(["follow-up-risk-set"], "incidence-limitations", "condition", "The authors relate loss to follow-up and the composition of the community sample to possible underestimation.", [(8, "lower education"), (8, "underestimates")])
    else:
        raise ValueError(f"Unsupported article id: {article_id}")

    authored = {
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "concept_aliases": {
            "mild cognitive impairment": ["MCI"],
            "amnestic mild cognitive impairment": ["aMCI"],
            "nonamnestic mild cognitive impairment": ["naMCI"],
            "Alzheimer dementia": ["Alzheimer disease", "AD"],
        },
        "source_limitations": [
            "Карта создана вручную Codex по пользовательскому полному PDF; внешние и локальные LLM, переводчик и эмбеддинги не вызывались.",
            "Ранее просмотренные Roberts 2012 и Katz 2012 используются только как обучающие источники, не как слепые контрольные статьи.",
            "Сохранён полный текст PDF, но формализованы только выбранные положения; полное смысловое покрытие и исчерпывающая формализация таблиц не заявляются.",
            "Результаты когортных наблюдений не устанавливают причинность; незначимый результат не трактуется как доказательство отсутствия эффекта.",
            "Дополнительные материалы по ссылкам в статьях не были включены в PDF и не формализованы.",
            "Научная экспертная проверка отсутствует.",
        ],
        "knowledge": records,
        "transitions": transitions,
    }
    validate_authored_polarity(authored)

    knowledge_units = {unit_id for item in records for unit_id in item["units"]}
    transition_only_units = {unit_id for edge in transitions for unit_id in edge["units"]} - knowledge_units
    excluded = {}
    for item in source["units"]:
        if item["id"] in knowledge_units:
            continue
        if item["id"] in transition_only_units:
            excluded[item["id"]] = "Фрагмент использован только для обоснования перехода и не формализован как самостоятельное каноническое знание."
        else:
            excluded[item["id"]] = "Фрагмент просмотрен, но не включён в выборочную формализацию; полное смысловое покрытие не заявляется."
    authored["excluded_units"] = excluded
    return authored


def write_run(article_id: str, metadata: dict) -> Path:
    source_folder = SOURCE_ROOT / article_id
    pdf_path = source_folder / "article.pdf"
    layout_path = source_folder / "article.layout.txt"
    intake = json.loads((source_folder / "intake.json").read_text(encoding="utf-8"))
    require(sha256(pdf_path.read_bytes()).hexdigest() == metadata["pdf_sha256"], f"PDF hash mismatch: {article_id}")
    require(sha256(layout_path.read_bytes()).hexdigest() == metadata["layout_sha256"], f"PDF layout hash mismatch: {article_id}")
    text, page_ranges, pages = extract_pdf(pdf_path)
    require(len(pages) == metadata["pages"], f"PDF page count mismatch: {article_id}")
    source = prepare_source(article_id, text)
    require(source["references_excluded"], f"References heading was not detected: {article_id}")
    require(source["content_end"] < len(text), f"References boundary missing: {article_id}")
    authored = build_authored(article_id, source, page_ranges)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    dependency_prompt = DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")
    artifacts = prepare_manual_map(article_id, text, source["sha256"], authored, prompt, dependency_prompt)
    base_run_id = artifacts["map.json"]["run_id"]
    run_id = str(uuid5(NAMESPACE_URL, f"codex-research-map-v6:{article_id}:{base_run_id}"))
    artifacts["map.json"]["run_id"] = run_id
    artifacts["map.json"]["translations"]["ru"]["run_id"] = run_id
    graph = artifacts["map.json"]["graph"]
    artifacts["map.json"]["builder_version"] = "codex-complete-research-map-6"
    evidence_audit = audit_evidence_origin(graph)
    artifacts["empirical-evidence-eligibility.json"] = evidence_audit
    artifacts["validation.json"]["direct_evidence_eligible_blocks"] = evidence_audit["eligible_blocks"]
    artifacts["source-review.json"] = {
        "article_id": article_id,
        "manual_semantic_revision": 6,
        "title": metadata["title"],
        "doi": metadata["doi"],
        "source_pdf_relative_path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "pdf_sha256": metadata["pdf_sha256"],
        "layout_sha256": metadata["layout_sha256"],
        "normalized_source_sha256": source["sha256"],
        "text_extractor": "pypdfium2 via Poetry",
        "normalization": "PDF page text extracted in reading order; line endings normalized to LF; non-empty extracted lines separated by blank lines for precise source spans; pages separated by two LF characters",
        "page_count": metadata["pages"],
        "visually_reviewed_pdf_pages": metadata["visually_reviewed_pages"],
        "table_pages_reviewed": metadata["table_pages"],
        "references_excluded_from_extraction": True,
        "complete_semantic_coverage": False,
        "all_table_cells_formalized": False,
        "prior_source_exposure": True,
        "training_only": True,
        "expert_validated": False,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "translation_llm_calls": 0,
        "embedding_calls": 0,
        "token_usage": None,
        "source_unit_count": len(source["units"]),
        "source_pages": [{"page": index + 1, "start": span[0], "end": span[1], "sha256": digest(pages[index])}
                          for index, span in enumerate(page_ranges)],
        "original_intake": intake,
    }
    report = [
        f"# {metadata['title_ru']}", "",
        f"DOI: {metadata['doi']}. PDF SHA-256: `{metadata['pdf_sha256']}`. Нормализованный полный текст: `{source['sha256']}`.",
        f"Подготовлено {len(graph['knowledge'])} канонических знаний, {sum(len(item['semantic_frame']['statements']) for item in graph['knowledge'])} утверждений и {len(graph['transitions'])} обоснованных переходов.",
        f"Видимая карта имеет {graph['analysis']['depth']} слоя, {graph['analysis']['isolated_count']} изолированных знаний и {len(source['units'])} исходных фрагментов. Контракт, происхождение и DAG прошли общий валидатор.", "",
        "## Состав карты", "",
        "Включены дизайн и критерии исследования, определение и подтипы MCI, исходные знаменатели и наблюдение, частоты, сравнения по возрасту/полу/образованию/происхождению и авторские ограничения. References сохранены в полном исходном тексте и исключены из извлечения.",
        "Значения таблиц сверены с визуальным PDF. Список литературы сохранён в полном исходном тексте и исключён из извлечения. Карта частичная: причины пропуска фрагментов записаны, но все ячейки и все положения статьи не формализованы.", "",
        "## Статус для прогноза", "",
        "Источник был ранее прочитан при тематическом скрининге. Он допускается только в обучающую часть и не может считаться слепым holdout или независимой проверкой прогноза. Наблюдательные оценки не превращены в причинные правила.",
        "Карту подготовил Codex. Внешние и локальные LLM, переводчик и эмбеддинги не вызывались. Точные версии промптов и сформированные входы сохранены для совместимости контракта; это не означает вызова моделей. Научная экспертная проверка требуется.", "",
    ]
    artifacts["report.ru.md"] = "\n".join(report)
    artifacts["source.en.md"] = text
    artifacts["source.layout.txt"] = layout_path.read_text(encoding="utf-8")
    artifacts["source.pdf-provenance.json"] = {
        "path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "pdf_sha256": metadata["pdf_sha256"],
        "layout_path": str(layout_path.relative_to(ROOT)).replace("\\", "/"),
        "layout_sha256": metadata["layout_sha256"],
        "normalized_text_sha256": source["sha256"],
        "extraction_tool": "pypdfium2 through Poetry",
        "model_calls": 0,
    }
    output = OUTPUT_ROOT / artifacts["map.json"]["run_id"]
    for name, value in artifacts.items():
        payload = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        write_immutable(output / name, payload)
    print(json.dumps({
        "article_id": article_id, "run_id": artifacts["map.json"]["run_id"],
        "output": str(output), "knowledge": len(graph["knowledge"]),
        "statements": sum(len(item["semantic_frame"]["statements"]) for item in graph["knowledge"]),
        "transitions": len(graph["transitions"]), "depth": graph["analysis"]["depth"],
        "source_units": len(source["units"]), "references_excluded": source["references_excluded"],
        "model_calls": 0, "complete_semantic_coverage": False,
    }, ensure_ascii=False))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--article", choices=[*ARTICLES, "all"], default="all")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    disable_network()
    require(args.root.resolve() == ROOT.resolve(), "Unexpected workspace root")
    selected = ARTICLES if args.article == "all" else {args.article: ARTICLES[args.article]}
    for article_id, metadata in selected.items():
        write_run(article_id, metadata)


if __name__ == "__main__":
    main()
