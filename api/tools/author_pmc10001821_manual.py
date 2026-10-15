"""Собирает отдельную ручную карту AgeWell без сети и модельных вызовов."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import PROMPT_PATH, DEPENDENCY_PROMPT_PATH
from domain.article_maps import digest, prepare_source, require
from infrastructure.immutable_files import write_immutable


ARTICLE_ID = "PMC10001821"
DOI = "10.3390/ijerph20054034"
SOURCE_PATH = Path("eval/article_pipeline_gold/cases/pmc10001821/article.md")
OUTPUT_ROOT = Path("eval/whole_map_forecast/agewell-digital-coach-codex-map-v2/runs")


def build_authored(source: dict) -> dict:
    """Описывает дизайн, результаты, смешанные эффекты и ограничения статьи."""
    units = {unit["id"]: unit for unit in source["units"]}
    records: list[dict] = []

    def add(key: str, en: str, ru: str, predicate: str, unit_ids: list[str], roles: dict,
            *, attrs: dict | None = None, kind: str = "state", knowledge_type: str = "result",
            claims: list[dict] | None = None, logic: str = "single", conditions: list[str] | None = None,
            time: str | None = "Ten-week AgeWell pilot in 2021; measurements at baseline, week 5, and week 10",
            modality: str | None = None, quantifier: str | None = None, status: str | None = None,
            origin: str = "direct observation or analysis in the present study") -> None:
        require(all(uid in units for uid in unit_ids), f"Unknown source unit in {key}")
        values = {"study": "AgeWell digital-coach pilot", **roles}
        if knowledge_type in {"observation", "result", "comparison"}:
            values.setdefault("evidence_origin", origin)
        item = {
            "key": key, "en": en, "ru": ru, "predicate": predicate, "units": unit_ids,
            "roles": values, "attrs": attrs or {}, "kind": kind, "type": knowledge_type,
            "logic": logic, "time": time,
            "conditions": conditions or ["Small uncontrolled mixed-methods pilot; do not interpret as a causal treatment effect."],
            "modality": modality, "quantifier": quantifier,
        }
        if claims:
            item["claims"] = claims
        if kind == "action":
            item["status"] = status or "performed"
        records.append(item)

    add("healthy-ageing-dimensions",
        "The article frames healthy ageing around physical activity, mental well-being, and social participation during the transition from work to retirement.",
        "В статье здоровое старение при переходе от работы к пенсии рассматривается через физическую активность, психическое благополучие и социальное участие.",
        "healthy_ageing_dimensions", ["U9", "U10", "U11", "U12"],
        {"population": "older adults transitioning from work to retirement", "dimensions": "physical activity, mental well-being, and social participation"},
        knowledge_type="assertion", origin="conceptual framing and prior literature summarized by the authors")
    add("retirement-transition-evidence-gap",
        "The article reports a lack of consensus about how retirement transition affects physical activity and says evidence on digital coaching for healthy older adults near retirement is scarce.",
        "Авторы указывают, что влияние перехода к пенсии на физическую активность изучено неоднозначно, а данных о цифровом коучинге для здоровых людей старшего возраста около выхода на пенсию мало.",
        "retirement_effect_and_digital_coaching_evidence_remain_uncertain", ["U10", "U13"],
        {"transition": "work-to-retirement", "outcome": "physical activity and healthy-ageing behaviours", "approach": "digital health coaching"},
        knowledge_type="limitation", modality="uncertain", origin="literature gap stated by the authors")
    add("study-aims",
        "The study aimed to assess a digital coach’s effects on physical activity, mental well-being, socialization, and retirement transition, describe user experience, and identify system strengths and weaknesses.",
        "Цель исследования — оценить влияние цифрового коуча на физическую активность, психическое благополучие, социализацию и переход к пенсии, описать пользовательский опыт и определить сильные и слабые стороны системы.",
        "evaluate_digital_coach_and_user_experience", ["U6", "U13"],
        {"intervention": "AgeWell digital coach", "target_population": "adults near retirement", "outcomes": "physical activity, mental well-being, socialization, retirement transition, user experience"},
        kind="action", knowledge_type="goal", status="planned", modality="aimed to", origin="stated study aims")
    add("retirement-transition-context",
        "The authors describe population ageing and retirement as a transition that can create opportunities while disrupting meaningful relationships, daily routines, social roles, and identity.",
        "Авторы описывают старение населения и выход на пенсию как переход, который открывает новые возможности, но может нарушать значимые отношения, повседневный распорядок, социальные роли и самоидентичность.",
        "retirement_transition_can_change_daily_life_and_social_roles", ["U8", "U9", "U10", "U11"],
        {"population": "older adults approaching or entering retirement", "possible_changes": "relationships, routines, social roles, identity", "evidence_origin": "background literature summarized by the authors"},
        knowledge_type="assertion", modality="can", origin="background framing, not a result measured by the AgeWell pilot")
    add("study-ethics-and-consent",
        "Participants provided signed informed consent by email, and the organizations conducting the evaluations sought approval from their competent ethics committees.",
        "Участники подписали информированное согласие и отправили его по электронной почте; организации, проводившие оценку, запросили одобрение соответствующих этических комитетов.",
        "obtain_participant_consent_and_ethics_review", ["U39"],
        {"participants": "AgeWell trial participants", "consent": "signed informed-consent form returned by email", "ethics_review": "sought from competent committees"},
        kind="action", knowledge_type="method", status="performed")
    add("understudied-transition-population",
        "The authors present adults aged 55 years and older around retirement as an overlooked population for digital coaching aimed at healthy-ageing behaviours.",
        "Авторы представляют людей от 55 лет, находящихся около выхода на пенсию, как недостаточно изученную группу для цифрового коучинга здорового старения.",
        "digital_coaching_research_underrepresents_adults_near_retirement", ["U81"],
        {"population": "adults aged 55 years or older near retirement", "research_gap": "limited attention to this group in digital coaching", "evidence_origin": "novelty claim by the authors"},
        knowledge_type="assertion", modality="authors state", origin="authors' characterization of the research gap")
    add("system-functionality",
        "The AgeWell smartphone app offered four activity areas—physical activity, social life, emotional well-being, and good retirement—with goal setting, plans, reminders, motivational content, and user-centred co-design.",
        "Приложение AgeWell предлагало четыре области — физическую активность, социальную жизнь, эмоциональное благополучие и подготовку к пенсии — с постановкой целей, планами, напоминаниями, мотивационными материалами и человеко-ориентированным проектированием.",
        "digital_coach_provides_four_personal_development_areas", ["U16", "U21", "U22", "U23", "U24", "U25", "U26", "U27"],
        {"system": "AgeWell smartphone application", "areas": "physical activity, social life, emotional well-being, retirement preparation", "functions": "user-selected activities, weekly planning, personal goals, reminders, motivational content"},
        knowledge_type="method", conditions=["The described functions establish what the system offered; they do not establish that every participant used each function."])
    add("technical-implementation",
        "The trial used an avatar-based Android app with a server backend; the authors report secure communication and that personal data were not stored in cloud services or with third parties.",
        "В испытании использовали Android-приложение с аватаром и серверной частью; авторы сообщают о защищённом канале связи и хранении персональных данных вне облачных сервисов и сторонних организаций.",
        "implement_digital_coach_with_private_backend", ["U18"],
        {"system": "AgeWell digital coach", "client": "Android smartphone application", "backend": "project consortium server"},
        knowledge_type="method", origin="implementation description by the study authors")
    add("intervention-phases",
        "The ten-week intervention had two five-week phases: participants used the digital coach with two human coaches in Phase 1, then used it autonomously in Phase 2 while retaining limited remote contact for questions or technical issues.",
        "Десятинедельное вмешательство включало две пятинедельные фазы: в первой участникам помогали два человека-коуча, во второй они пользовались цифровой системой самостоятельно, сохраняя ограниченный удалённый канал для вопросов и технических проблем.",
        "deliver_two_phase_digital_coaching_with_different_human_support", ["U29", "U30", "U32", "U34"],
        {"intervention": "AgeWell digital coach", "phase_1": "weeks 1–5 with two human coaches", "phase_2": "weeks 6–10 autonomous use with remote help for questions or technical issues"},
        kind="action", knowledge_type="method", status="performed", attrs={"total_duration": {"value": 10, "unit": "weeks"}, "phase_duration": {"value": 5, "unit": "weeks"}, "human_coaches_in_phase_1": {"value": 2, "unit": "coaches"}},
        conditions=["Human support and intervention phase changed together; their effects cannot be separated by this design."])
    add("human-coach-support",
        "During the supported phase, human coaches trained participants, encouraged engagement, built confidence with the technology, and answered questions in group sessions.",
        "В поддерживаемой фазе люди-коучи обучали участников, поддерживали вовлечённость и уверенность в использовании технологии и отвечали на вопросы на групповых встречах.",
        "human_coaches_provide_training_motivation_and_technical_support", ["U30", "U32", "U42", "U43"],
        {"actors": "two human coaches", "recipients": "AgeWell pilot participants", "functions": "training, motivation, technology support, engagement"},
        kind="action", knowledge_type="method", status="performed")
    add("study-design-and-measurement",
        "This was a ten-week longitudinal mixed-methods pilot with quantitative questionnaires at baseline, week 5, and week 10 and qualitative group sessions at three points.",
        "Это было десятинедельное продольное пилотное исследование со смешанными методами: количественные анкеты собирали в начале, на пятой и десятой неделях, качественные групповые встречи проводили в три срока.",
        "measure_quantitative_and_qualitative_outcomes_over_three_times", ["U29", "U30", "U32", "U34", "U41", "U42"],
        {"design": "longitudinal mixed-methods pilot", "quantitative_times": "T0 baseline, T1 week 5, T2 week 10", "qualitative_sessions": "three online group sessions"},
        knowledge_type="method", attrs={"study_duration": {"value": 10, "unit": "weeks"}, "quantitative_measurement_times": {"value": 3, "unit": "time points"}, "group_sessions": {"value": 3, "unit": "sessions"}},
        conditions=["The study had no control group; T0/T1/T2 comparisons do not isolate intervention effects from time or other changes."])
    add("eligibility-and-recruitment",
        "Participants were eligible if aged at least 55, within three years before or after retirement, and self-described as physically and cognitively healthy; recruitment occurred in Italy and the Netherlands.",
        "Критерии участия: возраст от 55 лет, не более трёх лет до или после выхода на пенсию и самооценка физического и когнитивного здоровья; набор проводили в Италии и Нидерландах.",
        "recruit_healthy_adults_near_retirement", ["U36", "U38"],
        {"population": "adults transitioning from work to retirement", "setting": "Italy and the Netherlands"},
        knowledge_type="method", attrs={"minimum_age": {"value": 55, "unit": "years"}, "retirement_window": {"value": 3, "unit": "years before or after retirement"}, "planned_sample": {"value": 100, "unit": "participants"}},
        conditions=["Eligibility was broad and based on reported physical and cognitive health; it is not a clinical diagnosis of healthy ageing."])
    add("participant-flow-and-analysis-sample",
        "The first assessment included 91 people; 23 dropped out, and 62 met the analysis criteria of baseline plus at least one follow-up and more than three quarters of questionnaire items answered.",
        "Первичное обследование включало 91 человека; 23 выбыли, а критериям анализа соответствовали 62 участника: исходная анкета и хотя бы одно повторное обследование при заполнении более трёх четвертей анкеты.",
        "retain_eligible_questionnaire_records_for_analysis", ["U59", "U60", "U53"],
        {"initial_sample": "AgeWell pilot participants", "analysis_sample": "participants meeting repeated-questionnaire criteria"},
        knowledge_type="observation", attrs={"first_wave": {"value": 91, "unit": "participants"}, "dropouts": {"value": 23, "unit": "participants"}, "analysis_sample": {"value": 62, "unit": "participants"}, "Italy_analysis_sample": {"value": 34, "unit": "participants"}, "Netherlands_analysis_sample": {"value": 28, "unit": "participants"}},
        conditions=["The first-wave, dropout, and analysis denominators are distinct; 91 minus 23 is not the stated analysis sample."])
    add("analysis-sample-demographics",
        "Among the reported samples, 64.5% were male overall; national samples differed in sex, education, and marital composition, and retirees were 66.7% of the Italian and 60.7% of the Dutch sample.",
        "В описанной выборке 64,5% составляли мужчины; итальянская и нидерландская выборки различались по полу, образованию и семейному положению. Пенсионеры составляли 66,7% итальянской и 60,7% нидерландской выборки.",
        "pilot_sample_demographics_differed_between_countries", ["U61", "U62", "U63"],
        {"population": "AgeWell study participants", "country_groups": "Italy and the Netherlands", "country_composition": "different sex, education, marital status, and retirement proportions"},
        knowledge_type="observation", logic="partition", claims=[
            {"predicate": "sample_composition", "roles": {"group": "whole sample", "characteristic": "male", "time": "baseline/sample description"}, "attrs": {"value": {"value": 64.5, "unit": "%"}}},
            {"predicate": "sample_composition", "roles": {"group": "Italy sample", "characteristic": "female"}, "attrs": {"value": {"value": 55.9, "unit": "%"}}},
            {"predicate": "sample_composition", "roles": {"group": "Netherlands sample", "characteristic": "female"}, "attrs": {"value": {"value": 10.7, "unit": "%"}}},
            {"predicate": "sample_composition", "roles": {"group": "Italy sample", "characteristic": "married"}, "attrs": {"value": {"value": 67.6, "unit": "%"}}},
            {"predicate": "sample_composition", "roles": {"group": "Netherlands sample", "characteristic": "married"}, "attrs": {"value": {"value": 85.7, "unit": "%"}}},
            {"predicate": "education_composition", "roles": {"group": "Netherlands sample", "characteristic": "more than 13 years education"}, "attrs": {"value": {"value": 75, "unit": "%"}, "count": {"value": 21, "unit": "of 28 participants"}}},
            {"predicate": "retirement_composition", "roles": {"group": "Italy sample", "characteristic": "retired"}, "attrs": {"value": {"value": 66.7, "unit": "%"}}},
            {"predicate": "retirement_composition", "roles": {"group": "Netherlands sample", "characteristic": "retired"}, "attrs": {"value": {"value": 60.7, "unit": "%"}}},
        ],
        conditions=["Descriptive sample characteristics, not outcome effects or evidence of representativeness."])
    add("pandemic-protocol-context",
        "Because of COVID-19 restrictions, questionnaires and group meetings were conducted online, and questions about infection and perceived pandemic effects were added as potential confounders.",
        "Из-за ограничений COVID-19 анкеты и групповые встречи проводили онлайн; добавили вопросы об инфекции и субъективном влиянии пандемии как о потенциальных смешивающих факторах.",
        "adapt_study_protocol_to_covid_context", ["U33"],
        {"context": "COVID-19 restrictions during the 2021 trial", "protocol_changes": "online assessments and pandemic-related covariates"},
        knowledge_type="method", time="May–October 2021")
    add("outcome-measures",
        "The study used SF-12v2 for physical and mental health, IPAQ for physical activity, WHO-5 and GSE-6 for well-being and self-efficacy, LSNS-6 for socialization, and SUS and UEQ for system usability and user experience.",
        "В исследовании применяли SF-12v2 для физического и психического здоровья, IPAQ для активности, WHO-5 и GSE-6 для благополучия и самоэффективности, LSNS-6 для социализации, SUS и UEQ для удобства системы и пользовательского опыта.",
        "measure_health_behaviour_and_user_experience_domains", ["U44", "U45", "U46", "U47", "U48", "U49", "U50"],
        {"population": "AgeWell pilot participants", "measures": "SF-12v2, IPAQ, WHO-5, GSE-6, LSNS-6, SUS, UEQ"},
        knowledge_type="method", logic="partition", claims=[
            {"predicate": "measures", "roles": {"instrument": "SF-12v2", "constructs": "physical and mental health", "score_direction": "higher is better"}, "attrs": {"score_range": {"value": "0–100", "unit": None}}},
            {"predicate": "measures", "roles": {"instrument": "IPAQ", "construct": "weekly physical activity level", "categories": "low, medium, high"}},
            {"predicate": "measures", "roles": {"instrument": "WHO-5", "construct": "well-being", "score_direction": "higher is better"}, "attrs": {"score_range": {"value": "0–25", "unit": None}}},
            {"predicate": "measures", "roles": {"instrument": "GSE-6", "construct": "self-efficacy", "score_direction": "higher is more self-efficacy"}, "attrs": {"score_range": {"value": "5–25", "unit": None}}},
            {"predicate": "measures", "roles": {"instrument": "LSNS-6", "construct": "social inclusion", "score_direction": "higher is greater inclusion"}, "attrs": {"score_range": {"value": "0–30", "unit": None}, "social-isolation-cutoff": {"value": "<12", "unit": "points"}}},
            {"predicate": "measures", "roles": {"instrument": "SUS and UEQ", "construct": "system usability and user experience"}},
        ],
        conditions=["The scale definitions are measurement conventions; they do not themselves show that the intervention changed an outcome."])
    add("analysis-methods",
        "Quantitative outcomes were compared across countries and between T0/T1 and T1/T2 using chi-square tests or Student’s t-tests; qualitative responses were coded and organized thematically by a framework-analysis process.",
        "Количественные исходы сравнивали между странами и между T0/T1 и T1/T2 с помощью χ² или t-критерия Стьюдента; качественные ответы кодировали и тематически организовывали методом рамочного анализа.",
        "analyze_pilot_quantitative_and_qualitative_data", ["U51", "U53", "U54", "U55", "U56"],
        {"quantitative_analysis": "country and within-participant time comparisons", "qualitative_analysis": "framework analysis of group-session transcripts"},
        kind="action", knowledge_type="method", status="performed", attrs={"significance_threshold": {"value": 0.05, "unit": "p-value"}},
        conditions=["Analyses used only participants with baseline and at least one follow-up and more than 75% questionnaire completion."])

    add("physical-activity-result",
        "Physical activity increased from baseline to week 5 (p=0.012) and was reported as stable from week 5 to week 10; the low-activity share fell from 8.2% to 6.0% during coach-supported use and rose to 8.3% during autonomous use.",
        "Физическая активность выросла от исходного уровня до пятой недели (p=0,012) и далее описана как стабильная до десятой недели; доля низкой активности снизилась с 8,2% до 6,0% при поддержке коуча и выросла до 8,3% при самостоятельном использовании.",
        "physical_activity_change_across_supported_and_autonomous_phases", ["U6", "U66", "U83", "U95"],
        {"intervention": "AgeWell digital coach", "outcome": "IPAQ physical activity", "period_1": "T0 to T1 with human-coach support", "period_2": "T1 to T2 autonomous use"},
        knowledge_type="comparison", logic="contrast", attrs={"T0_to_T1_p": {"value": 0.012, "unit": None}, "low_activity_T0": {"value": 8.2, "unit": "%"}, "low_activity_T1": {"value": 6.0, "unit": "%"}, "low_activity_T2": {"value": 8.3, "unit": "%"}},
        claims=[
            {"predicate": "physical_activity_increased", "roles": {"population": "AgeWell analysis participants", "outcome": "IPAQ physical activity"}, "attrs": {"p_value": {"value": 0.012, "unit": None}}, "time": "T0 to T1; first five weeks with human-coach support"},
            {"predicate": "physical_activity_remained_stable_as_reported", "roles": {"population": "AgeWell analysis participants", "outcome": "IPAQ physical activity"}, "time": "T1 to T2; second five weeks of autonomous app use"},
            {"predicate": "low_activity_share_changed", "roles": {"population": "AgeWell analysis participants", "outcome": "low IPAQ activity category"}, "attrs": {"T0": {"value": 8.2, "unit": "%"}, "T1": {"value": 6.0, "unit": "%"}, "T2": {"value": 8.3, "unit": "%"}}, "time": "T0 baseline, T1 week 5, T2 week 10"},
        ],
        conditions=["Uncontrolled pre/post pilot; the supported phase also included human coaching, so the digital app’s independent effect is not identified."])
    add("wellbeing-self-efficacy-result",
        "WHO-5 well-being and GSE-6 self-efficacy rose slightly from T0 to T1 and then fell from T1 to T2; the authors separately report significant pre/post differences in SF-12 physical and mental scale scores (p=0.002 and p<0.001), without giving their direction in this passage.",
        "Показатели WHO-5 и GSE-6 немного выросли от T0 к T1, затем снизились от T1 к T2; отдельно авторы сообщают о значимых различиях физических и психических шкал SF-12 до и после вмешательства (p=0,002 и p<0,001), но в этом фрагменте не указывают направление различий.",
        "wellbeing_and_self_efficacy_show_phase_dependent_changes", ["U6", "U65", "U67", "U83", "U95"],
        {"intervention": "AgeWell digital coach with changing human support", "outcomes": "WHO-5, GSE-6, SF-12 PCS and MCS"},
        knowledge_type="comparison", logic="contrast", attrs={"reported_pre_post_p_physical": {"value": 0.002, "unit": None}, "reported_pre_post_p_mental": {"value": "<0.001", "unit": None}},
        claims=[
            {"predicate": "increased_then_decreased", "roles": {"outcome": "WHO-5 mental well-being and GSE-6 self-efficacy"}, "time": "slight increase T0 to T1, then decrease T1 to T2"},
            {"predicate": "pre_post_score_difference_reported", "roles": {"outcome": "SF-12 physical and mental scale scores"}, "attrs": {"physical_p": {"value": 0.002, "unit": "p-value"}, "mental_p": {"value": "<0.001", "unit": "p-value"}}, "direction": "not specified in this passage"},
        ],
        conditions=["P values concern SF-12 scale scores; they do not specify direction or magnitude here and must not be conflated with threshold proportions reported separately.", "Uncontrolled pilot; no causal effect estimate."])
    add("socialization-result",
        "Measured socialization decreased significantly from T0 to T1 and increased from T1 to T2; the authors describe socialization as having worsened over the trial overall.",
        "Измеренная социализация значимо снизилась от T0 к T1 и выросла от T1 к T2; авторы в целом описывают её как ухудшившуюся в ходе испытания.",
        "socialization_changed_nonmonotonically_and_overall_worsened", ["U6", "U67", "U84", "U95"],
        {"intervention": "AgeWell digital coach and online group contacts", "outcome": "LSNS-6 socialization or social inclusion"},
        knowledge_type="comparison", logic="contrast", conditions=["The online context occurred during COVID-19 restrictions; the uncontrolled design cannot identify why the score changed."])
    add("physical-health-threshold-result",
        "The share of participants with SF-12 PCS≤50 rose from 19.6% at T0 to 30.6% at T2, while the share with SF-12 MCS≤42 was 14.3% at both times.",
        "Доля участников с SF-12 PCS≤50 выросла с 19,6% на T0 до 30,6% на T2, а доля с SF-12 MCS≤42 составляла 14,3% в оба срока.",
        "sf12_threshold_proportions_and_prepost_test_reported", ["U65"],
        {"intervention": "AgeWell digital coaching pilot", "outcomes": "SF-12 PCS and MCS threshold categories"},
        knowledge_type="comparison", logic="contrast", attrs={"PCS_T0": {"value": 19.6, "unit": "%"}, "PCS_T2": {"value": 30.6, "unit": "%"}, "MCS_T0": {"value": 14.3, "unit": "%"}, "MCS_T2": {"value": 14.3, "unit": "%"}},
        conditions=["These threshold proportions are distinct from the pre/post tests of continuous scale scores; no direction for the latter is inferred here."])
    add("usability-result",
        "User ratings were poor on five of six UEQ dimensions, only perspicuity was positive, novelty was not recognized, and the SUS score was 59 versus the reference average of 68.",
        "Пользователи низко оценили пять из шести измерений UEQ; положительным было только понятность, новизны они не отмечали, а SUS составил 59 при среднем ориентире 68.",
        "user_experience_and_usability_were_unfavourable", ["U69", "U70", "U86", "U92"],
        {"system": "AgeWell digital coach", "outcomes": "UEQ dimensions and System Usability Scale"},
        knowledge_type="result", attrs={"SUS_score": {"value": 59, "unit": "points"}, "SUS_reference_average": {"value": 68, "unit": "points"}, "positive_UEQ_dimensions": {"value": 1, "unit": "of 6"}},
        conditions=["User-reported usability and experience outcomes; they are distinct from health outcomes."])
    add("perceived-usefulness-result",
        "Fewer than half of participants considered the coach useful for several dimensions by week 10; perceived usefulness for free-time enrichment and mental well-being declined, while usefulness for retirement transition rose from 50% to 54.2%.",
        "К десятой неделе менее половины участников считали коуч полезным для нескольких направлений; полезность для досуга и психического благополучия снизилась, а для перехода к пенсии выросла с 50% до 54,2%.",
        "perceived_usefulness_varied_by_goal_and_time", ["U71", "U88"],
        {"system": "AgeWell digital coach", "outcomes": "perceived usefulness by healthy-ageing dimension"},
        knowledge_type="comparison", logic="contrast", attrs={"retirement_usefulness_T1": {"value": 50.0, "unit": "%"}, "retirement_usefulness_T2": {"value": 54.2, "unit": "%"}, "free_time_change": {"value": -13.1, "unit": "percentage points"}, "mental_wellbeing_change": {"value": -11.4, "unit": "percentage points"}},
        conditions=["Perceived usefulness is not an objective health outcome or a measure of adherence."])
    add("qualitative-strengths",
        "Participants described the coach as motivating physical activity, reminding them about activities, helping them focus on personal needs, inspiring mental-well-being activities, and supporting retirement preparation; videos were viewed as useful and motivating.",
        "Участники говорили, что коуч мотивировал к физической активности, напоминал о занятиях, помогал сосредоточиться на личных потребностях, вдохновлял на упражнения для благополучия и поддерживал подготовку к пенсии; видео считали полезными и мотивирующими.",
        "participants_reported_content_and_video_strengths", ["U73", "U74", "U76"],
        {"system": "AgeWell digital coach", "evidence": "participants’ qualitative reports", "reported_strengths": "motivation, reminders, reflective activities, videos"},
        knowledge_type="observation", conditions=["Qualitative participant reports illustrate perceived strengths; they do not estimate efficacy or prevalence."])
    add("content-weaknesses",
        "Participants reported that some activities were too demanding, the app was rigid and insufficiently customizable, and frequent performance reporting felt pressuring.",
        "Участники сообщали, что некоторые занятия были слишком тяжёлыми, приложение было жёстким и недостаточно настраиваемым, а частая отчётность о выполнении создавала давление.",
        "participants_reported_content_and_autonomy_barriers", ["U75", "U77", "U86"],
        {"system": "AgeWell digital coach", "evidence": "qualitative user feedback", "barriers": "activity fit, inflexibility, reporting burden"},
        knowledge_type="observation", conditions=["Qualitative feedback from a small pilot; not a population prevalence estimate."])
    add("technical-weaknesses",
        "Users reported problems logging or changing activities, slow loading, unintuitive navigation, unclear activity graphs, a rigid daily plan, and an avatar they found repetitive or unpleasant.",
        "Пользователи сообщали о трудностях регистрации и изменения занятий, медленной загрузке, неинтуитивной навигации, непонятных графиках, жёстком дневном плане и повторяющемся или неприятном аватаре.",
        "participants_reported_technical_and_interaction_problems", ["U77", "U86", "U87", "U89"],
        {"system": "AgeWell digital coach", "evidence": "qualitative user feedback", "issues": "recording activities, loading, navigation, planning, avatar interaction"},
        knowledge_type="observation", conditions=["Qualitative feedback; the study did not experimentally isolate each technical issue’s contribution to health outcomes."])
    add("user-improvement-suggestions",
        "Participants suggested more personalizable activities and schedules, periodic human-coach meetings, explanations of each activity’s purpose, more intuitive interaction, videos, and links to a phone calendar.",
        "Участники предлагали лучше настраивать занятия и расписания, проводить периодические встречи с человеком-коучем, объяснять пользу каждого занятия, упростить интерфейс, добавить видео и связать план со смартфонным календарём.",
        "users_proposed_personalization_human_support_and_interface_changes", ["U78", "U79", "U87"],
        {"system": "future digital coach", "evidence": "participant suggestions", "proposed_changes": "personalization, human contact, rationale, usability, video, calendar integration"},
        knowledge_type="goal", modality="recommended", conditions=["These are proposed changes, not interventions tested in the present study."])
    add("phase-dependent-support-interpretation",
        "The authors interpret the persistence of physical-activity change but not mental well-being or self-efficacy after human support ended as a possible indication that human coaching remained important for mid-term outcomes in those domains.",
        "Авторы трактуют сохранение изменений физической активности при отсутствии устойчивых изменений психического благополучия и самоэффективности после прекращения поддержки как возможный признак важности человеческого коучинга для среднесрочных результатов в этих областях.",
        "human_support_may_matter_for_persistence_of_some_outcomes", ["U83", "U92", "U95"],
        {"supported_period": "first five weeks with human coaches", "autonomous_period": "second five weeks", "outcomes": "physical activity, mental well-being, self-efficacy"},
        knowledge_type="conclusion", modality="may", logic="contrast", conditions=["Human support and time period co-varied; the design cannot attribute phase differences solely to the human coach or to the digital system."])
    add("socialization-interpretation",
        "The authors suggest that online contact during COVID-19 restrictions may not have improved social ties because virtual interaction was less satisfying than in-person contact.",
        "Авторы предполагают, что онлайн-контакты во время ограничений COVID-19 могли не улучшить социальные связи, поскольку виртуальное общение было менее удовлетворительным, чем личное.",
        "virtual_contact_may_not_improve_perceived_social_ties", ["U84", "U85"],
        {"context": "COVID-19 restrictions and online group meetings", "outcome": "perceived social ties", "candidate_factor": "virtual rather than in-person contact"},
        knowledge_type="conclusion", modality="may", conditions=["Authors’ interpretation; interaction mode was not randomized and causal mechanism was not tested."])
    add("causal-and-generalization-limitation",
        "The authors state that the small sample, attrition, lack of a control group, short trial, pandemic context, and recruitment difficulties prevent generalization and limit conclusions about effectiveness.",
        "Авторы указывают, что небольшая выборка, выбывание, отсутствие контрольной группы, короткое наблюдение, пандемический контекст и сложности набора ограничивают обобщение и выводы об эффективности.",
        "study_design_limits_causal_effectiveness_and_generalization", ["U91", "U92", "U93"],
        {"study": "AgeWell digital-coach pilot", "limitations": "small sample, attrition, no control, short duration, COVID-19 context"},
        knowledge_type="limitation", conditions=["The observed pre/post changes cannot establish that the digital coach caused the changes."])
    add("future-effectiveness-study",
        "The authors call for larger studies to assess digital coaching effectiveness and recommend tailoring the system to users’ physical, cognitive, and social status.",
        "Авторы призывают провести более крупные исследования эффективности цифрового коучинга и адаптировать систему к физическому, когнитивному и социальному состоянию пользователей.",
        "conduct_larger_tailored_effectiveness_studies", ["U87", "U89", "U93", "U95"],
        {"future_population": "older adults near retirement", "system_requirements": "flexible, attractive, personalized, appropriate to physical, cognitive, and social status"},
        kind="action", knowledge_type="goal", status="unresolved", modality="needed", conditions=["Future research task; not an action completed by this pilot."])
    add("mixed-effect-conclusion",
        "The article concludes that digital coaching may support healthy ageing, especially physical activity, while mental well-being and socialization remained difficult to improve and may require human support; system flexibility, attractiveness, and personalization were identified as needs.",
        "Авторы заключают, что цифровой коучинг может поддерживать здоровое старение, особенно физическую активность, тогда как психическое благополучие и социализацию улучшать сложнее и для них может требоваться человеческая поддержка; необходимы гибкость, привлекательность и персонализация системы.",
        "digital_coaching_has_mixed_dimension_specific_pilot_outcomes", ["U6", "U83", "U84", "U92", "U95"],
        {"intervention": "AgeWell digital coach", "population": "older adults transitioning to retirement", "dimensions": "physical activity, mental well-being, socialization"},
        knowledge_type="conclusion", logic="contrast", modality="may", conditions=["Qualified author conclusion from a small uncontrolled pilot; no overall success label or causal claim is justified."])

    represented = {uid for item in records for uid in item["units"]}
    headings = {"U1", "U5", "U7", "U14", "U15", "U28", "U35", "U40", "U52", "U57", "U58", "U64", "U68", "U72", "U80", "U82", "U90", "U94"}
    figures = {"U17", "U19", "U20", "U31", "U37"}
    excluded = {uid: "Heading organizes the article; the adjacent substantive paragraphs carry the content." for uid in headings}
    excluded.update({uid: "Figure caption retained in the source; the image itself was not available for quantitative reconstruction." for uid in figures})
    excluded.update({
        "U2": "Author metadata is retained in the full source, not modeled as scientific knowledge.",
        "U3": "Journal and year are retained as source metadata.",
        "U4": "DOI is retained as source metadata, not modeled as scientific knowledge.",
    })
    require(represented.isdisjoint(excluded), "A source unit is both represented and excluded")
    missing = set(units) - represented - set(excluded)
    require(not missing, f"Every non-reference source unit needs coverage accounting; missing={sorted(missing)}")
    transitions = [
        {"sources": ["system-functionality", "human-coach-support"], "target": "intervention-phases", "usage": "method", "reason": "The intervention phases combine the delivered digital system with explicitly different human-support conditions.", "units": ["U16", "U29", "U30"]},
        {"sources": ["eligibility-and-recruitment", "participant-flow-and-analysis-sample", "study-design-and-measurement"], "target": "physical-activity-result", "usage": "data", "reason": "The participant eligibility, analysis sample, measurement schedule, and physical-activity outcome define the reported T0/T1/T2 comparisons.", "units": ["U36", "U53", "U60", "U66"]},
        {"sources": ["intervention-phases", "outcome-measures", "analysis-methods"], "target": "physical-activity-result", "usage": "result", "reason": "The five-week support phases and IPAQ measurement are the design and outcome used for the physical-activity comparison.", "units": ["U30", "U44", "U46", "U53", "U66"]},
        {"sources": ["intervention-phases", "outcome-measures", "analysis-methods"], "target": "wellbeing-self-efficacy-result", "usage": "result", "reason": "The reported well-being and self-efficacy changes are comparisons of the specified scales across supported and autonomous periods.", "units": ["U30", "U44", "U47", "U48", "U53", "U65", "U67"]},
        {"sources": ["intervention-phases", "outcome-measures", "analysis-methods", "pandemic-protocol-context"], "target": "socialization-result", "usage": "result", "reason": "The time comparisons use the social-network outcome under online pandemic-era study conditions.", "units": ["U30", "U33", "U49", "U53", "U67"]},
        {"sources": ["outcome-measures", "analysis-methods"], "target": "usability-result", "usage": "result", "reason": "SUS and UEQ are the stated measures for the user-experience results.", "units": ["U50", "U53", "U69", "U70"]},
        {"sources": ["intervention-phases", "physical-activity-result", "wellbeing-self-efficacy-result", "causal-and-generalization-limitation"], "target": "phase-dependent-support-interpretation", "usage": "result", "reason": "The discussion interprets the distinct changes across supported and autonomous periods while the study-design limitations prevent isolating the cause.", "units": ["U30", "U65", "U66", "U67", "U83", "U92"]},
        {"sources": ["socialization-result", "pandemic-protocol-context", "qualitative-strengths"], "target": "socialization-interpretation", "usage": "evidence", "reason": "The authors relate the measured socialization pattern to online contact and participant reports, without treating this interpretation as a tested causal mechanism.", "units": ["U33", "U67", "U74", "U84"]},
        {"sources": ["qualitative-strengths", "content-weaknesses", "technical-weaknesses", "user-improvement-suggestions", "usability-result"], "target": "future-effectiveness-study", "usage": "condition", "reason": "The proposed future evaluation and tailoring respond to the reported strengths, content barriers, technical problems, and low user-experience scores.", "units": ["U69", "U70", "U74", "U75", "U77", "U78", "U79", "U87", "U93"]},
        {"sources": ["physical-activity-result", "wellbeing-self-efficacy-result", "socialization-result", "usability-result", "causal-and-generalization-limitation"], "target": "mixed-effect-conclusion", "usage": "result", "reason": "The conclusion synthesizes outcome-specific positive, negative, and uncertain findings under the stated pilot limitations.", "units": ["U65", "U66", "U67", "U69", "U70", "U83", "U84", "U92", "U95"]},
    ]
    return {
        "version": "pmc10001821-codex-manual-map-v2",
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "knowledge": records,
        "transitions": transitions,
        "excluded_units": excluded,
        "source_limitations": [
            "Карта вручную построена из полного сохранённого английского Markdown; раздел References сохранён в источнике, но исключён из извлечения.",
            "Таблицы и графики в Markdown не представлены как полные структурированные данные; использованы только числа, явно приведённые в прозе и подписях.",
            "Доля выбывших и конечная аналитическая выборка имеют разные знаменатели; карта не пересчитывает и не исправляет их.",
            "Пилот малый, без контрольной группы и с изменением человеческой поддержки между фазами; результаты не идентифицируют причинный эффект приложения.",
            "Экспертная научная проверка не проводилась; модельные вызовы и расход токенов равны нулю/не применимы.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source_path = root / SOURCE_PATH
    text = source_path.read_text(encoding="utf-8")
    source_hash = digest(text)
    expected_hash = "6aa007f870725b89840ea397dea6fd12237ea4f0624b9d2b80de14b9c407051d"
    require(source_hash == expected_hash, "PMC10001821 source revision changed; refusing to author against a different text")
    source = prepare_source(ARTICLE_ID, text)
    require(source["references_excluded"] and source["offset_encoding"] == "unicode_codepoints", "Source boundary or offset encoding invalid")
    authored = build_authored(source)
    prompts = (PROMPT_PATH.read_text(encoding="utf-8"), DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8"))
    artifacts = prepare_manual_map(ARTICLE_ID, text, source_hash, authored, *prompts)
    graph = artifacts["map.json"]["graph"]
    require(len(artifacts["coverage.json"]["units"]) == len(source["units"]), "Coverage accounting incomplete")
    artifacts["map.json"]["article_title"] = "The Impact of Digital Coaching Intervention for Improving Healthy Ageing Dimensions among Older Adults during Their Transition from Work to Retirement"
    artifacts["source-review.json"] = {
        "article_id": ARTICLE_ID, "doi": DOI, "source_sha256": source_hash,
        "full_text_reviewed": True, "source_units": len(source["units"]),
        "references_excluded_from_extraction": True, "offset_encoding": "unicode_codepoints",
        "complete_semantic_coverage": False, "tables_exhaustively_formalized": False,
        "expert_validated": False, "author": "Codex", "generation_method": "manual_from_full_english_text",
        "external_llm_calls": 0, "local_llm_calls": 0, "translation_llm_calls": 0, "embedding_calls": 0,
        "token_usage": None,
    }
    artifacts["validation.json"].update({"doi": DOI, "source_sha256": source_hash,
        "external_llm_calls": 0, "local_llm_calls": 0, "translation_llm_calls": 0,
        "embedding_calls": 0, "scientific_accuracy": "not_assessed"})
    artifacts["report.ru.md"] = "\n".join([
        "# PMC10001821: карта пилотного вмешательства AgeWell",
        "",
        f"**DOI:** `{DOI}`  ",
        f"**SHA-256 источника:** `{source_hash}`  ",
        f"**Запуск:** `{artifacts['map.json']['run_id']}`  ",
        f"**Схема:** 6; **промпты:** KM.TEXT_TO_MAP 4 и зависимости 16; **знаний:** {len(graph['knowledge'])}; **утверждений:** {graph['analysis']['statement_count']}; **переходов:** {len(graph['transitions'])}; **глубина DAG:** {graph['analysis']['depth']}",
        "",
        "Карта создана вручную Codex по полному английскому тексту. Внешние и локальные LLM, переводчик, эмбеддинги, сеть и Neo4j не использовались. Расход токенов Codex неизвестен и не оценивался.",
        "",
        "## Что показывает этот источник",
        "",
        "В одной статье наблюдаются разные результаты по отдельным измерениям и временным фазам: физическая активность улучшилась в первые пять недель и затем описана как стабильная; благополучие и самоэффективность после небольшого начального роста снизились; социализация сначала ухудшилась, затем частично восстановилась. При этом переход от поддержки человека-коуча к самостоятельному использованию совпал со сменой фаз, поэтому причина различий не установлена.",
        "",
        "Удобство и пользовательский опыт оценены плохо; качественные отзывы указывают на жёсткое расписание, слабую настройку и технические проблемы. Это позволяет отделить исходы здоровья от принятия системы и её реализации. Статья не имеет контрольной группы, выборка мала, выбывание и пандемический контекст ограничивают переносимость выводов.",
        "",
        "## Ограничения карты",
        "",
        f"Покрыты все {len(source['units'])} фрагментов до References: каждый связан со знанием или имеет причину исключения. Семантическая полнота и исчерпывающее извлечение табличных данных не заявлены; рисунки не реконструировались по отсутствующим изображениям. Слова «успех» и «неуспех» не назначаются статье целиком: результат зависит от целевого измерения и временного окна. Научная точность требует экспертной проверки.",
        "",
        "Эта карта пригодна как один источник для диагностики подграфов «условия реализации → действие → измеренный исход», но не как независимое подтверждение и не как доказательство эффективности цифрового коучинга.",
        "",
    ])
    artifacts["manifest.json"] = {
        "schema_version": 1, "pmc_id": ARTICLE_ID, "doi": DOI,
        "article_id": artifacts["map.json"]["article_id"], "run_id": artifacts["map.json"]["run_id"],
        "source_sha256": source_hash,
        "prompt_binding": {"prompt": artifacts["map.json"]["prompt"], "dependency_prompt": artifacts["map.json"]["dependency_prompt"]},
        "generation": artifacts["map.json"]["generation"], "needs_expert_review": True,
        "eligible_as_independent_confirmation": False,
        "files": {name: sha256(value if isinstance(value, bytes) else value.encode("utf-8") if isinstance(value, str)
                                else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")).hexdigest()
                  for name, value in artifacts.items()},
    }
    output = root / OUTPUT_ROOT / artifacts["map.json"]["run_id"]
    for name, value in artifacts.items():
        payload = value if isinstance(value, bytes) else value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        write_immutable(output / name, payload)
    print(output)
    print(json.dumps({"run_id": artifacts["map.json"]["run_id"], "knowledge": len(graph["knowledge"]),
                      "statements": graph["analysis"]["statement_count"], "transitions": len(graph["transitions"]),
                      "depth": graph["analysis"]["depth"], "isolated": graph["analysis"]["isolated_count"],
                      "source_units": len(source["units"]), "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
