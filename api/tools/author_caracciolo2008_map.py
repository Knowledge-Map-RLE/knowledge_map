"""Создаёт выборочную исследовательскую карту статьи Caracciolo et al. 2008."""
from __future__ import annotations

import argparse
import json
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
from tools.author_roberts_katz_maps import _normalize, source_unit
from tools.run_free_prediction import disable_network


ARTICLE_ID = "caracciolo2008"
DOI = "10.1212/01.wnl.0000288180.21984.cb"
TITLE = "Occurrence of cognitive impairment and dementia in the community: A 9-year-long prospective study"
TITLE_RU = "Возникновение когнитивных нарушений и деменции в сообществе: 9-летнее проспективное исследование"
SOURCE_ROOT = ROOT / "eval/free_prediction/primary-pdf-cohort-v1/sources" / ARTICLE_ID
OUTPUT_ROOT = ROOT / "eval/whole_map_forecast/caracciolo2008-codex-map-v1/runs"
PDF_SHA256 = "effafa6c52fe6a355ac90e7eab1780f77a50a0b422eeed5d5482012a1ebd88f5"
LAYOUT_SHA256 = "08765f240af7d75ad6e18142aad270d8cbfcdcf357913206662bd1c0387b3497"


def extract_pdf(pdf_path: Path) -> tuple[str, list[tuple[int, int]], list[str]]:
    """Извлекает страницы PDF и записывает их координаты в кодовых точках Unicode."""
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
            require(bool(text), f"Страница PDF {index + 1} не содержит извлекаемого текста")
            pages.append(text)
            text_page.close()
            page.close()
        document.close()
    ranges = []
    cursor = 0
    for page in pages:
        ranges.append((cursor, cursor + len(page)))
        cursor += len(page) + 2
    return "\n\n".join(pages), ranges, pages


