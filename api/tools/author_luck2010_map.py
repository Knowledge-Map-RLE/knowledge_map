"""Создаёт отдельный ручной черновик карты статьи Luck et al. 2010."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
import sys

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import PROMPT_PATH, DEPENDENCY_PROMPT_PATH
from domain.article_maps import require
from domain.empirical_evidence_eligibility import audit as audit_evidence_origin
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


ARTICLE_ID = "luck2010"
PDF_SHA256 = "96fc3b83e4d70c6c9da35617b80013aa2a3b1b21ce640d12000b8709699e1fbf"
SOURCE_SHA256 = "d5e15ac426b3c43e116dfa0ef038992c8aa104ffcb588b36419fa8685ccb8cd3"
SOURCE_FOLDER = Path("eval/whole_map_forecast/whicap-leila-codex-maps-v1/luck2010")
OUTPUT_FOLDER = Path("eval/whole_map_forecast/luck2010-complete-map-v1/runs")


def build_authored(source: dict) -> dict:
    """Формализует только проверенные утверждения, методы и результаты статьи."""
    units = {unit["id"]: unit for unit in source["units"]}
    records: list[dict] = []

    def add(key: str, en: str, ru: str, predicate: str, unit_ids: list[str], roles: dict,
            *, attrs: dict | None = None, kind: str = "state", knowledge_type: str = "result",
            claims: list[dict] | None = None, logic: str = "single", conditions: list[str] | None = None,
            time: str | None = "LEILA 75+ baseline and follow-up assessments, 1997–2005",
            modality: str | None = None, quantifier: str | None = None, status: str | None = None,
            origin: str = "direct observation in this primary study") -> None:
        for uid in unit_ids:
            require(uid in units, f"Unknown source unit: {uid}")
        normalized_roles = {"cohort": "LEILA 75+", **roles}
        if knowledge_type in {"observation", "result", "comparison"}:
            normalized_roles.setdefault("evidence_origin", origin)
        item = {
            "key": key, "en": en, "ru": ru, "predicate": predicate, "units": unit_ids,
            "roles": normalized_roles, "attrs": attrs or {},
            "kind": kind, "type": knowledge_type, "logic": logic, "time": time,
            "conditions": conditions or ["Population-based prospective observational cohort; this is not a causal estimate."],
            "modality": modality, "quantifier": quantifier,
        }
        if claims:
            item["claims"] = claims
        if kind == "action":
            item["status"] = status or "performed"
        records.append(item)

    add("study-design",
        "LEILA 75+ was a population-based prospective cohort study of mild cognitive impairment and dementia in Leipzig, Germany.",
        "LEILA 75+ — популяционное проспективное когортное исследование лёгких когнитивных нарушений и деменции в Лейпциге, Германия.",
        "study design", ["U4", "U8"], {"study": "LEILA 75+", "setting": "Leipzig, Germany"},
        knowledge_type="method", attrs={"design": {"value": "prospective cohort", "unit": None},
        "population_basis": {"value": "population-based", "unit": None}})

    add("baseline-population",
        "The baseline sample included 1,692 people aged 75 years or older; 1,265 participated.",
        "Исходная выборка включала 1 692 человека в возрасте 75 лет и старше; в исследовании участвовали 1 265.",
        "baseline recruitment", ["U4", "U11"], {"population": "people aged 75 years or older"},
        knowledge_type="observation", attrs={"baseline_sample": {"value": 1692, "unit": "participants"},
        "participants": {"value": 1265, "unit": "participants"}, "minimum_age": {"value": 75, "unit": "years"}},
        time="Baseline recruitment before follow-up", conditions=["Counts refer to the LEILA 75+ recruitment flow."])

    add("followup-schedule",
        "The study covered eight years, with baseline assessments from January 1997 to June 1998 and five follow-up assessments from July 1998 to April 2005, spaced about 1.4 years apart on average.",
        "Исследование длилось восемь лет: исходные обследования проводили с января 1997 по июнь 1998 года, затем с июля 1998 по апрель 2005 года провели пять повторных обследований со средним интервалом около 1,4 года.",
        "follow-up schedule", ["U8"], {"study": "LEILA 75+", "assessment": "five follow-up assessments"},
        knowledge_type="method", attrs={"duration": {"value": 8, "unit": "years"},
        "baseline_period": {"value": "1997-01 to 1998-06", "unit": None},
        "followup_period": {"value": "1998-07 to 2005-04", "unit": None},
        "mean_assessment_interval": {"value": 1.4, "unit": "years"}},
        time="1997–2005")

    add("risk-set-flow",
        "Of 1,265 participants, 732 were at risk of incident MCI at follow-up after excluding baseline dementia, baseline MCI, and invalid or incomplete cognitive assessments.",
        "Из 1 265 участников 732 вошли в группу риска возникновения MCI при последующем наблюдении после исключения деменции, MCI и недействительных или неполных когнитивных обследований на исходном этапе.",
        "risk-set selection", ["U12"], {"participants": "LEILA 75+ participants", "eligible_group": "population at risk of incident MCI"},
        knowledge_type="result", attrs={"participants": {"value": 1265, "unit": "participants"},
        "risk_set": {"value": 732, "unit": "participants"}, "excluded_dementia": {"value": 220, "unit": "participants"},
        "excluded_baseline_mci": {"value": 162, "unit": "participants"},
        "excluded_invalid_or_incomplete": {"value": 151, "unit": "participants"}},
        time="Baseline to follow-up", conditions=["Counts are the Figure 1 sample flow; categories follow the article's labels."])

    add("incidence-analysis-selection",
        "The incidence calculation included 519 of 732 participants at risk; 213 were excluded because diagnostic criteria could not be applied at one or more follow-up assessments, and excluded participants were older.",
        "В расчёт частоты включили 519 из 732 участников группы риска; 213 исключили, поскольку критерии нельзя было применить хотя бы на одном повторном обследовании. Исключённые участники были старше.",
        "incidence analysis selection", ["U13", "U23", "U24"],
        {"eligible_group": "population at risk of incident MCI", "included_group": "incidence analysis sample", "selection_reason": "incomplete follow-up assessment"},
        knowledge_type="result", attrs={"at_risk": {"value": 732, "unit": "participants"},
        "included": {"value": 519, "unit": "participants"}, "excluded": {"value": 213, "unit": "participants"},
        "excluded_age_mean": {"value": 82.0, "unit": "years"}, "included_age_mean": {"value": 81.0, "unit": "years"}},
        time="Follow-up incidence analysis", conditions=["Excluded participants lacked at least one follow-up at which MCI criteria could be applied."])

    add("mci-core-definition",
        "Study-defined MCI required absence of dementia, preserved or minimally impaired daily function, reported cognitive decline, and objective cognitive impairment.",
        "Согласно критериям исследования, MCI требовал отсутствия деменции, сохранной или минимально нарушенной повседневной функции, сообщённого когнитивного снижения и объективного когнитивного нарушения.",
        "MCI diagnostic definition", ["U19"], {"classification": "MCI under LEILA 75+ criteria"},
        knowledge_type="definition", logic="conjunction", quantifier="all",
        claims=[
            {"predicate": "requires absence of dementia", "roles": {"criterion": "no DSM-IV dementia diagnosis"}},
            {"predicate": "requires preserved daily function", "roles": {"criterion": "preserved or minimally impaired ADL/IADL function"}},
            {"predicate": "requires reported cognitive decline", "roles": {"criterion": "self- or informant-reported cognitive decline"}},
            {"predicate": "requires objective cognitive impairment", "roles": {"criterion": "objective impairment in cognitive testing"}},
        ], time="Classification at each baseline or follow-up assessment",
        conditions=["Consensus diagnosis used SIDAM and proxy Clinical Dementia Rating when direct testing was unavailable."])

    add("sidam-instrument",
        "SIDAM combined a 55-item cognitive battery, including the 30-item MMSE, with clinical judgement and third-party information.",
        "SIDAM объединял когнитивную батарею из 55 пунктов, включая 30 пунктов MMSE, с клинической оценкой и сведениями от третьих лиц.",
        "cognitive assessment instrument", ["U19"], {"instrument": "SIDAM", "assessment_target": "cognitive impairment"},
        knowledge_type="method", attrs={"battery_items": {"value": 55, "unit": "items"},
        "mmse_items": {"value": 30, "unit": "items"}})

    add("objective-threshold",
        "Objective impairment in a cognitive domain was defined as performance more than one standard deviation below age- and education-specific norms.",
        "Объективное нарушение когнитивной области определяли как результат более чем на одно стандартное отклонение ниже норм, учитывающих возраст и образование.",
        "objective cognitive impairment threshold", ["U19"], {"test_performance": "cognitive-domain performance", "reference": "age- and education-specific norms"},
        knowledge_type="definition", attrs={"cutoff": {"value": 1, "unit": "standard deviation below norm"}},
        conditions=["The article specifies a strict threshold of more than one standard deviation below the norm."])

    subtype_records = [
        ("subtype-single-amnestic", "Single-domain amnestic MCI required an objective memory deficit without impairment in another cognitive domain.", "Однодоменный амнестический MCI требовал объективного нарушения памяти без нарушений других когнитивных областей.", "memory impairment only"),
        ("subtype-single-nonmemory", "Single-domain nonmemory MCI required impairment in one cognitive domain other than memory.", "Однодоменный неамнестический MCI требовал нарушения одной когнитивной области, кроме памяти.", "one nonmemory domain impaired"),
        ("subtype-multidomain-nonamnestic", "Multidomain nonamnestic MCI required impairment in at least two nonmemory cognitive domains.", "Многодоменный неамнестический MCI требовал нарушений как минимум двух когнитивных областей, кроме памяти.", "at least two nonmemory domains impaired"),
        ("subtype-multidomain-amnestic", "Multidomain amnestic MCI required memory impairment and impairment in at least one additional cognitive domain.", "Многодоменный амнестический MCI требовал нарушения памяти и как минимум ещё одной когнитивной области.", "memory and at least one other domain impaired"),
    ]
    for key, en, ru, criterion in subtype_records:
        add(key, en, ru, "MCI subtype definition", ["U19", "U28"],
            {"subtype": key.replace("-", " "), "shared_criteria": "@mci-core-definition"},
            knowledge_type="definition", attrs={"subtype_criterion": {"value": criterion, "unit": None}},
            conditions=["Subtype definitions are mutually distinguishable only by the listed cognitive-domain pattern."])

    add("smi-measurement",
        "Subjective memory impairment was measured before cognitive testing by asking whether the participant had problems with memory.",
        "Субъективное нарушение памяти измеряли до когнитивного тестирования вопросом, есть ли у участника проблемы с памятью.",
        "subjective memory measurement", ["U19"], {"measure": "subjective memory impairment", "respondent": "participant"},
        knowledge_type="method", attrs={"question": {"value": "Do you have problems with your memory?", "unit": None}})

    add("iadl-measurement",
        "Instrumental activities of daily living were assessed with 11 items; difficulty with one item classified a participant as impaired.",
        "Инструментальную повседневную активность оценивали по 11 пунктам; затруднение хотя бы в одном пункте означало нарушение.",
        "IADL measurement", ["U19"], {"measure": "instrumental activities of daily living", "classification": "IADL impairment"},
        knowledge_type="method", attrs={"items": {"value": 11, "unit": "items"}, "impairment_cutoff": {"value": 1, "unit": "item with difficulty"}})

    add("incidence-person-time-method",
        "Incidence rates were calculated as new MCI cases divided by person-years at risk.",
        "Частоту рассчитывали как число новых случаев MCI, делённое на человеко-годы риска.",
        "incidence calculation method", ["U4", "U19"], {"numerator": "new MCI cases", "denominator": "person-years at risk"},
        kind="action", knowledge_type="operation", status="performed", time="Follow-up period",
        conditions=["The article uses person-years at risk; reported rates are not percentages."])

    add("onset-midpoint-method",
        "Because MCI was diagnosed only at scheduled assessments, the study assigned onset to the midpoint between the diagnosis visit and the preceding visit.",
        "Поскольку MCI устанавливали только во время плановых обследований, началом считали середину интервала между визитом с диагнозом и предыдущим визитом.",
        "incident onset-time assignment", ["U19", "U42"], {"incident_case": "MCI diagnosed at follow-up", "time_assignment": "midpoint between visits"},
        knowledge_type="method", attrs={"assignment": {"value": "midpoint", "unit": "between adjacent assessment visits"}},
        time="Between the last visit without and first visit with diagnosed MCI")

    add("cox-model-method",
        "Cox proportional hazards models examined associations with incident MCI; age and MMSE were continuous predictors, while smoking, alcohol use, and hypertension were categorical.",
        "Модели пропорциональных рисков Кокса оценивали связи с возникновением MCI; возраст и MMSE задавали непрерывными предикторами, курение, алкоголь и гипертонию — категориальными.",
        "Cox risk-factor analysis", ["U19", "U32", "U34"], {"analysis": "Cox proportional hazards model", "outcome": "incident MCI"},
        kind="action", knowledge_type="method", status="performed", time="Follow-up from baseline",
        attrs={"complete_case_n": {"value": 463, "unit": "participants"}, "missing_data_excluded": {"value": 56, "unit": "participants"}},
        conditions=["Risk-factor models used complete cases; this differs from the 519-person incidence denominator."])

    add("overall-mci-incidence",
        "During eight years, 137 of 519 participants developed MCI (26.4%); the overall incidence rate was 76.5 per 1,000 person-years (95% CI 64.7–90.4).",
        "За восемь лет MCI развился у 137 из 519 участников (26,4%); общая частота составила 76,5 случая на 1 000 человеко-лет (95% ДИ 64,7–90,4).",
        "incident MCI rate", ["U4", "U24", "U27"], {"outcome": "incident total MCI", "population": "incidence analysis sample"},
        attrs={"cases": {"value": 137, "unit": "participants"}, "denominator": {"value": 519, "unit": "participants"},
        "cumulative_proportion": {"value": 26.4, "unit": "percent"}, "person_years": {"value": 1791.08, "unit": "person-years"},
        "incidence_rate": {"value": 76.5, "unit": "per 1,000 person-years"}, "ci_low": {"value": 64.7, "unit": "per 1,000 person-years"},
        "ci_high": {"value": 90.4, "unit": "per 1,000 person-years"}, "confidence_level": {"value": 95, "unit": "percent"}},
        time="Eight-year follow-up", conditions=["Person-time incidence estimate; observational result under the LEILA 75+ case definition."])

    add("mean-time-to-mci",
        "Among incident MCI cases, mean time from baseline to diagnosis was 5.8 years (95% CI 5.6–6.1).",
        "Среди новых случаев MCI среднее время от исходного обследования до диагноза составило 5,8 года (95% ДИ 5,6–6,1).",
        "time to incident MCI diagnosis", ["U24"], {"outcome": "incident MCI diagnosis", "measure": "mean time from baseline"},
        attrs={"mean": {"value": 5.8, "unit": "years"}, "ci_low": {"value": 5.6, "unit": "years"},
        "ci_high": {"value": 6.1, "unit": "years"}, "confidence_level": {"value": 95, "unit": "percent"}},
        time="From baseline to diagnosis")

    add("total-mci-age-rates",
        "Total-MCI incidence rates increased across age strata: 50.3 per 1,000 person-years at ages 75–79, 84.8 at 80–84, and 157.6 at age 85 or older.",
        "Частота MCI в целом возрастала между возрастными группами: 50,3 на 1 000 человеко-лет в 75–79 лет, 84,8 в 80–84 года и 157,6 в возрасте 85 лет и старше.",
        "age-stratified incidence rate", ["U25", "U26", "U27"], {"outcome": "incident total MCI", "stratifier": "age group"},
        knowledge_type="comparison", logic="contrast", attrs={"measure": {"value": "cases per 1,000 person-years", "unit": None}},
        claims=[
            {"predicate": "age-specific incidence", "roles": {"age_group": "75–79 years"}, "attrs": {"cases": {"value": 52, "unit": "cases"}, "person_years": {"value": 1033.99, "unit": "person-years"}, "rate": {"value": 50.3, "unit": "per 1,000 person-years"}, "ci_low": {"value": 38.3, "unit": "per 1,000 person-years"}, "ci_high": {"value": 66.0, "unit": "per 1,000 person-years"}}},
            {"predicate": "age-specific incidence", "roles": {"age_group": "80–84 years"}, "attrs": {"cases": {"value": 40, "unit": "cases"}, "person_years": {"value": 471.65, "unit": "person-years"}, "rate": {"value": 84.8, "unit": "per 1,000 person-years"}, "ci_low": {"value": 62.2, "unit": "per 1,000 person-years"}, "ci_high": {"value": 115.6, "unit": "per 1,000 person-years"}}},
            {"predicate": "age-specific incidence", "roles": {"age_group": "85 years or older"}, "attrs": {"cases": {"value": 45, "unit": "cases"}, "person_years": {"value": 285.45, "unit": "person-years"}, "rate": {"value": 157.6, "unit": "per 1,000 person-years"}, "ci_low": {"value": 117.7, "unit": "per 1,000 person-years"}, "ci_high": {"value": 211.1, "unit": "per 1,000 person-years"}}},
        ], time="Eight-year follow-up", conditions=["Age strata are those reported in Table 2; rates are not adjusted causal effects."])

    add("total-mci-sex-rates",
        "Across participants aged 75 or older, total-MCI incidence was 80.8 per 1,000 person-years in women and 65.8 in men; the adjusted Cox model did not detect a significant sex association.",
        "Среди участников 75 лет и старше частота MCI в целом составляла 80,8 на 1 000 человеко-лет у женщин и 65,8 у мужчин.",
        "sex-stratified total-MCI incidence", ["U27", "U31", "U33"], {"outcome": "incident total MCI", "stratifier": "sex"},
        knowledge_type="comparison", logic="contrast", claims=[
            {"predicate": "incidence rate in women", "roles": {"sex_group": "women aged 75 years or older"}, "attrs": {"cases": {"value": 103, "unit": "cases"}, "person_years": {"value": 1274.63, "unit": "person-years"}, "rate": {"value": 80.8, "unit": "per 1,000 person-years"}, "ci_low": {"value": 66.6, "unit": "per 1,000 person-years"}, "ci_high": {"value": 98.0, "unit": "per 1,000 person-years"}}},
            {"predicate": "incidence rate in men", "roles": {"sex_group": "men aged 75 years or older"}, "attrs": {"cases": {"value": 34, "unit": "cases"}, "person_years": {"value": 516.45, "unit": "person-years"}, "rate": {"value": 65.8, "unit": "per 1,000 person-years"}, "ci_low": {"value": 47.0, "unit": "per 1,000 person-years"}, "ci_high": {"value": 92.1, "unit": "per 1,000 person-years"}}},
        ], conditions=["Table 2 rates are unadjusted; the separate adjusted Cox model reports no significant sex effect."])

    add("mci-subtype-incidence-rates",
        "The reported total incidence was 27.9 per 1,000 person-years for amnestic MCI (95% CI 21.2–36.8) and 48.6 for nonamnestic MCI (95% CI 39.4–59.9).",
        "Общая частота амнестического MCI составила 27,9 на 1 000 человеко-лет (95% ДИ 21,2–36,8), неамнестического — 48,6 (95% ДИ 39,4–59,9).",
        "MCI subtype incidence rates", ["U25", "U27", "U28", "U31"], {"outcome": "incident MCI subtype", "comparison": "amnestic versus nonamnestic"},
        knowledge_type="comparison", logic="contrast", claims=[
            {"predicate": "incidence rate", "roles": {"subtype": "amnestic MCI"}, "attrs": {"cases": {"value": 50, "unit": "cases"}, "person_years": {"value": 1791.08, "unit": "person-years"}, "rate": {"value": 27.9, "unit": "per 1,000 person-years"}, "ci_low": {"value": 21.2, "unit": "per 1,000 person-years"}, "ci_high": {"value": 36.8, "unit": "per 1,000 person-years"}}},
            {"predicate": "incidence rate", "roles": {"subtype": "nonamnestic MCI"}, "attrs": {"cases": {"value": 87, "unit": "cases"}, "person_years": {"value": 1791.08, "unit": "person-years"}, "rate": {"value": 48.6, "unit": "per 1,000 person-years"}, "ci_low": {"value": 39.4, "unit": "per 1,000 person-years"}, "ci_high": {"value": 59.9, "unit": "per 1,000 person-years"}}},
        ], time="Eight-year follow-up", conditions=["Subtype groups are defined by the study's operational criteria; these are incidence rates, not risk ratios."])

    def model_result(key: str, factor: str, contrast: str, sentence_en: str, sentence_ru: str,
                     hr: float, low: float, high: float, p: str, units_list: list[str], *,
                     outcome: str = "incident total MCI", model: str = "complete-case total-MCI Cox model",
                     n: int = 463, se: str | None = None, z: str | None = None,
                     note: str | None = None) -> None:
        attrs = {"hazard_ratio": {"value": hr, "unit": "dimensionless"},
                 "ci_low": {"value": low, "unit": "dimensionless"},
                 "ci_high": {"value": high, "unit": "dimensionless"},
                 "confidence_level": {"value": 95, "unit": "percent"},
                 "p_value": {"value": p, "unit": None}, "model_n": {"value": n, "unit": "participants"}}
        if se is not None:
            attrs["standard_error"] = {"value": se, "unit": "dimensionless"}
        if z is not None:
            attrs["z_statistic"] = {"value": z, "unit": None}
        cond = [f"{model}; the outcome is {outcome}.", "Association estimate from an observational model; causation is not established."]
        if note:
            cond.append(note)
        add(key, sentence_en, sentence_ru, "reported Cox-model association", units_list,
            {"exposure": factor, "contrast": contrast, "outcome": outcome, "analysis_model": model,
             "evidence_origin": "direct observation in this primary study"}, attrs=attrs,
            knowledge_type="result", time="Baseline predictor to incident outcome during follow-up", conditions=cond)

    model_result("total-age-association", "age", "per additional year",
        "In the complete-case Cox model, each additional year of age was associated with higher hazard of incident total MCI (HR 1.06, 95% CI 1.02–1.14; P=.01).",
        "В модели Кокса для полных наблюдений каждый дополнительный год возраста был связан с более высокой интенсивностью возникновения MCI в целом (HR 1,06; 95% ДИ 1,02–1,14; P=.01).",
        1.06, 1.02, 1.14, ".01", ["U33", "U34"], se="0.02", z="2.63")

    model_result("total-smi-association", "subjective memory impairment", "present versus absent",
        "Baseline subjective memory impairment was associated with higher hazard of incident total MCI (HR 1.92, 95% CI 1.28–2.88; P<.001).",
        "Исходное субъективное нарушение памяти было связано с более высокой интенсивностью возникновения MCI в целом (HR 1,92; 95% ДИ 1,28–2,88; P<.001).",
        1.92, 1.28, 2.88, "<.001", ["U19", "U33", "U34"], se="0.40", z="3.16")

    model_result("total-iadl-association", "IADL impairment", "impaired versus not impaired",
        "Baseline IADL impairment was associated with higher hazard of incident total MCI (HR 1.85, 95% CI 1.21–2.85; P=.01).",
        "Исходное нарушение IADL было связано с более высокой интенсивностью возникновения MCI в целом (HR 1,85; 95% ДИ 1,21–2,85; P=.01).",
        1.85, 1.21, 2.85, ".01", ["U19", "U33", "U34"], se="0.41", z="2.81")

    model_result("total-mmse-association", "baseline MMSE score", "per one additional point",
        "Each additional baseline MMSE point was associated with a lower hazard of incident total MCI (HR 0.78, 95% CI 0.70–0.87; P<.001).",
        "Каждый дополнительный балл исходного MMSE был связан с меньшей интенсивностью возникновения MCI в целом (HR 0,78; 95% ДИ 0,70–0,87; P<.001).",
        0.78, 0.70, 0.87, "<.001", ["U19", "U33", "U34"], se="0.04", z="-4.42",
        note="The direction is per higher MMSE score; it must not be reversed when transferring the result.")

    add("total-model-no-detected-sex-effect",
        "The adjusted total-MCI Cox model did not detect a statistically significant association with sex (female versus male HR 1.30, 95% CI 0.72–2.32; P=.38).",
        "Скорректированная модель Кокса для MCI в целом не выявила статистически значимой связи с полом (женщины против мужчин: HR 1,30; 95% ДИ 0,72–2,32; P=.38).",
        "no statistically significant association detected", ["U33", "U34"],
        {"exposure": "sex", "contrast": "female versus male", "outcome": "incident total MCI", "analysis_model": "complete-case total-MCI Cox model", "evidence_origin": "direct observation in this primary study"},
        knowledge_type="comparison", attrs={"hazard_ratio": {"value": 1.30, "unit": "dimensionless"},
        "ci_low": {"value": 0.72, "unit": "dimensionless"}, "ci_high": {"value": 2.32, "unit": "dimensionless"},
        "p_value": {"value": ".38", "unit": None}, "model_n": {"value": 463, "unit": "participants"}},
        time="Baseline sex to incident total MCI", conditions=["A nonsignificant result does not establish absence of an effect.", "Adjusted observational Cox model."])

    add("total-model-other-nonsignificant-factors",
        "In the complete-case total-MCI Cox model, the reported associations for marital status, living situation, comorbidity, depressive symptoms, hypertension, smoking, alcohol consumption, and family history did not reach statistical significance.",
        "В модели Кокса для полных наблюдений связи MCI в целом с семейным положением, местом проживания, сопутствующими заболеваниями, депрессивными симптомами, гипертонией, курением, алкоголем и семейным анамнезом не достигли статистической значимости.",
        "no statistically significant associations detected", ["U33", "U34"],
        {"outcome": "incident total MCI", "analysis_model": "complete-case total-MCI Cox model", "evidence_origin": "direct observation in this primary study"},
        knowledge_type="comparison", logic="conjunction", claims=[
            {"predicate": "not statistically significant in adjusted model", "roles": {"factor": "marital status"}, "attrs": {"hazard_ratio": {"value": 0.81, "unit": "dimensionless"}, "ci_low": {"value": 0.48, "unit": "dimensionless"}, "ci_high": {"value": 1.37, "unit": "dimensionless"}, "p_value": {"value": ".44", "unit": None}}},
            {"predicate": "not statistically significant in adjusted model", "roles": {"factor": "living situation"}, "attrs": {"hazard_ratio": {"value": 0.65, "unit": "dimensionless"}, "ci_low": {"value": 0.32, "unit": "dimensionless"}, "ci_high": {"value": 1.32, "unit": "dimensionless"}, "p_value": {"value": ".23", "unit": None}}},
            {"predicate": "not statistically significant in adjusted model", "roles": {"factor": "diabetes mellitus"}, "attrs": {"hazard_ratio": {"value": 0.93, "unit": "dimensionless"}, "ci_low": {"value": 0.59, "unit": "dimensionless"}, "ci_high": {"value": 1.46, "unit": "dimensionless"}, "p_value": {"value": ".75", "unit": None}}},
            {"predicate": "not statistically significant in adjusted model", "roles": {"factor": "depressive symptoms"}, "attrs": {"hazard_ratio": {"value": 0.89, "unit": "dimensionless"}, "ci_low": {"value": 0.51, "unit": "dimensionless"}, "ci_high": {"value": 1.55, "unit": "dimensionless"}, "p_value": {"value": ".68", "unit": None}}},
            {"predicate": "not statistically significant in adjusted model", "roles": {"factor": "family history of dementia"}, "attrs": {"hazard_ratio": {"value": 1.39, "unit": "dimensionless"}, "ci_low": {"value": 0.90, "unit": "dimensionless"}, "ci_high": {"value": 2.15, "unit": "dimensionless"}, "p_value": {"value": ".14", "unit": None}}},
        ], time="Baseline covariates to incident total MCI", conditions=["Nonsignificance is not evidence of equivalence or proof of no effect.", "All estimates are from the same complete-case Cox model; they are not independent studies."])

    add("smi-time-to-diagnosis",
        "Baseline SMI was associated with shorter mean time to MCI diagnosis: 5.0 years (95% CI 4.5–5.4) with SMI versus 6.2 years (95% CI 5.9–6.5) without SMI; log-rank P<.001.",
        "Исходное SMI было связано с меньшим средним временем до диагноза MCI: 5,0 года (95% ДИ 4,5–5,4) при SMI против 6,2 года (95% ДИ 5,9–6,5) без SMI; log-rank P<.001.",
        "SMI-stratified time to MCI diagnosis", ["U37", "U38"], {"exposure": "baseline subjective memory impairment", "outcome": "time to MCI diagnosis"},
        knowledge_type="comparison", logic="contrast", claims=[
            {"predicate": "mean time to diagnosis", "roles": {"group": "baseline SMI present"}, "attrs": {"mean": {"value": 5.0, "unit": "years"}, "ci_low": {"value": 4.5, "unit": "years"}, "ci_high": {"value": 5.4, "unit": "years"}}},
            {"predicate": "mean time to diagnosis", "roles": {"group": "baseline SMI absent"}, "attrs": {"mean": {"value": 6.2, "unit": "years"}, "ci_low": {"value": 5.9, "unit": "years"}, "ci_high": {"value": 6.5, "unit": "years"}}},
            {"predicate": "log-rank comparison", "roles": {"test": "log-rank test"}, "attrs": {"chi_square": {"value": 11.72, "unit": None}, "p_value": {"value": "<.001", "unit": None}}},
        ], conditions=["Age-adjusted Kaplan–Meier comparison; a time-to-diagnosis association does not establish causation."])

    add("amnestic-subtype-model-results",
        "In the amnestic-MCI Cox model, baseline SMI (HR 2.66, 95% CI 1.35–5.26), IADL impairment (HR 2.17, 95% CI 1.02–4.62), and each additional MMSE point (HR 0.79, 95% CI 0.66–0.95) were reported as associated with incident amnestic MCI.",
        "В модели Кокса для амнестического MCI с его возникновением связывались исходное SMI (HR 2,66; 95% ДИ 1,35–5,26), нарушение IADL (HR 2,17; 95% ДИ 1,02–4,62) и каждый дополнительный балл MMSE (HR 0,79; 95% ДИ 0,66–0,95).",
        "amnestic MCI subtype model results", ["U37", "U38"], {"outcome": "incident amnestic MCI", "analysis_model": "amnestic-subtype Cox model"},
        knowledge_type="comparison", logic="conjunction", claims=[
            {"predicate": "higher hazard associated with baseline SMI", "roles": {"factor": "subjective memory impairment", "contrast": "present versus absent"}, "attrs": {"hazard_ratio": {"value": 2.66, "unit": "dimensionless"}, "ci_low": {"value": 1.35, "unit": "dimensionless"}, "ci_high": {"value": 5.26, "unit": "dimensionless"}, "confidence_level": {"value": 95, "unit": "percent"}}},
            {"predicate": "higher hazard associated with IADL impairment", "roles": {"factor": "IADL impairment", "contrast": "impaired versus not impaired"}, "attrs": {"hazard_ratio": {"value": 2.17, "unit": "dimensionless"}, "ci_low": {"value": 1.02, "unit": "dimensionless"}, "ci_high": {"value": 4.62, "unit": "dimensionless"}, "confidence_level": {"value": 95, "unit": "percent"}}},
            {"predicate": "lower hazard per additional MMSE point", "roles": {"factor": "baseline MMSE", "contrast": "per one additional point"}, "attrs": {"hazard_ratio": {"value": 0.79, "unit": "dimensionless"}, "ci_low": {"value": 0.66, "unit": "dimensionless"}, "ci_high": {"value": 0.95, "unit": "dimensionless"}, "confidence_level": {"value": 95, "unit": "percent"}}},
        ], conditions=["The article reports subtype-specific Cox estimates; do not merge with total-MCI estimates.", "Observational associations do not establish causal effects."])

    add("amnestic-subtype-age-not-significant",
        "The article reports that older age was not a statistically significant risk factor in the amnestic-MCI subtype model.",
        "В статье сообщается, что возраст не был статистически значимым фактором риска в модели амнестического MCI.",
        "no statistically significant association detected", ["U37", "U38"],
        {"factor": "older age", "outcome": "incident amnestic MCI", "analysis_model": "amnestic-subtype Cox model", "evidence_origin": "direct observation in this primary study"},
        knowledge_type="comparison", time="Baseline age to incident amnestic MCI",
        conditions=["No numerical estimate is supplied in this discussion passage.", "Nonsignificance does not establish absence of an age effect."])

    add("nonamnestic-subtype-age-estimate-ambiguous",
        "The article reports a significant age association in the nonamnestic-MCI model (HR 1.06 per year) but prints a 95% CI of 1.1–1.13, which is incompatible with that point estimate; retain the qualitative report and quarantine the numerical estimate.",
        "В статье сообщается о значимой связи возраста с неамнестическим MCI (HR 1,06 за год), но напечатанный 95% ДИ равен 1,1–1,13 и несовместим с точечной оценкой; сохраняем качественное сообщение, а числовую оценку исключаем из переноса.",
        "internally inconsistent reported age estimate", ["U39"],
        {"factor": "age per additional year", "outcome": "incident nonamnestic MCI", "analysis_model": "nonamnestic-subtype Cox model", "evidence_origin": "direct observation in this primary study"},
        knowledge_type="limitation", attrs={"hazard_ratio": {"value": 1.06, "unit": "dimensionless"},
        "printed_ci_low": {"value": 1.1, "unit": "dimensionless"}, "printed_ci_high": {"value": 1.13, "unit": "dimensionless"},
        "confidence_level": {"value": 95, "unit": "percent"}},
        time="Baseline age to incident nonamnestic MCI", conditions=["Source page 1908 was visually checked at high resolution; the printed confidence interval is internally inconsistent.", "Exclude this quantitative estimate from transfer and pooled comparisons."])

    add("nonamnestic-subtype-iadl-mmse",
        "In the nonamnestic-MCI Cox model, IADL impairment was associated with higher hazard (HR 1.74, 95% CI 1.02–2.97), while each additional MMSE point was associated with lower hazard (HR 0.78, 95% CI 0.68–0.89).",
        "В модели Кокса для неамнестического MCI нарушение IADL было связано с большей интенсивностью возникновения (HR 1,74; 95% ДИ 1,02–2,97), а каждый дополнительный балл MMSE — с меньшей (HR 0,78; 95% ДИ 0,68–0,89).",
        "nonamnestic MCI subtype model results", ["U39"], {"outcome": "incident nonamnestic MCI", "analysis_model": "nonamnestic-subtype Cox model"},
        knowledge_type="comparison", logic="conjunction", claims=[
            {"predicate": "higher hazard associated with IADL impairment", "roles": {"factor": "IADL impairment", "contrast": "impaired versus not impaired"}, "attrs": {"hazard_ratio": {"value": 1.74, "unit": "dimensionless"}, "ci_low": {"value": 1.02, "unit": "dimensionless"}, "ci_high": {"value": 2.97, "unit": "dimensionless"}, "confidence_level": {"value": 95, "unit": "percent"}}},
            {"predicate": "lower hazard per additional MMSE point", "roles": {"factor": "baseline MMSE", "contrast": "per one additional point"}, "attrs": {"hazard_ratio": {"value": 0.78, "unit": "dimensionless"}, "ci_low": {"value": 0.68, "unit": "dimensionless"}, "ci_high": {"value": 0.89, "unit": "dimensionless"}, "confidence_level": {"value": 95, "unit": "percent"}}},
        ], conditions=["Subtype-specific observational Cox estimates; do not merge with total- or amnestic-MCI models."])

    add("nonamnestic-private-home",
        "Living in a private home was reported as protective for incident nonamnestic MCI (HR 0.28, 95% CI 0.08–0.95); the reference category is not explicit in the available passage.",
        "Проживание в частном доме было указано как защитный фактор для возникновения неамнестического MCI (HR 0,28; 95% ДИ 0,08–0,95); референтная категория в доступном фрагменте не уточнена.",
        "reported protective association", ["U39"], {"exposure": "living in a private home", "outcome": "incident nonamnestic MCI", "analysis_model": "nonamnestic-subtype Cox model"},
        knowledge_type="result", attrs={"hazard_ratio": {"value": 0.28, "unit": "dimensionless"},
        "ci_low": {"value": 0.08, "unit": "dimensionless"}, "ci_high": {"value": 0.95, "unit": "dimensionless"},
        "confidence_level": {"value": 95, "unit": "percent"}},
        time="Baseline living situation to incident nonamnestic MCI", conditions=["Article calls this a protective factor; reference category is not stated in the passage and must not be guessed."])

    add("subtype-model-nonsignificant-factors",
        "The subtype-specific Cox discussion reports no statistically significant associations for several other factors, with significance patterns differing between amnestic and nonamnestic MCI.",
        "В обсуждении моделей подтипов для ряда других факторов не сообщается статистически значимых связей; набор таких факторов различается для амнестического и неамнестического MCI.",
        "subtype model nonsignificant findings", ["U37", "U39"], {"outcome": "incident MCI subtype", "comparison": "amnestic versus nonamnestic"},
        knowledge_type="comparison", logic="contrast", claims=[
            {"predicate": "not statistically significant in amnestic subtype model", "roles": {"factor": "sex, marital status, living situation, comorbidity, smoking, alcohol, family history, older age"}},
            {"predicate": "not statistically significant in nonamnestic subtype model", "roles": {"factor": "SMI, sex, marital status, comorbidity, smoking, alcohol, family history"}},
        ], conditions=["This is a report of nonsignificance, not evidence that these factors have no association.", "The subtype models have different outcomes and cannot be pooled."])

    add("proportional-hazards-check",
        "The reported global tests did not reject the proportional-hazards assumption for the amnestic and nonamnestic subtype Cox models (P=.75 and P=.14).",
        "Согласно глобальным тестам, предположение пропорциональности рисков не было отвергнуто для моделей амнестического и неамнестического подтипов (P=.75 и P=.14).",
        "proportional hazards diagnostic", ["U39"], {"test": "global proportional-hazards tests", "models": "amnestic and nonamnestic subtype Cox models"},
        knowledge_type="method", attrs={"amnestic_p_value": {"value": ".75", "unit": None}, "nonamnestic_p_value": {"value": ".14", "unit": None}},
        conditions=["Failure to reject the assumption is not proof that it is true."])

    add("incidence-limitations",
        "The authors cautioned that incidence may be underestimated because excluded participants were older; onset time was interval-imputed, SIDAM was brief, risk factors were limited to those planned, comorbidity was self-reported, and genetic, imaging, and biomarker data were unavailable.",
        "Авторы предупредили, что частота может быть занижена, поскольку исключённые участники были старше; время начала интерполировали внутри интервала, SIDAM был кратким, набор факторов риска был ограничен планом исследования, сопутствующие заболевания сообщали сами участники, а генетические, визуализационные и биомаркерные данные отсутствовали.",
        "study limitations", ["U42"], {"study": "LEILA 75+ incidence analysis", "estimate": "reported MCI incidence"},
        knowledge_type="limitation", logic="conjunction", claims=[
            {"predicate": "incidence may be underestimated due to selective exclusions", "roles": {"reason": "excluded participants were older"}, "modality": "possible"},
            {"predicate": "onset time was assigned between visits", "roles": {"method": "midpoint assignment"}},
            {"predicate": "brief SIDAM may have lower subtype sensitivity and specificity", "roles": {"instrument": "SIDAM"}, "modality": "possible"},
            {"predicate": "risk factors were limited to those planned for the study", "roles": {"measurement_scope": "risk-factor assessment"}},
            {"predicate": "comorbidity data were self-reported", "roles": {"measurement": "comorbidity"}},
            {"predicate": "genetic, neuroimaging, and biomarker data were available", "roles": {"missing_measurements": "genetic, neuroimaging, and biomarker data"}, "negated": True},
        ], conditions=["These are limitations stated by the authors, not quantified correction factors."])

    add("clinical-interpretation-caveat",
        "The authors state that many participants with MCI do not progress to dementia and that the current MCI diagnosis cannot itself be equated with a prodromal dementia stage; they describe SMI in cognitively healthy individuals as a possible prestage of MCI.",
        "Авторы отмечают, что у многих людей с MCI деменция не развивается и сам диагноз MCI нельзя приравнивать к продромальной стадии деменции; SMI у когнитивно здоровых людей рассматривается как возможная предшествующая стадия MCI.",
        "clinical interpretation and qualification", ["U42"], {"classification": "MCI", "possible_precursor": "subjective memory impairment"},
        knowledge_type="conclusion", logic="contrast", claims=[
            {"predicate": "does not necessarily progress to dementia", "roles": {"subject": "MCI cases"}, "quantifier": "many"},
            {"predicate": "cannot be equated with prodromal dementia", "roles": {"subject": "current MCI diagnosis"}, "negated": True},
            {"predicate": "may precede MCI", "roles": {"subject": "subjective memory impairment in cognitively healthy individuals", "object": "MCI"}, "modality": "possible"},
        ], conditions=["The authors qualify clinical interpretation; this is not a treatment recommendation or causal finding."])

    represented = {uid for item in records for uid in item["units"]}
    excluded = {}
    for uid in units:
        if uid in represented:
            continue
        if uid in {"U1", "U3", "U5", "U7", "U18", "U21", "U30", "U36", "U41", "U43", "U44"}:
            reason = "Заголовок, библиографические сведения, колонтитул или авторские сведения; самостоятельное научное знание здесь не формализуется."
        elif uid in {"U2", "U6", "U17", "U20", "U29", "U35", "U40"}:
            reason = "Маркер страницы исходного PDF; содержательного утверждения не содержит."
        elif uid == "U9":
            reason = "Метка схемы отбора; числовые значения и группы сохранены в блоке потока выборки."
        elif uid == "U10":
            reason = "Повторяет размер исходной выборки, сохранённый в блоке исходной популяции."
        elif uid == "U14":
            reason = "Причины отсутствия диагноза и выбытия относятся к деталям рисунка потока; этот фрагмент пока не формализован исчерпывающе."
        elif uid == "U15":
            reason = "Сноска к рисунку о возможности применить критерии; основные критерии и исключения уже связаны с потоком выборки."
        elif uid == "U16":
            reason = "Подпись к рисунку; количественный поток представлен отдельно."
        elif uid == "U22":
            reason = "Заголовок таблицы; данные таблицы представлены в соответствующих блоках, а не как отдельное знание."
        elif uid == "U26":
            reason = "Заголовки колонок таблицы 2; значения привязаны к явно названным возрастным и половым группам."
        elif uid == "U32":
            reason = "Заголовок таблицы 3; оценки модели представлены отдельными знаниями."
        else:
            reason = "Фрагмент просмотрен; самостоятельное утверждение для текущего частичного черновика не выделено."
        excluded[uid] = reason

    require(len({record["key"] for record in records}) == len(records), "Duplicate manual knowledge key")
    return {
        "version": "luck2010-codex-manual-map-v2",
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "knowledge": records,
        "transitions": [
            {"sources": ["study-design", "followup-schedule"], "target": "risk-set-flow", "usage": "method",
             "reason": "The cohort and assessment schedule define the observed population at risk.", "units": ["U8", "U12"]},
            {"sources": ["mci-core-definition", "risk-set-flow"], "target": "incidence-analysis-selection", "usage": "definition",
             "reason": "The case definition and baseline risk set determine who can enter the incidence calculation.", "units": ["U19", "U13"]},
            {"sources": ["incidence-person-time-method", "incidence-analysis-selection"], "target": "overall-mci-incidence", "usage": "data",
             "reason": "The incidence method and included sample support the reported total cases and person-time rate.", "units": ["U19", "U24"]},
            {"sources": ["mci-core-definition", "incidence-person-time-method", "incidence-analysis-selection"], "target": "total-mci-age-rates", "usage": "data",
             "reason": "Age-stratified table rates use the study definition, person-time method, and incidence sample.", "units": ["U19", "U27"]},
            {"sources": ["mci-core-definition", "incidence-person-time-method", "incidence-analysis-selection"], "target": "total-mci-sex-rates", "usage": "data",
             "reason": "Sex-stratified table rates use the study definition, person-time method, and incidence sample.", "units": ["U19", "U27"]},
            {"sources": ["subtype-single-amnestic", "subtype-single-nonmemory", "subtype-multidomain-amnestic", "subtype-multidomain-nonamnestic", "incidence-person-time-method", "incidence-analysis-selection"], "target": "mci-subtype-incidence-rates", "usage": "data",
             "reason": "Subtype rate groups follow the operational definitions and are calculated over the incidence sample.", "units": ["U19", "U27", "U28"]},
            {"sources": ["cox-model-method", "smi-measurement", "incidence-analysis-selection"], "target": "total-smi-association", "usage": "method",
             "reason": "The measured baseline exposure and complete-case Cox model support this association estimate.", "units": ["U19", "U33", "U34"]},
            {"sources": ["cox-model-method", "iadl-measurement", "incidence-analysis-selection"], "target": "total-iadl-association", "usage": "method",
             "reason": "The measured baseline functional status and complete-case Cox model support this association estimate.", "units": ["U19", "U33", "U34"]},
            {"sources": ["cox-model-method", "incidence-analysis-selection"], "target": "total-age-association", "usage": "method",
             "reason": "The complete-case Cox model reports the age association for incident total MCI.", "units": ["U19", "U33", "U34"]},
            {"sources": ["cox-model-method", "incidence-analysis-selection"], "target": "total-mmse-association", "usage": "method",
             "reason": "The complete-case Cox model reports the per-point MMSE association for incident total MCI.", "units": ["U19", "U33", "U34"]},
            {"sources": ["smi-measurement", "onset-midpoint-method"], "target": "smi-time-to-diagnosis", "usage": "method",
             "reason": "The baseline SMI groups and assigned onset times define the Kaplan–Meier comparison.", "units": ["U19", "U37", "U38"]},
            {"sources": ["cox-model-method", "subtype-single-amnestic", "subtype-multidomain-amnestic"], "target": "amnestic-subtype-model-results", "usage": "method",
             "reason": "The subtype definitions and Cox model define the reported amnestic-MCI endpoint and estimates.", "units": ["U19", "U37", "U38"]},
            {"sources": ["cox-model-method", "subtype-single-nonmemory", "subtype-multidomain-nonamnestic"], "target": "nonamnestic-subtype-age-estimate-ambiguous", "usage": "method",
             "reason": "The article reports an age association for the nonamnestic endpoint, while the printed interval is preserved as inconsistent.", "units": ["U19", "U39"]},
            {"sources": ["cox-model-method", "subtype-single-nonmemory", "subtype-multidomain-nonamnestic"], "target": "nonamnestic-subtype-iadl-mmse", "usage": "method",
             "reason": "The subtype definitions and Cox model define the reported nonamnestic-MCI estimates.", "units": ["U19", "U39"]},
        ],
        "excluded_units": excluded,
        "source_limitations": [
            "Это вручную подготовленный исследовательский черновик из полного текста, а не семантически полная карта.",
            "Таблицы 1–3 просмотрены по PDF; все ячейки и все предложения статьи ещё не формализованы.",
            "Карта не проверена экспертами и не должна трактоваться как клиническая рекомендация.",
            "Опечатка внутренне несовместимого доверительного интервала HR возраста для неамнестического MCI сохранена и помечена; показатель исключён из количественного переноса.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    disable_network()
    root = args.root.resolve()
    pdf_path = root / "personal_folder/luck2010.pdf"
    source_path = root / SOURCE_FOLDER / "source.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    require(sha256(pdf_path.read_bytes()).hexdigest() == PDF_SHA256, "Luck 2010 PDF hash differs from reviewed source")
    require(source["sha256"] == SOURCE_SHA256, "Luck 2010 source revision differs from reviewed source")
    authored = build_authored(source)
    artifacts = prepare_manual_map(
        ARTICLE_ID, source["text"], SOURCE_SHA256, authored,
        PROMPT_PATH.read_text(encoding="utf-8"), DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8"),
    )
    graph = artifacts["map.json"]["graph"]
    evidence_audit = audit_evidence_origin(graph)
    artifacts["empirical-evidence-eligibility.json"] = evidence_audit
    artifacts["validation.json"]["direct_evidence_eligible_blocks"] = evidence_audit["eligible_blocks"]
    report = [
        "# Luck 2010: отдельный черновик карты полного текста", "",
        f"Проверенный PDF: `{PDF_SHA256}`. Текстовая ревизия: `{SOURCE_SHA256}`.",
        f"Подготовлено {len(graph['knowledge'])} канонических знаний, {sum(len(k['semantic_frame']['statements']) for k in graph['knowledge'])} утверждений и {len(graph['transitions'])} обоснованных переходов.",
        f"Видимый граф: {graph['analysis']['depth']} уровня; {graph['analysis']['isolated_count']} изолированных знаний. Проверка контракта и DAG выполнена общим сценарием подготовки.", "",
        "## Что сохранено", "",
        "Формализованы дизайн и выборка LEILA 75+, критерии и подтипы MCI, инструменты и методы анализа, общая и стратифицированная частота, оценки моделей Кокса, временные ограничения и авторские оговорки.",
        "На страницах 1904–1908 по PDF визуально сверены поток участников, определения, методы и таблицы 1–3. Для представленных табличных строк сохранены знаменатели, человеко-годы, единицы, возрастные группы, исходы и доверительные интервалы.",
        "Оценки общего MCI отделены от амнестического и неамнестического подтипов. Ассоциации остаются наблюдательными. Статистическая незначимость не превращена в отсутствие эффекта.",
        "Для возраста в модели неамнестического MCI статья печатает HR 1.06 при 95% ДИ 1.1–1.13. PDF просмотрен в увеличенном разрешении: интервал действительно несовместим с HR. Запись сохранена как качественное сообщение с пометкой и не допускается к количественному переносу.", "",
        f"Фильтр прямых эмпирических данных пропустил {evidence_audit['eligible_blocks']} блоков; все они принадлежат одной публикации и не считаются независимыми подтверждениями.", "",
        "## Ограничения", "",
        "Это отдельная частичная версия: семантическая полнота и исчерпывающая формализация всех табличных ячеек не заявлены. Предыдущая карта и исходные файлы не изменены.",
        "Авторство ручной интерпретации — Codex. Внешние и локальные LLM, переводчики и эмбеддинги не вызывались. Экспертная проверка научной точности требуется; новая карта пока не включена в прогнозный корпус.", "",
    ]
    artifacts["report.ru.md"] = "\n".join(report)
    artifacts["source-review.json"] = {
        "article_id": ARTICLE_ID, "pdf_sha256": PDF_SHA256, "source_sha256": SOURCE_SHA256,
        "visually_reviewed_pdf_pages": [1, 2, 3, 4, 5, 6, 7, 8],
        "table_pages_reviewed": [4, 5], "subtype_model_page_reviewed_high_resolution": 6,
        "references_excluded_from_knowledge_extraction": True,
        "full_semantic_coverage": False, "all_table_cells_formalized": False,
        "expert_validated": False, "external_llm_calls": 0, "local_llm_calls": 0,
    }
    output = root / OUTPUT_FOLDER / artifacts["map.json"]["run_id"]
    for name, value in artifacts.items():
        payload = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        write_immutable(output / name, payload)
    print(output)
    print(json.dumps({"run_id": artifacts["map.json"]["run_id"], "knowledge": len(graph["knowledge"]),
                      "transitions": len(graph["transitions"]), "depth": graph["analysis"]["depth"],
                      "isolated": graph["analysis"]["isolated_count"], "model_calls": 0,
                      "complete_semantic_coverage": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
