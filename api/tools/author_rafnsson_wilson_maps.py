"""Готовит вручную проверенные карты двух когортных статей без вызова моделей."""
from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(r"D:\Knowledge_Map")
sys.path.insert(0, str(ROOT / "api"))

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import DEPENDENCY_PROMPT_PATH, PROMPT_PATH
from domain.article_maps import digest, require
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


SOURCE_ROOT = ROOT / "eval/question_prediction/il6-plasma-global-v1/empirical-fulltext-continuation-v1/sources"
OUTPUT_ROOT = ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs"
PROMPT_EXTRACTION = PROMPT_PATH.read_text(encoding="utf-8")
PROMPT_DEPENDENCIES = DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")

SOURCES = {
    "rafnsson2007": {
        "doi": "10.1111/j.1532-5415.2007.01158.x",
        "family": "edinburgh-artery-study",
        "pdf_sha256": "4242db33ad8e4c045c092c3108ae2ceee2eb1fda42c094fb2a221c225010b538",
        "text_sha256": "bd795ef1e620ac8076a1114df8c59d7de78825b0714b0f9b6a080dc624c1d12f",
        "title": "Cognitive Decline and Markers of Inflammation and Hemostasis: The Edinburgh Artery Study",
        "title_ru": "Когнитивное снижение и маркеры воспаления и гемостаза: Edinburgh Artery Study",
        "visual_pages": [2, 4, 5, 6],
        "table_pages": [5, 6],
        "knowledge": [
            {"key":"aim","en":"The study aimed to assess whether circulating inflammatory and hemostatic markers were associated with cognitive performance and decline in older people.","ru":"Цель исследования — оценить, связаны ли циркулирующие маркеры воспаления и гемостаза с когнитивными показателями и их снижением у пожилых людей.","predicate":"aims to assess biomarker associations with cognitive decline","units":["U1","U2"],"roles":{"study":"Edinburgh Artery Study","exposure":"circulating inflammatory and hemostatic markers","outcome":"cognitive performance and decline","population":"older people"},"type":"goal","conditions":["This is the study objective, not an observed result."]},
            {"key":"cohort","en":"The Edinburgh Artery Study recruited 1,592 adults aged 55–74 in 1987/88 from 11 general practices in Edinburgh; the cohort included 809 men and 783 women.","ru":"В 1987/88 году Edinburgh Artery Study набрала 1 592 человека 55–74 лет из 11 врачебных практик Эдинбурга: 809 мужчин и 783 женщины.","predicate":"recruited a population-based cohort","units":["U2"],"roles":{"study":"Edinburgh Artery Study","participants":"cohort members","setting":"11 general practices in Edinburgh"},"type":"observation","attrs":{"recruited_n":{"value":1592,"unit":"participants"},"age_low":{"value":55,"unit":"years"},"age_high":{"value":74,"unit":"years"},"men":{"value":809,"unit":"participants"},"women":{"value":783,"unit":"participants"}},"time":"1987/88"},
            {"key":"assessment-timeline","en":"Plasma biomarkers were measured in 1987/88; cognitive testing was conducted in 1998/99 and again in 2002/03, four years later.","ru":"Плазменные биомаркеры измеряли в 1987/88 году; когнитивное тестирование проводили в 1998/99 и повторно в 2002/03 году, через четыре года.","predicate":"measured biomarkers before two cognitive assessments","units":["U1","U2","U3"],"roles":{"biomarker_measurement":"plasma biomarkers","first_assessment":"cognitive testing in 1998/99","second_assessment":"cognitive testing in 2002/03"},"type":"method","attrs":{"interval":{"value":4,"unit":"years"}},"time":"Biomarkers in 1987/88; cognition in 1998/99 and 2002/03"},
            {"key":"tested-sample","en":"Of 1,103 people invited to the first cognitive assessment, 717 were tested; 452 were tested in 2002/03. Participants tested in 2002/03 had somewhat more favorable baseline characteristics than the surviving target sample.","ru":"Из 1 103 приглашённых на первое когнитивное обследование протестировали 717 человек; в 2002/03 году — 452. У прошедших обследование в 2002/03 году исходные характеристики были несколько благоприятнее, чем у выжившей целевой выборки.","predicate":"retained a selected sample for repeated cognitive testing","units":["U2","U3","U4"],"roles":{"invited_first_round":"eligible participants","tested_first_round":"participants tested in 1998/99","tested_second_round":"participants tested in 2002/03","selection":"tested sample"},"type":"observation","attrs":{"first_round_invited":{"value":1103,"unit":"participants"},"first_round_tested":{"value":717,"unit":"participants"},"second_round_tested":{"value":452,"unit":"participants"}},"conditions":["The 2002/03 sample had modestly higher education and socioeconomic position and somewhat more favorable health and lifestyle profiles; selective attrition can limit generalization."]},
            {"key":"cognitive-measures","en":"Cognition was assessed with Logical Memory, Raven’s Standard Progressive Matrices, Verbal Fluency, Digit Symbol-Coding, and a general cognitive factor; the National Adult Reading Test was used to estimate peak prior ability.","ru":"Когнитивные функции оценивали тестами Logical Memory, матрицами Равена, беглостью речи, Digit Symbol-Coding и общим когнитивным фактором; National Adult Reading Test использовали как оценку пиковых прежних способностей.","predicate":"assessed several cognitive domains and estimated prior peak ability","units":["U1","U2","U3","U4"],"roles":{"cognition":"older participants’ cognitive performance","memory_measure":"Logical Memory Test","reasoning_measure":"Raven’s Standard Progressive Matrices","fluency_measure":"Verbal Fluency Test","speed_measure":"Digit Symbol-Coding Test","prior_ability_measure":"National Adult Reading Test"},"type":"method","conditions":["The general cognitive factor was the first unrotated principal component of the four cognitive tests and accounted for 57.1% of variance."]},
            {"key":"biomarker-measures","en":"Baseline plasma markers included fibrinogen, D-dimer, CRP, IL-6, ICAM-1, VCAM-1, and E-selectin; assay procedures and reliability varied by marker.","ru":"Исходные плазменные маркеры включали фибриноген, D-димер, CRP, IL-6, ICAM-1, VCAM-1 и E-selectin; методы анализа и их надёжность различались по маркерам.","predicate":"measured baseline inflammatory and hemostatic markers","units":["U2","U3"],"roles":{"exposure":"baseline plasma markers","marker_1":"fibrinogen","marker_2":"D-dimer","marker_3":"C-reactive protein","marker_4":"interleukin-6","marker_5":"ICAM-1","marker_6":"VCAM-1","marker_7":"E-selectin"},"type":"method","time":"Baseline 1987/88"},
            {"key":"four-year-score-change","en":"Between 1998/99 and 2002/03, mean scores declined on Raven’s Matrices, Verbal Fluency, and Digit Symbol-Coding, while mean Logical Memory performance increased.","ru":"Между 1998/99 и 2002/03 годами средние показатели снизились по матрицам Равена, беглости речи и Digit Symbol-Coding, тогда как средний результат Logical Memory вырос.","predicate":"showed domain-specific mean score changes over four years","units":["U4"],"roles":{"participants":"participants with complete repeated test data","reasoning":"Raven’s Matrices score","fluency":"Verbal Fluency score","processing_speed":"Digit Symbol-Coding score","memory":"Logical Memory score"},"type":"result","logic":"contrast","attrs":{"reasoning_mean_change":{"value":-2.18,"unit":"test-score points"},"fluency_mean_change":{"value":-1.80,"unit":"test-score points"},"processing_speed_mean_change":{"value":-4.84,"unit":"test-score points"},"memory_mean_change":{"value":1.48,"unit":"test-score points"}},"time":"1998/99 to 2002/03"},
            {"key":"age-adjusted-associations","en":"In age-adjusted analyses, baseline fibrinogen, IL-6, and ICAM-1 were negatively associated with several 2002/03 cognitive scores; the associations varied by marker and test.","ru":"В анализах с поправкой на возраст исходные фибриноген, IL-6 и ICAM-1 отрицательно коррелировали с несколькими когнитивными показателями 2002/03 года; связь зависела от маркера и теста.","predicate":"was negatively associated with selected cognitive performance measures","units":["U4","U5"],"roles":{"exposure":"baseline fibrinogen, IL-6, or ICAM-1","outcome":"selected 2002/03 cognitive test scores","analysis":"age-adjusted correlation analysis"},"type":"result","logic":"conjunction","claims":[{"predicate":"negative association across Raven’s Matrices, Verbal Fluency, Digit Symbol-Coding, and general cognitive factor","roles":{"exposure":"baseline fibrinogen"},"attrs":{"correlation_range":{"value":"r = -0.10 to -0.11","unit":None}}},{"predicate":"negative association across Raven’s Matrices, Verbal Fluency, Digit Symbol-Coding, and general cognitive factor","roles":{"exposure":"baseline IL-6"},"attrs":{"correlation_range":{"value":"r = -0.11 to -0.21","unit":None}}},{"predicate":"negative association across Raven’s Matrices, Verbal Fluency, Digit Symbol-Coding, and general cognitive factor","roles":{"exposure":"baseline ICAM-1"},"attrs":{"correlation_range":{"value":"r = -0.16 to -0.25","unit":None}}}],"conditions":["The associations were age-adjusted cross-sectional associations with scores in 2002/03, not by themselves evidence of prospective decline."]},
            {"key":"null-cross-sectional-markers","en":"D-dimer, CRP, and VCAM-1 were not statistically associated with performance on any cognitive test in the reported age-adjusted analyses.","ru":"В приведённых анализах с поправкой на возраст D-димер, CRP и VCAM-1 не имели статистически значимой связи ни с одним когнитивным тестом.","predicate":"did not show statistically significant association in this analysis","units":["U4","U5"],"roles":{"exposure":"baseline D-dimer, CRP, and VCAM-1","outcome":"cognitive test performance","analysis":"age-adjusted analysis"},"type":"result","negated":True,"conditions":["A non-significant result is not proof that no association exists in other samples, measures, or time windows."]},
            {"key":"adjusted-four-year-result","en":"After adjustment for age, sex, prior cognitive performance, depression, lifestyle, glucose intolerance or diabetes, and major cardiovascular disease, fibrinogen remained inversely associated with four-year decline in nonverbal reasoning.","ru":"После поправки на возраст, пол, прежние когнитивные результаты, депрессию, образ жизни, нарушение толерантности к глюкозе или диабет и крупные сердечно-сосудистые заболевания фибриноген сохранял обратную связь с четырёхлетним снижением невербального мышления.","predicate":"predicted greater four-year decline in nonverbal reasoning after full adjustment","units":["U4","U5","U6"],"roles":{"exposure":"baseline fibrinogen","outcome":"four-year change in Raven’s Matrices performance","adjustment":"multivariable model"},"type":"result","attrs":{"coefficient":{"value":-1.14,"unit":"test-score points per fibrinogen unit as modeled"},"p_value":{"value":"<.05","unit":None}},"time":"1998/99 to 2002/03","conditions":["Observational prediction in the regression model; it does not establish that fibrinogen caused the decline."]},
            {"key":"peak-ability-results","en":"When decline was estimated relative to NART-estimated peak prior ability, adjusted analyses associated IL-6 with lower processing-speed performance and ICAM-1 with lower nonverbal reasoning and general cognitive scores.","ru":"Когда снижение оценивали относительно пиковых прежних способностей по NART, скорректированные анализы связывали IL-6 с худшей скоростью обработки информации, а ICAM-1 — с худшими показателями невербального мышления и общего когнитивного фактора.","predicate":"was associated with estimated decline from peak prior cognitive ability","units":["U5","U6"],"roles":{"exposure":"baseline IL-6 or ICAM-1","outcome":"cognitive score relative to NART-estimated peak prior ability","analysis":"NART-adjusted multivariable analysis"},"type":"result","logic":"conjunction","claims":[{"predicate":"remained inversely associated with Digit Symbol-Coding performance","roles":{"exposure":"baseline IL-6"},"attrs":{"p_value":{"value":"<.05","unit":None}}},{"predicate":"remained inversely associated with Raven’s Matrices performance","roles":{"exposure":"baseline ICAM-1"},"attrs":{"p_value":{"value":"<.05","unit":None}}},{"predicate":"remained inversely associated with the general cognitive factor","roles":{"exposure":"baseline ICAM-1"},"attrs":{"p_value":{"value":"<.05","unit":None}}}],"conditions":["NART was measured in 2002/03 as a proxy for peak prior ability; this estimate is not the same outcome as observed four-year change from 1998/99."]},
            {"key":"separate-marker-model","en":"In models containing both IL-6 and ICAM-1, IL-6 contributed independently to Digit Symbol-Coding and general-factor scores, but neither marker was associated with Raven’s Matrices in that model.","ru":"В моделях с одновременным включением IL-6 и ICAM-1 IL-6 вносил независимый вклад в показатели Digit Symbol-Coding и общего фактора, но ни один маркер не был связан с результатом матриц Равена в этой модели.","predicate":"IL-6 contributed separately in selected joint models","units":["U5","U6"],"roles":{"exposure":"IL-6 and ICAM-1","outcome":"Digit Symbol-Coding and general cognitive factor","analysis":"joint model with both markers"},"type":"result","logic":"contrast","conditions":["The joint-model result does not establish a biological mechanism or causal independence."]},
            {"key":"mechanism-hypotheses","en":"The authors discussed vascular, coagulation, and inflammatory pathways as possible mechanisms linking biomarkers with cognition, while noting that causal direction and mechanisms remained uncertain.","ru":"Авторы обсуждали сосудистые, коагуляционные и воспалительные пути как возможные механизмы связи биомаркеров с когнитивными функциями, подчёркивая неопределённость причинного направления и механизмов.","predicate":"may be mechanistically related to cognitive decline","units":["U6","U7"],"roles":{"biomarkers":"fibrinogen, IL-6, and ICAM-1","outcome":"cognitive decline","candidate_mechanism":"vascular, coagulation, or inflammatory pathways"},"type":"conclusion","modality":"possible","conditions":["Author-discussed mechanisms are hypotheses; the observational study did not test causal mechanisms directly."]},
            {"key":"study-limitations","en":"The study used a single baseline biomarker measurement, had selective survival and participation, and could not eliminate practice effects or fully resolve the meaning of NART-estimated peak ability.","ru":"Исследование использовало однократное исходное измерение биомаркеров, включало избирательно сохранившуюся и участвовавшую выборку и не могло устранить эффект повторного тестирования или полностью разрешить ограничения оценки пиковых способностей по NART.","predicate":"limits interpretation and generalizability of biomarker associations","units":["U4","U5","U6","U7"],"roles":{"study":"Edinburgh Artery Study","limitation_1":"single baseline biomarker measurement","limitation_2":"selective survival and participation","limitation_3":"possible practice effects","limitation_4":"NART as an estimate of peak prior ability"},"type":"limitation","logic":"conjunction"},
            {"key":"study-conclusion","en":"The authors concluded that systemic inflammatory and hemostatic markers were associated with decline in selected cognitive abilities in older people, with associations depending on marker, outcome, and adjustment model.","ru":"Авторы заключили, что системные маркеры воспаления и гемостаза связаны со снижением отдельных когнитивных функций у пожилых людей; результат зависит от маркера, исхода и модели поправок.","predicate":"concluded that selected markers were associated with cognitive decline","units":["U1","U6","U7"],"roles":{"study":"Edinburgh Artery Study","markers":"systemic inflammatory and hemostatic markers","outcome":"selected cognitive abilities in older people"},"type":"conclusion","conditions":["This is the authors’ qualified interpretation of observational analyses, not a causal claim."]},
            {"key":"cited-prior-findings","en":"The introduction summarized prior studies with mixed findings: one report linked higher IL-6 and CRP tertiles to greater odds of cognitive decline, while other cohorts reported no adjusted association for IL-6 or CRP.","ru":"Во введении приведены неоднородные результаты прежних исследований: одна работа связала верхние тертили IL-6 и CRP с более высокими шансами когнитивного снижения, тогда как другие когорты не обнаружили скорректированной связи IL-6 или CRP.","predicate":"prior studies reported mixed biomarker-cognition associations","units":["U1","U2"],"roles":{"evidence":"previously published cohort studies","exposure":"IL-6 or CRP","outcome":"cognitive decline"},"type":"observation","logic":"contrast","conditions":["This is a summary of cited literature, not an independent result from the Edinburgh Artery Study; do not count as primary evidence from this article."]},
        ],
        "transitions": [
            {"sources":["cohort","assessment-timeline"],"target":"tested-sample","usage":"condition","reason":"The cohort and follow-up schedule define the participants eligible for repeated cognitive testing.","units":["U2","U3"]},
            {"sources":["assessment-timeline","cognitive-measures"],"target":"four-year-score-change","usage":"data","reason":"Repeated domain-specific tests provide the scores used to estimate four-year change.","units":["U3","U4"]},
            {"sources":["cohort","biomarker-measures"],"target":"age-adjusted-associations","usage":"method","reason":"The baseline cohort and marker assays define exposure measurements for the reported cognitive analyses.","units":["U2","U4","U5"]},
            {"sources":["cognitive-measures","biomarker-measures"],"target":"age-adjusted-associations","usage":"data","reason":"Cognitive test scores and baseline marker values are the variables paired in the age-adjusted analyses.","units":["U4","U5"]},
            {"sources":["tested-sample","age-adjusted-associations"],"target":"null-cross-sectional-markers","usage":"result","reason":"The stated null findings are bounded to the tested sample and age-adjusted cognitive analyses.","units":["U4","U5"]},
            {"sources":["assessment-timeline","cognitive-measures","biomarker-measures"],"target":"adjusted-four-year-result","usage":"method","reason":"The exposure timing, repeated cognition measures, and adjustment framework define the four-year regression result.","units":["U2","U3","U4","U5"]},
            {"sources":["cognitive-measures","adjusted-four-year-result"],"target":"peak-ability-results","usage":"condition","reason":"NART supplies the distinct peak-ability reference used for the second decline estimand.","units":["U3","U5","U6"]},
            {"sources":["age-adjusted-associations","peak-ability-results"],"target":"separate-marker-model","usage":"method","reason":"The joint model tests whether IL-6 and ICAM-1 contribute separately to overlapping cognitive outcomes.","units":["U5","U6"]},
            {"sources":["adjusted-four-year-result","peak-ability-results","study-limitations"],"target":"study-conclusion","usage":"result","reason":"The conclusion summarizes qualified results together with limits on timing, selection, and outcome interpretation.","units":["U6","U7"]},
            {"sources":["age-adjusted-associations","study-limitations"],"target":"mechanism-hypotheses","usage":"premise","reason":"The discussion interprets observed associations as possible mechanisms while retaining unresolved causal direction.","units":["U6","U7"]},
        ],
        "source_limitations": [
            "Ручная карта Codex по полному извлечённому тексту; все утверждения и ячейки таблиц не формализованы исчерпывающе.",
            "Таблицы 1–3 просмотрены визуально на страницах PDF 5–6; распознавание прочих страниц сверено по тексту, но не по изображению.",
            "Результаты наблюдательные; карта не прошла экспертную научную проверку.",
            "Фрагменты введения, пересказывающие цитируемые работы, помечены отдельно и не должны засчитываться как результаты этой когорты.",
        ],
    },
    "wilson2003": {
        "doi": "10.1046/j.1532-5415.2003.51454.x",
        "family": "duke-epese",
        "pdf_sha256": "bafe10e7007a4b156dd7e6ff725c356981fda6b2e92e7ef291397bc07b0485df",
        "text_sha256": "d2e88571f503a8872815c15a5575f9f68161af01decfeec34e0647a215ca0240",
        "title": "Cross-Linked Fibrin Degradation Products (D-Dimer), Plasma Cytokines, and Cognitive Decline in Community-Dwelling Elderly Persons",
        "title_ru": "Продукты распада сшитого фибрина (D-димер), плазменные цитокины и когнитивное снижение у пожилых людей, живущих в сообществе",
        "visual_pages": [2, 4, 5, 6],
        "table_pages": [4, 5],
        "knowledge": [
            {"key":"aim","en":"The study aimed to test whether coagulation and inflammatory markers predicted subsequent cognitive decline in older community-dwelling adults.","ru":"Цель исследования — проверить, предсказывают ли маркеры коагуляции и воспаления последующее когнитивное снижение у пожилых людей, живущих в сообществе.","predicate":"aimed to test marker associations with future cognitive decline","units":["U1","U2"],"roles":{"study":"Duke EPESE analysis","exposure":"coagulation and inflammatory markers","outcome":"subsequent cognitive decline","population":"older community-dwelling adults"},"type":"goal","conditions":["This is the study objective, not an observed result."]},
            {"key":"cohort-design","en":"The Duke EPESE was a longitudinal community-based cohort of adults aged 65 years and older recruited in a stratified household sample across five North Carolina counties.","ru":"Duke EPESE — продольная популяционная когорта людей от 65 лет, набранных стратифицированной выборкой домохозяйств в пяти округах Северной Каролины.","predicate":"followed a community-based cohort over repeated survey waves","units":["U1","U2"],"roles":{"study":"Duke EPESE","participants":"community-dwelling adults aged 65 years or older","setting":"five counties in North Carolina"},"type":"method","attrs":{"baseline_n":{"value":4162,"unit":"participants"}},"time":"Baseline survey in 1986; follow-up surveys through 1996"},
            {"key":"blood-sample","en":"At the 1992 third in-person survey, blood was collected from 1,727 participants; D-dimer and IL-6 were measured in 1,723 and 1,726 participants, respectively, and other cytokines in 1,551.","ru":"Во время третьего очного обследования в 1992 году кровь взяли у 1 727 участников; D-димер измерили у 1 723, IL-6 — у 1 726, другие цитокины — у 1 551 человека.","predicate":"collected blood and assayed inflammatory and coagulation markers","units":["U1","U2","U4"],"roles":{"sample":"blood collected at P3","marker_1":"D-dimer","marker_2":"IL-6","marker_3":"IL-10","marker_4":"TGF-beta","marker_5":"soluble VCAM-1","marker_6":"L-selectin"},"type":"method","attrs":{"blood_draw_n":{"value":1727,"unit":"participants"},"d_dimer_n":{"value":1723,"unit":"participants"},"il6_n":{"value":1726,"unit":"participants"},"other_cytokines_n":{"value":1551,"unit":"participants"}},"time":"1992, third in-person survey"},
            {"key":"cognitive-measure","en":"Cognition was measured with the Short Portable Mental Status Questionnaire at surveys in 1986, 1992, and 1996; higher error counts indicate worse performance, and an increase of at least two errors was treated as clinically meaningful.","ru":"Когнитивные функции измеряли Short Portable Mental Status Questionnaire в 1986, 1992 и 1996 годах; большее число ошибок означает худший результат, а прирост не менее чем на две ошибки считался клинически значимым.","predicate":"used repeated SPMSQ error scores as a global cognitive outcome","units":["U1","U2","U3"],"roles":{"instrument":"Short Portable Mental Status Questionnaire","outcome":"number of cognitive errors","interpretation":"higher score indicates worse performance"},"type":"method","attrs":{"clinically_meaningful_increase":{"value":2,"unit":"errors or more"}},"time":"P1=1986, P3=1992, P4=1996","conditions":["SPMSQ was the only longitudinal cognitive measure in this cohort analysis; it is a global screen, not a domain-specific battery."]},
            {"key":"analysis-sample","en":"Among 2,569 cohort members surviving to the 1992 blood draw, 1,727 had a successful blood collection; 1,218 had SPMSQ data at the 1996 follow-up. People unable to consent were more cognitively and functionally impaired.","ru":"Из 2 569 участников когорты, доживших до забора крови в 1992 году, кровь успешно взяли у 1 727; в 1996 году результаты SPMSQ имелись у 1 218 человек. Не способные дать согласие участники имели более выраженные когнитивные и функциональные нарушения.","predicate":"formed a selected analytic sample after survival and consent","units":["U2","U3","U5","U7"],"roles":{"survivors_at_blood_draw":"Duke EPESE members alive in 1992","blood_sample":"participants with successful blood draw","follow_up_sample":"participants with 1996 SPMSQ data","selection":"survival and ability to consent"},"type":"observation","attrs":{"survivors_1992":{"value":2569,"unit":"participants"},"blood_draw_success":{"value":1727,"unit":"participants"},"follow_up_spmsq":{"value":1218,"unit":"participants"}},"conditions":["Selection could exclude people with worse baseline cognition or function and limits generalization."]},
            {"key":"sample-characteristics","en":"At the 1992 survey, the mean age was 77.6 years (SD 5.4), 35.0% were men, and the mean IL-6 concentration was 1.7 pg/mL (SD 1.8).","ru":"В 1992 году средний возраст составлял 77,6 года (SD 5,4), мужчины составляли 35,0%, а средняя концентрация IL-6 — 1,7 пг/мл (SD 1,8).","predicate":"described the analytic cohort at the third survey","units":["U3","U4"],"roles":{"participants":"Duke EPESE sample at P3","age":"participant age","sex_composition":"male participants","il6":"plasma IL-6 concentration"},"type":"observation","attrs":{"mean_age":{"value":77.6,"unit":"years"},"age_sd":{"value":5.4,"unit":"years"},"male_share":{"value":35.0,"unit":"percent"},"il6_mean":{"value":1.7,"unit":"pg/mL"},"il6_sd":{"value":1.8,"unit":"pg/mL"}},"time":"1992, third in-person survey"},
            {"key":"cross-sectional-findings","en":"At the 1992 survey, D-dimer, IL-6, and soluble VCAM-1 had statistically significant but weak bivariate correlations with SPMSQ performance; adjusted cross-sectional models retained D-dimer, IL-10, and soluble VCAM-1.","ru":"В 1992 году D-димер, IL-6 и растворимый VCAM-1 имели статистически значимые, но слабые парные корреляции с результатом SPMSQ; в скорректированных поперечных моделях сохранились D-димер, IL-10 и растворимый VCAM-1.","predicate":"showed selected cross-sectional associations with SPMSQ performance","units":["U3","U4","U5"],"roles":{"exposure":"D-dimer, IL-6, or soluble VCAM-1","outcome":"SPMSQ performance at P3","analysis":"cross-sectional correlation and regression"},"type":"result","logic":"contrast","claims":[{"predicate":"weak bivariate correlation with SPMSQ at P3","roles":{"exposure":"log D-dimer"},"attrs":{"correlation":{"value":0.21,"unit":"Spearman r"},"p_value":{"value":"<.001","unit":None}}},{"predicate":"weak bivariate correlation with SPMSQ at P3","roles":{"exposure":"log IL-6"},"attrs":{"correlation":{"value":0.10,"unit":"Spearman r"},"p_value":{"value":"<.05","unit":None}}},{"predicate":"weak bivariate correlation with SPMSQ at P3","roles":{"exposure":"log soluble VCAM-1"},"attrs":{"correlation":{"value":0.10,"unit":"Spearman r"},"p_value":{"value":"<.05","unit":None}}}],"conditions":["The reported correlations are weak; the study authors questioned the clinical significance of IL-6 and soluble VCAM-1 associations."]},
            {"key":"d-dimer-prospective-result","en":"Higher log10 D-dimer independently predicted more SPMSQ errors over the 1992–1996 follow-up (parameter estimate 0.46, SE 0.20, P=.02) after multivariable stepwise adjustment.","ru":"Более высокий log10 D-димера независимо предсказывал больше ошибок SPMSQ в 1992–1996 годах (оценка 0,46; SE 0,20; P=.02) в пошаговой многофакторной модели.","predicate":"higher D-dimer predicted increase in SPMSQ errors over four years","units":["U1","U3","U5"],"roles":{"exposure":"log10 plasma D-dimer at P3","outcome":"change in SPMSQ errors from P3 to P4","analysis":"multivariable stepwise linear regression"},"type":"result","attrs":{"parameter_estimate":{"value":0.46,"unit":"SPMSQ error points per modeled log10 D-dimer unit"},"standard_error":{"value":0.20,"unit":"SPMSQ error points"},"p_value":{"value":".02","unit":None}},"time":"Four-year follow-up, 1992 to 1996","conditions":["An increase in SPMSQ errors indicates worse performance. This is an observational association, not evidence that D-dimer causes decline."]},
            {"key":"cross-sectional-effect-size","en":"In the adjusted cross-sectional model, a one-unit difference in log10 D-dimer corresponded to 0.27 more SPMSQ errors at the 1992 survey.","ru":"В скорректированной поперечной модели различие в одну единицу log10 D-димера соответствовало 0,27 дополнительной ошибки SPMSQ в 1992 году.","predicate":"was associated with poorer SPMSQ performance at P3","units":["U5"],"roles":{"exposure":"log10 D-dimer","outcome":"SPMSQ error count at P3","analysis":"adjusted cross-sectional regression"},"type":"result","attrs":{"parameter_estimate":{"value":0.27,"unit":"SPMSQ error points per modeled log10 D-dimer unit"},"standard_error":{"value":0.11,"unit":"SPMSQ error points"},"p_value":{"value":".02","unit":None}},"time":"1992"},
            {"key":"cytokine-prospective-null","en":"Peripheral cytokines, including IL-6, were not significantly associated with four-year SPMSQ change in the prospective adjusted analyses; no cytokine met the model-entry threshold for the change outcome.","ru":"Периферические цитокины, включая IL-6, не имели значимой связи с четырёхлетним изменением SPMSQ в скорректированных проспективных анализах; ни один цитокин не прошёл порог включения в модель изменения.","predicate":"did not show statistically significant association with prospective cognitive change","units":["U1","U3","U4","U5"],"roles":{"exposure":"peripheral cytokines including IL-6","outcome":"four-year SPMSQ change","analysis":"prospective adjusted regression"},"type":"result","negated":True,"conditions":["The null result is bounded to this cohort, assay, global cognitive screen, and follow-up period; it does not prove absence of effects in other settings."]},
            {"key":"reverse-direction-result","en":"Cognitive change from 1986 to 1992 did not independently predict later measured D-dimer or cytokine levels in the reported regression analyses.","ru":"Изменение когнитивных показателей с 1986 по 1992 год независимо не предсказывало последующие измеренные уровни D-димера или цитокинов в приведённых регрессионных анализах.","predicate":"prior SPMSQ change did not independently predict biomarker levels","units":["U3","U5"],"roles":{"predictor":"SPMSQ change from P1 to P3","outcome":"measured D-dimer and cytokine levels","analysis":"reverse-direction multivariable regression"},"type":"result","negated":True,"time":"Cognition P1–P3; biomarkers at P3","conditions":["Failure to detect a relationship in this analysis is not proof that no bidirectional mechanism exists."]},
            {"key":"method-adjustments","en":"Prospective models used SPMSQ change from P3 to P4 and adjusted for demographic, health, and functional variables selected through clinically important covariates and stepwise procedures.","ru":"В проспективных моделях анализировали изменение SPMSQ с P3 до P4 и учитывали демографические, медицинские и функциональные переменные, отобранные по клинической важности и пошаговой процедуре.","predicate":"modeled four-year SPMSQ change with selected covariates","units":["U3","U4","U5"],"roles":{"analysis":"forward stepwise linear regression","outcome":"increase in SPMSQ errors from P3 to P4","covariates":"demographic, medical, and functional status variables"},"type":"method","conditions":["Continuous biomarker values were natural-log transformed; BMI was mean-imputed by sex for missing values."]},
            {"key":"mechanistic-uncertainty","en":"The authors considered vascular and coagulation mechanisms for the D-dimer association but stated that the causal direction and the role of D-dimer itself remained uncertain.","ru":"Авторы рассматривали сосудистые и коагуляционные механизмы связи D-димера с когнитивными функциями, но отмечали неопределённость причинного направления и роли самого D-димера.","predicate":"may reflect vascular or coagulation mechanisms","units":["U6","U7"],"roles":{"exposure":"elevated D-dimer","outcome":"cognitive decline","candidate_mechanism":"vascular or coagulation pathway"},"type":"conclusion","modality":"possible","conditions":["These are proposed mechanisms; the cohort study did not test them causally."]},
            {"key":"limitations","en":"Interpretation is limited by selective survival and consent, competing deaths, possible ceiling effects, a global rather than domain-specific cognitive measure, and uncertainty about chronic versus acute cytokine elevations.","ru":"Интерпретацию ограничивают избирательное выживание и согласие на забор крови, конкурирующая смертность, возможный потолочный эффект, глобальный вместо доменно-специфичного когнитивный тест и неопределённость хронического или острого характера повышения цитокинов.","predicate":"limits interpretation and generalizability of biomarker findings","units":["U2","U3","U5","U6","U7"],"roles":{"study":"Duke EPESE analysis","limitation_1":"selection through survival and ability to consent","limitation_2":"death as a competing endpoint","limitation_3":"SPMSQ ceiling and global-screen limitations","limitation_4":"acute versus chronic biomarker elevation"},"type":"limitation","logic":"conjunction"},
            {"key":"conclusion","en":"The authors concluded that D-dimer predicted cognitive decline in this elderly community cohort, whereas no clinically significant prospective association was found for the peripheral cytokines measured.","ru":"Авторы заключили, что D-димер предсказывал когнитивное снижение в этой когорте пожилых людей, тогда как клинически значимой проспективной связи измеренных периферических цитокинов не обнаружили.","predicate":"concluded that D-dimer but not measured peripheral cytokines predicted decline","units":["U1","U5","U6","U7"],"roles":{"study":"Duke EPESE analysis","exposure_positive":"D-dimer","exposure_without_detected_prospective_association":"measured peripheral cytokines","outcome":"four-year cognitive decline"},"type":"conclusion","logic":"contrast","conditions":["The conclusion applies to this observational cohort, its assays, SPMSQ outcome, and four-year interval; it is not a causal claim."]},
            {"key":"cited-mechanistic-background","en":"The introduction described possible pathways through which inflammatory and coagulation activity could affect cognition, including vascular insults, neurotransmitter effects, and microthrombi.","ru":"Во введении описаны возможные пути влияния воспалительной и коагуляционной активности на когнитивные функции, включая сосудистые повреждения, эффекты нейромедиаторов и микротромбы.","predicate":"may influence cognition through several proposed pathways","units":["U1","U2"],"roles":{"pathways":"inflammatory and coagulation pathways","outcome":"cognition","mechanism_1":"vascular insults","mechanism_2":"neurotransmitter effects","mechanism_3":"microthrombi"},"type":"observation","modality":"possible","conditions":["This is mechanistic background summarized by the authors, not a mechanism demonstrated by the Duke EPESE analysis."]},
        ],
        "transitions": [
            {"sources":["cohort-design","blood-sample"],"target":"analysis-sample","usage":"condition","reason":"The cohort and blood-draw flow delimit the sample eligible for biomarker-linked follow-up analyses.","units":["U2","U3"]},
            {"sources":["blood-sample","sample-characteristics"],"target":"cross-sectional-findings","usage":"data","reason":"The measured biomarker values and P3 cognitive scores provide inputs to the cross-sectional analyses.","units":["U3","U4"]},
            {"sources":["cognitive-measure","analysis-sample","method-adjustments"],"target":"d-dimer-prospective-result","usage":"method","reason":"The outcome definition, eligible follow-up sample, and model specify the prospective D-dimer estimate.","units":["U3","U5"]},
            {"sources":["blood-sample","cognitive-measure","method-adjustments"],"target":"cytokine-prospective-null","usage":"method","reason":"The assayed cytokines and defined SPMSQ change outcome are tested in the adjusted prospective models.","units":["U3","U5"]},
            {"sources":["cognitive-measure","method-adjustments"],"target":"reverse-direction-result","usage":"method","reason":"The earlier SPMSQ interval is used as a predictor in the separately specified reverse-direction analyses.","units":["U3","U5"]},
            {"sources":["cross-sectional-findings","d-dimer-prospective-result"],"target":"cross-sectional-effect-size","usage":"result","reason":"The cross-sectional coefficient is a separate estimate from the same exposure but a different time-specific outcome model.","units":["U4","U5"]},
            {"sources":["d-dimer-prospective-result","cytokine-prospective-null","limitations"],"target":"conclusion","usage":"result","reason":"The conclusion contrasts the observed D-dimer association with the cytokine results under the study's stated limits.","units":["U5","U6","U7"]},
            {"sources":["cross-sectional-findings","limitations"],"target":"mechanistic-uncertainty","usage":"premise","reason":"The discussion frames candidate vascular mechanisms but retains uncertainty about causal direction.","units":["U6","U7"]},
        ],
        "source_limitations": [
            "Ручная карта Codex по полному извлечённому тексту; все утверждения и ячейки таблиц не формализованы исчерпывающе.",
            "Таблицы 2–5 визуально просмотрены на страницах PDF 4–5; таблица 1 и остальные страницы сверены по извлечённому тексту, но не все просмотрены как изображения.",
            "Результаты наблюдательные; карта не прошла экспертную научную проверку.",
            "Слабая парная корреляция IL-6 со SPMSQ в P3 отделена от отсутствия выявленной проспективной связи за P3–P4.",
        ],
    },
}