def build_authored(source: dict, page_ranges: list[tuple[int, int]]) -> dict:
    """Фиксирует выбранные знания и авторские переходы со ссылками на PDF-фрагменты."""
    records: list[dict] = []
    transitions: list[dict] = []

    def units(refs: list[tuple[int, str]]) -> list[str]:
        return list(dict.fromkeys(
            unit_id
            for page, anchor in refs
            for unit_id in source_unit(source, page_ranges, page, anchor)
        ))

    def add(
        key: str,
        en: str,
        ru: str,
        predicate: str,
        refs: list[tuple[int, str]],
        roles: dict[str, str],
        *,
        kind: str = "state",
        knowledge_type: str = "result",
        attrs: dict | None = None,
        claims: list[dict] | None = None,
        logic: str = "single",
        conditions: list[str] | None = None,
        time: str | None = None,
    ) -> None:
        record = {
            "key": key, "en": en, "ru": ru, "predicate": predicate,
            "units": units(refs), "roles": roles, "attrs": attrs or {},
            "kind": kind, "type": knowledge_type, "logic": logic,
            "conditions": conditions or [], "time": time,
        }
        if claims:
            record["claims"] = claims
        records.append(record)

    def transition(sources: list[str], target: str, usage: str, reason: str,
                   refs: list[tuple[int, str]]) -> None:
        by_key = {item["key"]: item["units"] for item in records}
        endpoint_units = [unit_id for key in [*sources, target] for unit_id in by_key[key]]
        transitions.append({
            "sources": sources, "target": target, "usage": usage,
            "reason": reason,
            "units": list(dict.fromkeys([*endpoint_units, *units(refs)])),
        })

    observational = ["Observational estimates do not establish causation."]

    add(
        "study-design",
        "The Kungsholmen Project was a population-based prospective study of aging and dementia in Stockholm residents aged 75 years or older in 1987.",
        "Kungsholmen Project было популяционным проспективным исследованием старения и деменции среди жителей Стокгольма в возрасте 75 лет и старше в 1987 году.",
        "prospective cohort design",
        [(2, "a prospective population-based study on aging"),
         (2, "who lived in Kungsholmen, Stockholm, Sweden, in 1987")],
        {"study": "Kungsholmen Project", "setting": "Kungsholmen, Stockholm, Sweden", "population": "residents aged 75 years or older"},
        knowledge_type="method",
        attrs={"design": {"value": "population-based prospective cohort", "unit": None},
               "baseline_year": {"value": 1987, "unit": "year"},
               "minimum_age": {"value": 75, "unit": "years"}},
        time="Baseline in 1987",
    )
    add(
        "analysis-populations",
        "Dementia incidence was estimated in 1,435 dementia-free participants; aMCI and OCIND incidence were studied in 1,070 cognitively unimpaired participants.",
        "Частоту деменции оценивали у 1 435 участников без деменции; частоту aMCI и OCIND изучали у 1 070 участников без когнитивных нарушений.",
        "study population denominators",
        [(2, "For the estimation of dementia incidence, the dementia-free cohort"),
         (2, "a cohort of 1,070 persons remained for the present study"),
         (3, "Cognitively unimpaired participants at baseline")],
        {"study": "Kungsholmen Project", "dementia_risk_set": "dementia-free participants", "non_dementia_impairment_risk_set": "cognitively unimpaired participants"},
        knowledge_type="observation",
        logic="contrast",
        claims=[
            {"predicate": "dementia incidence denominator", "roles": {"risk_set": "dementia-free participants"},
             "attrs": {"sample_size": {"value": 1435, "unit": "participants"}}},
            {"predicate": "non-dementia impairment denominator", "roles": {"risk_set": "cognitively unimpaired participants"},
             "attrs": {"sample_size": {"value": 1070, "unit": "participants"}}},
        ],
    )
    add(
        "follow-up-schedule",
        "Participants were followed for 9 years with three follow-up examinations at approximately 3-year intervals.",
        "Участников наблюдали 9 лет, проведя три повторных обследования с интервалами около 3 лет.",
        "follow-up schedule",
        [(2, "Subjects were followed for 9 years"), (2, "three examinations took place, at approximately 3-yearly intervals")],
        {"cohort": "Kungsholmen Project", "participants": "study participants", "assessment": "follow-up examination"},
        knowledge_type="method",
        attrs={"duration": {"value": 9, "unit": "years"},
               "follow_up_examinations": {"value": 3, "unit": "examinations"},
               "interval": {"value": 3, "unit": "approximately years"}},
    )
    add(
        "amci-definition",
        "Incident aMCI required a memory complaint, preserved global cognition, no dementia, normal daily function, and objective memory impairment.",
        "Для нового случая aMCI требовались жалоба на память, сохранная общая когнитивная функция, отсутствие деменции, сохранная повседневная активность и объективное нарушение памяти.",
        "operational aMCI definition",
        [(2, "aMCI was defined according to Petersen’s criteria"),
         (3, "Objective memory impairment for prevalent cases"),
         (3, "For incident cases the criterion was defined as")],
        {"classification": "incident aMCI", "participant": "cognitively unimpaired participant"},
        knowledge_type="definition",
        logic="conjunction",
        conditions=["For incident cases, objective memory impairment used a verbal memory task with an age- and education-specific 1.5 SD cutoff."],
        claims=[
            {"predicate": "requires memory complaint", "roles": {"criterion": "subject or close informant report of troublesome memory problems"}},
            {"predicate": "requires preserved global cognition", "roles": {"criterion": "MMSE above the age- and education-specific impairment cutoff"}},
            {"predicate": "requires absence of dementia", "roles": {"criterion": "no dementia diagnosis"}},
            {"predicate": "requires normal daily function", "roles": {"criterion": "no relevant functional impairment on Katz Activities of Daily Living scale"}},
            {"predicate": "requires objective memory impairment", "roles": {"criterion": "1.5 SD below age- and education-specific mean on verbal memory task"}},
        ],
    )
    add(
        "ocind-definition",
        "OCIND required absence of dementia and global cognitive impairment at least 1 SD below age- and education-specific MMSE means.",
        "Для OCIND требовались отсутствие деменции и общая когнитивная функция не менее чем на 1 стандартное отклонение ниже среднего MMSE для возраста и образования.",
        "operational OCIND definition",
        [(3, "OCIND) that was defined as 1) not having dementia"),
         (3, "scoring 1 SD or more below age- and education-specific means on the MMSE")],
        {"classification": "OCIND", "participant": "cognitively unimpaired participant"},
        knowledge_type="definition",
        logic="conjunction",
        claims=[
            {"predicate": "requires absence of dementia", "roles": {"criterion": "no dementia diagnosis"}},
            {"predicate": "requires MMSE impairment", "roles": {"criterion": "at least 1 SD below age- and education-specific mean"}},
        ],
    )
    add(
        "endpoint-exclusivity",
        "The study criteria made aMCI and OCIND mutually exclusive classifications.",
        "По критериям исследования классификации aMCI и OCIND не пересекались.",
        "mutually exclusive endpoint definitions",
        [(3, "aMCI and OCIND were mutually exclusive in our study")],
        {"classification_a": "aMCI", "classification_b": "OCIND", "study": "Kungsholmen Project"},
        knowledge_type="definition",
        conditions=["Mutual exclusivity applies to this study's operational criteria."],
    )
    add(
        "death-attrition",
        "During follow-up, 539 of 1,070 participants died (50.4%); those who died were older than survivors.",
        "Во время наблюдения умерли 539 из 1 070 участников (50,4%); умершие были старше выживших.",
        "reported group comparison",
        [(2, "a total of 539 deceased subjects (50.4%; table 1)"),
         (2, "Those who died during the time of the study were older")],
        {"group": "participants who died", "comparison_group": "survivors", "cohort": "Kungsholmen Project"},
        knowledge_type="comparison",
        attrs={"deaths": {"value": 539, "unit": "participants"},
               "death_fraction": {"value": 50.4, "unit": "percent"}},
        conditions=["The age difference was reported as p < 0.001."],
        time="Nine-year follow-up",
    )
    add(
        "estimate-incidence-rates",
        "The authors estimated incidence as new events per person-years and calculated 95% confidence intervals using the Poisson distribution.",
        "Авторы рассчитывали частоту новых случаев на человеко-годы, а 95%-ные доверительные интервалы — по распределению Пуассона.",
        "estimate incidence rate",
        [(3, "Incidence rates were calculated as the number of new events divided by the time at risk"),
         (3, "95% CIs calculated according to the Poisson distribution")],
        {"events": "newly diagnosed events", "denominator": "person-years at risk", "method": "Poisson distribution for confidence intervals"},
        kind="action",
        knowledge_type="operation",
        attrs={"confidence_level": {"value": 95, "unit": "percent"}},
        conditions=["Participants left the risk set at diagnosis, refusal or moving, or death as specified for each outcome."],
    )
    add(
        "observed-case-counts",
        "Observed during 9 years were 49 incident aMCI cases and 145 incident OCIND cases over 4,292 person-years.",
        "За 9 лет наблюдения выявили 49 новых случаев aMCI и 145 случаев OCIND за 4 292 человеко-года.",
        "reported cohort incidence",
        [(4, "49 incident aMCI cases and 145 incident OCIND cases"),
         (4, "during 4,292 person-years of follow-up")],
        {"cohort": "Kungsholmen Project", "outcomes": "incident aMCI and incident OCIND"},
        knowledge_type="result",
        logic="conjunction",
        attrs={"follow_up": {"value": 9, "unit": "years"},
               "person_time": {"value": 4292, "unit": "person-years"}},
        conditions=observational,
    )
    add(
        "observed-incidence-rates",
        "Observed incidence per 1,000 person-years was 11.4 for aMCI (95% CI 8.6–15.1) and 33.8 for OCIND (28.7–39.8).",
        "Наблюдаемая частота на 1 000 человеко-лет составила 11,4 для aMCI (95% ДИ 8,6–15,1) и 33,8 для OCIND (28,7–39,8).",
        "incident mci rate",
        [(4, "11.4 (95% CI: 8.6 to 15.1) for aMCI"),
         (4, "33.8 (95% CI: 28.7 to 39.8) for OCIND per 1,000 person-years")],
        {"cohort": "Kungsholmen Project", "measure": "incidence per 1,000 person-years"},
        knowledge_type="comparison",
        logic="contrast",
        claims=[
            {"predicate": "incident mci rate", "roles": {"outcome": "aMCI"},
             "attrs": {"rate": {"value": 11.4, "unit": "per 1,000 person-years"},
                       "confidence_interval": {"value": "8.6–15.1", "unit": "95% CI"}}},
            {"predicate": "incident mci rate", "roles": {"outcome": "OCIND"},
             "attrs": {"rate": {"value": 33.8, "unit": "per 1,000 person-years"},
                       "confidence_interval": {"value": "28.7–39.8", "unit": "95% CI"}}},
        ],
        conditions=observational,
    )
    add(
        "impute-deceased-participant-status",
        "The authors used multiple imputation to estimate missing aMCI or OCIND status for 346 deceased participants who were cognitively unimpaired at their last observation.",
        "Авторы применили множественную импутацию, чтобы оценить отсутствующий статус aMCI или OCIND у 346 умерших участников, сохранявших нормальные когнитивные функции при последнем обследовании.",
        "analyze data",
        [(4, "Missing information on the presence/absence of aMCI or"),
         (4, "cognitively unimpaired at the last observation"),
         (4, "generate five plausible estimates of the missing values")],
        {"analysis": "multiple imputation", "missing_status": "aMCI or OCIND status", "participants": "deceased participants unimpaired at last observation"},
        kind="action",
        knowledge_type="operation",
        attrs={"participants": {"value": 346, "unit": "participants"},
               "imputed_datasets": {"value": 5, "unit": "datasets"}},
        conditions=["Predictors included variables related to cognitive impairment or mortality; pooled estimates used Rubin's formula."],
    )
    add(
        "corrected-case-counts",
        "After correcting for mortality, the analyses detected 64 incident aMCI cases and 196 incident OCIND cases over 4,655 person-years.",
        "После поправки на смертность в анализах выявили 64 новых случая aMCI и 196 случаев OCIND за 4 655 человеко-лет.",
        "reported cohort incidence",
        [(4, "64 incident aMCI cases and 196 OCIND cases"),
         (4, "during 4,655 person-years of follow-up")],
        {"cohort": "Kungsholmen Project", "outcomes": "incident aMCI and incident OCIND"},
        knowledge_type="result",
        logic="conjunction",
        attrs={"person_time": {"value": 4655, "unit": "person-years"}},
        conditions=[*observational, "Incidence estimates were corrected for cognitive status missing after death."],
    )
    add(
        "corrected-incidence-rates",
        "Corrected incidence per 1,000 person-years was 13.7 for aMCI (95% CI 10.3–18.2) and 42.1 for OCIND (36.5–48.6).",
        "Скорректированная частота на 1 000 человеко-лет составила 13,7 для aMCI (95% ДИ 10,3–18,2) и 42,1 для OCIND (36,5–48,6).",
        "adjusted incidence rate",
        [(4, "increased to 13.7 (10.3 to 18.2) and 42.1"),
         (4, "(36.5 to 48.6)")],
        {"cohort": "Kungsholmen Project", "measure": "incidence per 1,000 person-years"},
        knowledge_type="comparison",
        logic="contrast",
        claims=[
            {"predicate": "adjusted incidence rate", "roles": {"outcome": "aMCI"},
             "attrs": {"rate": {"value": 13.7, "unit": "per 1,000 person-years"},
                       "confidence_interval": {"value": "10.3–18.2", "unit": "95% CI"}}},
            {"predicate": "adjusted incidence rate", "roles": {"outcome": "OCIND"},
             "attrs": {"rate": {"value": 42.1, "unit": "per 1,000 person-years"},
                       "confidence_interval": {"value": "36.5–48.6", "unit": "95% CI"}}},
        ],
        conditions=[*observational, "Incidence estimates were corrected for cognitive status missing after death."],
    )
    add(
        "age-specific-incidence-pattern",
        "Observed incidence increased with age for aMCI and OCIND; after mortality correction, rates in participants aged 85 years or older were higher, especially for OCIND.",
        "Наблюдаемая частота aMCI и OCIND возрастала с возрастом; после поправки на смертность частоты среди участников 85 лет и старше были выше, особенно для OCIND.",
        "age-specific incidence",
        [(5, "All, age groups"), (5, "75–79"), (5, "80–84"), (5, "85"),
         (4, "similar in the younger age groups"),
         (4, "differed among the")],
        {"outcome": "aMCI and OCIND incidence", "modifier": "age group", "comparison": "observed versus corrected estimates"},
        knowledge_type="comparison",
        logic="conjunction",
        claims=[
            {"predicate": "age-specific incidence", "roles": {"age_group": "75–79 years"},
             "attrs": {"observed_aMCI": {"value": 5.3, "unit": "per 1,000 person-years"},
                       "observed_OCIND": {"value": 8.5, "unit": "per 1,000 person-years"},
                       "corrected_aMCI": {"value": 5.4, "unit": "per 1,000 person-years"},
                       "corrected_OCIND": {"value": 9.2, "unit": "per 1,000 person-years"}}},
            {"predicate": "age-specific incidence", "roles": {"age_group": "80–84 years"},
             "attrs": {"observed_aMCI": {"value": 9.6, "unit": "per 1,000 person-years"},
                       "observed_OCIND": {"value": 31.9, "unit": "per 1,000 person-years"},
                       "corrected_aMCI": {"value": 11.2, "unit": "per 1,000 person-years"},
                       "corrected_OCIND": {"value": 36.4, "unit": "per 1,000 person-years"}}},
            {"predicate": "age-specific incidence", "roles": {"age_group": "85 years or older"},
             "attrs": {"observed_aMCI": {"value": 16.3, "unit": "per 1,000 person-years"},
                       "observed_OCIND": {"value": 48.8, "unit": "per 1,000 person-years"},
                       "corrected_aMCI": {"value": 20.2, "unit": "per 1,000 person-years"},
                       "corrected_OCIND": {"value": 64.6, "unit": "per 1,000 person-years"}}},
        ],
        conditions=[*observational, "Table 2 reports 95% confidence intervals; values here are point estimates."],
    )
    add(
        "age-associated-incidence-ratios",
        "For each 5-year age increase, the reported incidence-rate ratio was 1.8 for observed aMCI and 2.0 for observed OCIND; corrected estimates were 1.9 and 2.2.",
        "На каждые 5 лет возраста отношение частот составило 1,8 для наблюдаемой aMCI и 2,0 для OCIND; после поправки оценки составили 1,9 и 2,2.",
        "age and education incidence patterns",
        [(5, "Age, 5-year increment"), (5, "1.8 (1.2–2.7)"),
         (5, "2.0 (1.6–2.5)"), (5, "2.2 (1.8–2.8)")],
        {"modifier": "5-year age increment", "outcome": "incident aMCI or OCIND"},
        knowledge_type="comparison",
        logic="contrast",
        claims=[
            {"predicate": "age and education incidence patterns", "roles": {"outcome": "aMCI", "estimate": "observed"},
             "attrs": {"incidence_rate_ratio": {"value": 1.8, "unit": "per 5-year age increment"},
                       "confidence_interval": {"value": "1.2–2.7", "unit": "95% CI"}}},
            {"predicate": "age and education incidence patterns", "roles": {"outcome": "OCIND", "estimate": "observed"},
             "attrs": {"incidence_rate_ratio": {"value": 2.0, "unit": "per 5-year age increment"},
                       "confidence_interval": {"value": "1.6–2.5", "unit": "95% CI"}}},
            {"predicate": "age and education incidence patterns", "roles": {"outcome": "aMCI", "estimate": "corrected"},
             "attrs": {"incidence_rate_ratio": {"value": 1.9, "unit": "per 5-year age increment"},
                       "confidence_interval": {"value": "1.2–3.1", "unit": "95% CI"}}},
            {"predicate": "age and education incidence patterns", "roles": {"outcome": "OCIND", "estimate": "corrected"},
             "attrs": {"incidence_rate_ratio": {"value": 2.2, "unit": "per 5-year age increment"},
                       "confidence_interval": {"value": "1.8–2.8", "unit": "95% CI"}}},
        ],
        conditions=[*observational, "The comparison is an adjusted observational association, not a causal effect."],
    )
    add(
        "mortality-correction-effect",
        "Correcting for death-related attrition increased estimated non-dementia cognitive-impairment incidence, with larger differences at older ages.",
        "Поправка на выбывание из-за смерти повысила оценку частоты когнитивных нарушений без деменции; различие было больше в старших возрастных группах.",
        "reported incidence rate difference",
        [(1, "often underestimated in population studies that do not adjust for attrition"),
         (4, "similar in the younger age groups"),
         (4, "differed among the"),
         (6, "the incidence of non-dementia cognitive impairment increased when the data were corrected")],
        {"estimate": "corrected incidence", "comparison": "observed incidence", "modifier": "age"},
        knowledge_type="conclusion",
        logic="argument",
        conditions=[*observational, "The authors estimate an overall underestimation of around 20%; residual unmeasured factors may remain."],
    )
    add(
        "age-pattern-dementia-comparison",
        "The joint incidence of aMCI and OCIND was close to dementia incidence at ages 75–79, but became increasingly lower with age.",
        "Совместная частота aMCI и OCIND была близка к частоте деменции в возрасте 75–79 лет, но с возрастом становилась относительно ниже.",
        "reported group comparison",
        [(6, "The joint incidence of aMCI and OCIND was close to that of dementia at age 75 to 79"),
         (6, "became increasingly lower with increasing age")],
        {"outcome_a": "joint aMCI and OCIND incidence", "outcome_b": "dementia incidence", "modifier": "age"},
        knowledge_type="comparison",
        logic="contrast",
        conditions=observational,
    )
    add(
        "study-limitation",
        "The authors could not exclude residual factors related to cognitive impairment and mortality that were not included in the imputation model.",
        "Авторы не исключили остаточное влияние факторов когнитивных нарушений и смертности, не включённых в модель импутации.",
        "interpretation limited by",
        [(6, "we cannot exclude the possibility that some factors related to cognitive impairment and mortality were not taken into account in our model")],
        {"analysis": "mortality-corrected incidence estimates", "limitation": "unmeasured predictors"},
        knowledge_type="limitation",
        conditions=["The article also notes possible underestimation of terminal cognitive decline."],
    )

    transition(
        ["study-design"], "analysis-populations", "definition",
        "The population-based cohort and its eligibility exclusions define the two reported risk sets.",
        [(2, "For the estimation of dementia incidence"), (2, "a cohort of 1,070 persons remained")],
    )
    transition(
        ["analysis-populations"], "follow-up-schedule", "method",
        "The study describes the follow-up schedule for the selected cohort.",
        [(2, "Subjects were followed for 9 years")],
    )
    transition(
        ["analysis-populations", "follow-up-schedule", "amci-definition", "ocind-definition"],
        "observed-case-counts", "data",
        "The reported incident cases are classified under the study definitions during follow-up.",
        [(4, "49 incident aMCI cases and 145 incident OCIND cases")],
    )
    transition(
        ["observed-case-counts"], "estimate-incidence-rates", "data",
        "The paper defines incidence rates from new events and time at risk.",
        [(3, "number of new events divided by the time at risk")],
    )
    transition(
        ["estimate-incidence-rates"], "observed-incidence-rates", "result",
        "The incidence calculation produces the observed rates reported in the Results section.",
        [(4, "Overall incidence rates (95% CI)")],
    )
    transition(
        ["death-attrition"], "impute-deceased-participant-status", "condition",
        "Missing impairment status among deceased participants is the stated reason for the mortality correction.",
        [(4, "Missing information on the presence/absence of aMCI or OCIND in deceased subjects")],
    )
    transition(
        ["impute-deceased-participant-status"], "corrected-case-counts", "data",
        "Multiple imputation supplies corrected case counts for the mortality-adjusted analysis.",
        [(4, "After correcting for mortality during follow-up")],
    )
    transition(
        ["corrected-case-counts"], "estimate-incidence-rates", "data",
        "The corrected person-time and imputed case counts enter the same incidence-rate estimation procedure.",
        [(4, "Overall incidence rates of aMCI and OCIND increased")],
    )
    transition(
        ["estimate-incidence-rates"], "corrected-incidence-rates", "result",
        "The incidence calculation reports corrected rates after imputing status missing after death.",
        [(4, "increased to 13.7")],
    )
    transition(
        ["observed-incidence-rates", "corrected-incidence-rates"], "age-specific-incidence-pattern",
        "result", "Table 2 compares observed and mortality-corrected incidence across age and gender strata.",
        [(5, "Observed rates"), (5, "Corrected")],
    )
    transition(
        ["observed-incidence-rates", "corrected-incidence-rates"], "mortality-correction-effect",
        "result", "The authors compare observed and corrected incidence and interpret the larger estimates after correction.",
        [(1, "often underestimated in population studies"), (4, "differed among the")],
    )
    transition(
        ["age-specific-incidence-pattern"], "age-associated-incidence-ratios", "result",
        "The regression models quantify the age-related incidence pattern for aMCI and OCIND.",
        [(4, "confirmed the age and gender trends")],
    )
    transition(
        ["age-specific-incidence-pattern"], "age-pattern-dementia-comparison", "result",
        "The article compares age-stratified non-dementia impairment incidence with dementia incidence.",
        [(4, "dementia rates are graphed too")],
    )
    transition(
        ["death-attrition", "impute-deceased-participant-status"], "study-limitation", "condition",
        "The correction depends on imputation predictors and cannot rule out unmeasured determinants of death or impairment.",
        [(6, "we cannot exclude the possibility")],
    )

    covered = {unit_id for item in records for unit_id in item["units"]}
    transition_only = {unit_id for edge in transitions for unit_id in edge["units"]} - covered
    excluded = {}
    for item in source["units"]:
        if item["id"] in covered:
            continue
        if item["id"] in transition_only:
            excluded[item["id"]] = "Фрагмент использован для обоснования перехода, но не включён как самостоятельное каноническое знание."
        else:
            excluded[item["id"]] = "Фрагмент прочитан, но не включён в выборочную карту; полное смысловое покрытие не заявляется."

    return {
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "concept_aliases": {
            "amnestic mild cognitive impairment": ["aMCI", "amnestic MCI"],
            "other cognitive impairment, no dementia": ["OCIND"],
            "cognitive impairment, no dementia": ["CIND"],
            "Mini-Mental State Examination": ["MMSE"],
        },
        "source_limitations": [
            "Статья просмотрена по полному пользовательскому PDF; модельные вызовы, переводчик и эмбеддинги не использовались.",
            "Карта выборочная: не все положения текста и таблиц преобразованы в знания.",
            "Числа таблиц сверены с изображениями страниц 4–6 PDF; полный постраничный визуальный аудит всех библиографических записей не выполнялся.",
            "Наблюдательные связи не трактуются как причинные; коррекция смертности основана на множественной импутации.",
            "Статья была ранее прочитана при аудите корпуса и не является слепой контрольной статьёй.",
            "Научная экспертная проверка отсутствует.",
        ],
        "knowledge": records,
        "transitions": transitions,
        "excluded_units": excluded,
    }


def write_run() -> Path:
    disable_network()
    pdf_path = SOURCE_ROOT / "article.pdf"
    layout_path = SOURCE_ROOT / "article.layout.txt"
    intake = json.loads((SOURCE_ROOT / "intake.json").read_text(encoding="utf-8"))
    require(sha256(pdf_path.read_bytes()).hexdigest() == PDF_SHA256, "Хеш исходного PDF изменён")
    require(sha256(layout_path.read_bytes()).hexdigest() == LAYOUT_SHA256, "Хеш извлечённой раскладки изменён")
    text, page_ranges, pages = extract_pdf(pdf_path)
    require(len(pages) == 9, "Число страниц исходного PDF не совпадает")
    require(_normalize(TITLE.replace(":", "")) in _normalize(pages[0]), "Заголовок не подтверждён первой страницей")
    require(DOI in pages[-1], "DOI не подтверждён последней страницей")
    source = prepare_source(ARTICLE_ID, text)
    require(source["references_excluded"], "Граница References не обнаружена")
    authored = build_authored(source, page_ranges)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    dependency_prompt = DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")
    artifacts = prepare_manual_map(ARTICLE_ID, text, source["sha256"], authored, prompt, dependency_prompt)
    base_run_id = artifacts["map.json"]["run_id"]
    run_id = str(uuid5(NAMESPACE_URL, f"codex-caracciolo2008-schema6-v1:{base_run_id}"))
    result = artifacts["map.json"]
    result["run_id"] = run_id
    result["article_title"] = TITLE
    result["builder_version"] = "codex-caracciolo2008-research-map-1"
    result["translations"]["ru"]["run_id"] = run_id
    graph = result["graph"]
    audit = audit_evidence_origin(graph)
    artifacts["empirical-evidence-eligibility.json"] = audit
    artifacts["validation.json"].update({
        "direct_evidence_eligible_blocks": audit["eligible_blocks"],
        "visible_dag": "passed", "model_calls": 0,
    })
    artifacts["source-review.json"] = {
        "article_id": ARTICLE_ID, "title": TITLE, "doi": DOI,
        "pdf_sha256": PDF_SHA256, "layout_sha256": LAYOUT_SHA256,
        "normalized_source_sha256": source["sha256"],
        "page_count": len(pages),
        "visually_reviewed_pdf_pages": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "tables_and_figures_checked": ["Figure 1", "Table 1", "Table 2", "Table 3", "Figure 2"],
        "references_excluded_from_extraction": True,
        "complete_semantic_coverage": False,
        "all_table_cells_formalized": False,
        "prior_source_exposure": True,
        "training_only": True,
        "expert_validated": False,
        "external_llm_calls": 0, "local_llm_calls": 0,
        "translation_llm_calls": 0, "embedding_calls": 0,
        "token_usage": None,
        "source_unit_count": len(source["units"]),
        "source_pages": [
            {"page": index + 1, "start": span[0], "end": span[1], "sha256": digest(pages[index])}
            for index, span in enumerate(page_ranges)
        ],
        "original_intake": intake,
    }
    knowledge_count = len(graph["knowledge"])
    statement_count = sum(len(item["semantic_frame"]["statements"]) for item in graph["knowledge"])
    report = [
        f"# {TITLE_RU}", "",
        f"DOI: {DOI}. PDF SHA-256: `{PDF_SHA256}`. Нормализованный полный текст: `{source['sha256']}`.",
        f"Подготовлено {knowledge_count} канонических знаний, {statement_count} утверждений, "
        f"{len(graph['transitions'])} обоснованных переходов и {len(source['units'])} единиц исходного текста.",
        "",
        "## Основное содержание карты", "",
        "В карту включены дизайн и знаменатели когорт, определения aMCI и OCIND, взаимное исключение исходов, "
        "девятилетнее наблюдение, смертность и пропуски, наблюдаемые и скорректированные частоты, "
        "возрастные оценки, сравнение с деменцией и ограничение множественной импутации.", "",
        "## Контроль источника", "",
        "Визуально проверены все девять страниц. Значения Figure 1, Tables 1–3 и Figure 2 сверены с изображениями PDF. "
        "References сохранены в исходном тексте и исключены из извлечения. Хеши PDF и извлечённой раскладки совпали "
        "с квитанцией; заголовок и DOI подтверждены непосредственно в PDF.", "",
        "## Ограничения и применение", "",
        "Это выборочная исследовательская карта, а не полная формализация статьи. Она подготовлена Codex; "
        "внешние и локальные LLM, переводчик, сетевые источники и эмбеддинги не вызывались. "
        "Научная экспертная проверка отсутствует. Статья была прочитана при предыдущем аудите, поэтому её можно "
        "использовать только для обучения или ретроспективной диагностики, но не как слепую контрольную статью.", "",
    ]
    artifacts["report.ru.md"] = "\n".join(report)
    artifacts["source.en.md"] = text
    artifacts["source.layout.txt"] = layout_path.read_text(encoding="utf-8")
    artifacts["source.pdf-provenance.json"] = {
        "path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "pdf_sha256": PDF_SHA256,
        "layout_path": str(layout_path.relative_to(ROOT)).replace("\\", "/"),
        "layout_sha256": LAYOUT_SHA256,
        "normalized_text_sha256": source["sha256"],
        "extraction_tool": "pypdfium2 through Poetry",
        "model_calls": 0,
    }
    output = OUTPUT_ROOT / run_id
    for name, value in artifacts.items():
        payload = value.encode("utf-8") if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        write_immutable(output / name, payload)
    print(json.dumps({
        "article_id": ARTICLE_ID, "run_id": run_id, "output": str(output),
        "knowledge": knowledge_count, "statements": statement_count,
        "transitions": len(graph["transitions"]), "depth": graph["analysis"]["depth"],
        "source_units": len(source["units"]), "references_excluded": source["references_excluded"],
        "model_calls": 0, "complete_semantic_coverage": False,
    }, ensure_ascii=False, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Ручная карта Caracciolo 2008 без модельных вызовов")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    require(args.root.resolve() == ROOT.resolve(), "Неожиданный корень рабочего пространства")
    write_run()


if __name__ == "__main__":
    main()