def author_one(article_id: str) -> Path:
    """Проверяет квитанцию и публикует отдельную неизменяемую ручную ревизию."""
    meta = SOURCES[article_id]
    source_dir = SOURCE_ROOT / article_id
    text_path = source_dir / "article.txt"
    receipt_path = source_dir / "receipt.json"
    source_text = text_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt["id"] == article_id, "Идентификатор квитанции не совпал")
    require(receipt["doi"] == meta["doi"], "DOI квитанции не совпал")
    require(receipt["family"] == meta["family"], "Семейство статьи не совпало")
    require(receipt["pdf_sha256"] == meta["pdf_sha256"], "Хеш PDF в квитанции не совпал")
    require(receipt["text_sha256"] == meta["text_sha256"] == digest(source_text), "Хеш полного текста не совпал")
    pdf_path = Path(receipt["origin"])
    require(pdf_path.is_file() and sha256(pdf_path.read_bytes()).hexdigest() == meta["pdf_sha256"], "Исходный PDF не прошёл проверку хеша")
    authored = {
        "version": "primary-cohort-codex-manual-map-v1",
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "knowledge": meta["knowledge"],
        "transitions": meta["transitions"],
        "excluded_units": {},
        "source_limitations": meta["source_limitations"],
    }
    artifacts = prepare_manual_map(article_id, source_text, meta["text_sha256"], authored,
                                   PROMPT_EXTRACTION, PROMPT_DEPENDENCIES)
    require(artifacts["coverage.json"]["references_excluded"] is True, "Раздел References не исключён")
    require(all(row["status"] == "represented" for row in artifacts["coverage.json"]["units"]), "Не все единицы источника учтены")
    artifacts["map.json"]["article_title"] = meta["title"]
    artifacts["source-receipt.json"] = receipt
    artifacts["source-review.json"] = {
        "article_id": article_id,
        "doi": meta["doi"],
        "publication_family": meta["family"],
        "pdf_sha256": meta["pdf_sha256"],
        "source_sha256": meta["text_sha256"],
        "full_text_units_reviewed": [f"U{i}" for i in range(1, 8)],
        "visually_reviewed_pdf_pages": meta["visual_pages"],
        "visually_reviewed_table_pages": meta["table_pages"],
        "references_excluded_from_extraction": True,
        "complete_semantic_coverage": False,
        "all_table_cells_formalized": False,
        "expert_validated": False,
        "author": "Codex",
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "translation_llm_calls": 0,
        "embedding_calls": 0,
        "token_usage": None,
    }
    graph = artifacts["map.json"]["graph"]
    report = [
        f"# {article_id}: исследовательская карта полного текста",
        "",
        f"**DOI:** `{meta['doi']}`  ",
        f"**SHA-256 PDF:** `{meta['pdf_sha256']}`  ",
        f"**SHA-256 текста:** `{meta['text_sha256']}`  ",
        f"**Запуск карты:** `{artifacts['map.json']['run_id']}`",
        "",
        f"Создано {len(graph['knowledge'])} канонических знаний, {sum(len(k['semantic_frame']['statements']) for k in graph['knowledge'])} отдельных утверждений и {len(graph['transitions'])} обоснованных переходов. Видимый DAG имеет {graph['analysis']['depth']} уровней.",
        "",
        "## Границы формализации",
        "",
        "Карта подготовлена вручную Codex из полного сохранённого текста. Извлечённый раздел References сохранён в источнике и исключён из знаний. Для ключевых числовых таблиц использованы визуально сверенные страницы, указанные в `source-review.json`; остальные табличные детали не считаются исчерпывающе формализованными.",
        "",
        "Карта подходит для исследовательского сопоставления контекстов, маркеров, измерений и результатов. Она не прошла экспертную проверку, не доказывает причинность и не подменяет исходную публикацию.",
        "",
        "Внешние и локальные LLM, переводчики и эмбеддинги не вызывались. Русские подписи подготовлены Codex; сведения о расходе токенов не выдумывались.",
        "",
    ]
    artifacts["report.ru.md"] = "\n".join(report)
    artifacts["validation.json"].update({
        "doi": meta["doi"], "pdf_sha256": meta["pdf_sha256"],
        "source_sha256": meta["text_sha256"], "external_llm_calls": 0,
        "local_llm_calls": 0, "translation_llm_calls": 0, "embedding_calls": 0,
    })
    output = OUTPUT_ROOT / artifacts["map.json"]["run_id"]
    for name, value in artifacts.items():
        payload = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        write_immutable(output / name, payload)
    return output


def main() -> None:
    global ROOT, SOURCE_ROOT, OUTPUT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--articles", nargs="+", choices=tuple(SOURCES), default=list(SOURCES))
    args = parser.parse_args()
    ROOT = args.root.resolve()
    SOURCE_ROOT = ROOT / "eval/question_prediction/il6-plasma-global-v1/empirical-fulltext-continuation-v1/sources"
    OUTPUT_ROOT = ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs"
    sys.stdout.reconfigure(encoding="utf-8")
    disable_network()
    for article_id in args.articles:
        output = author_one(article_id)
        result = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        print(json.dumps({"article_id": article_id, "run_id": output.name,
                          "knowledge": result["analysis"]["canonical_knowledge_count"],
                          "transitions": result["analysis"]["transition_count"],
                          "depth": result["analysis"]["depth"], "model_calls": 0,
                          "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
