"""Создаёт альтернативную ручную аннотацию уже оценённой статьи без модельных вызовов."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import registered_prompt_paths
from domain.article_maps import digest, prepare_source, require
from infrastructure.immutable_files import write_immutable


ARTICLE_ID = "PMC10002471"
DOI = "10.1016/j.neurobiolaging.2022.10.011"
SOURCE_PATH = Path("eval/article_pipeline_gold/cases/pmc10002471/article.md")
OUTPUT_ROOT = Path("eval/whole_map_forecast/pmc10002471-annotation-version-audit-v1/codex-v3-v15/runs")
PRIOR_HELDOUT_RUN_ID = "86f921d6-7bb9-5cd3-a84a-befdc0e83854"
HISTORICAL_BINDING = {
    "prompt": {"id": "KM.TEXT_TO_MAP", "version": "3", "sha256": "71d626d5e892dfac0cef836170142e442928a9526982011c483f17ef94f90c1f"},
    "dependency_prompt": {"id": "KM.TEXT_TO_MAP.DEPENDENCIES", "version": "15", "sha256": "21d56fba6683319b09e001faa3f91f637b1f28cecb6cadef9ef019b25d144915"},
}


def build_authored(source: dict) -> dict:
    """Формализует эмпирические результаты, методы и явно ограниченные выводы."""
    units = {unit["id"]: unit for unit in source["units"]}
    records: list[dict] = []

    def add(key: str, en: str, ru: str, predicate: str, unit_ids: list[str], roles: dict,
            *, attrs: dict | None = None, kind: str = "state", knowledge_type: str = "result",
            claims: list[dict] | None = None, logic: str = "single", conditions: list[str] | None = None,
            time: str | None = "Cross-sectional healthy-aging cohort; assessment during the imaging visit",
            modality: str | None = None, quantifier: str | None = None, status: str | None = None,
            origin: str = "direct observation or analysis in the present study") -> None:
        require(all(uid in units for uid in unit_ids), f"Unknown source unit in {key}")
        values = {"cohort": "160 community-dwelling healthy older adults in the present study", **roles}
        if knowledge_type in {"observation", "result", "comparison"}:
            values.setdefault("evidence_origin", origin)
        item = {
            "key": key, "en": en, "ru": ru, "predicate": predicate, "units": unit_ids,
            "roles": values, "attrs": attrs or {}, "kind": kind, "type": knowledge_type,
            "logic": logic, "time": time,
            "conditions": conditions or ["Observational study result; this association does not establish causation."],
            "modality": modality, "quantifier": quantifier,
        }
        if claims:
            item["claims"] = claims
        if kind == "action":
            item["status"] = status or "performed"
        records.append(item)

    # Background in the article is attributed to cited literature, not to this cohort.
    add("hcy-background", "The article describes homocysteine as a vascular risk factor associated with cognitive impairment and cerebrovascular disease and implicated in Alzheimer’s disease.",
        "В статье гомоцистеин описан как сосудистый фактор риска, связанный с когнитивными нарушениями и цереброваскулярными заболеваниями и рассматриваемый в связи с болезнью Альцгеймера.",
        "associated_with_risk_or_disease", ["U6", "U8"], {"exposure": "plasma homocysteine (Hcy)", "outcome": "cognitive impairment", "disease": "cerebrovascular disease and Alzheimer’s disease"},
        knowledge_type="assertion", origin="prior studies summarized by the authors", conditions=["Background statement; not an outcome measured as a new causal effect in this cohort."])
    add("hcy-metabolism", "Homocysteine is produced during metabolism of the dietary essential amino acid methionine, and age-related metabolic disturbances may increase plasma Hcy concentrations.",
        "Гомоцистеин образуется при метаболизме незаменимой аминокислоты метионина; возрастные нарушения метаболизма могут повышать его концентрацию в плазме.",
        "metabolism_and_possible_age_related_increase", ["U8"], {"metabolite": "homocysteine", "precursor": "methionine", "age_related_factor": "metabolic disturbance"},
        knowledge_type="assertion", modality="may", origin="background mechanism described by the authors")
    add("prior-hcy-atrophy", "Prior imaging studies associated higher Hcy with stroke risk and brain atrophy, including medial temporal and hippocampal regions, while another study reported associations in nucleus accumbens, thalamus, and brain stem but not hippocampus.",
        "В прежних нейровизуализационных исследованиях более высокий Hcy связывали с риском инсульта и атрофией мозга, включая медиальную височную область и гиппокамп; другое исследование обнаружило связи в прилежащем ядре, таламусе и стволе мозга, но не в гиппокампе.",
        "prior_studies_reported_regionally_different_associations", ["U8", "U9"], {"exposure": "higher homocysteine", "outcomes": "stroke risk and regional brain atrophy"},
        knowledge_type="comparison", logic="contrast", origin="separate prior studies cited in the introduction",
        claims=[
            {"predicate": "associated_with", "roles": {"exposure": "higher homocysteine", "outcome": "stroke risk and medial temporal or hippocampal atrophy"}, "conditions": ["Prior studies cited by the authors; populations and methods differ."]},
            {"predicate": "associated_with_regional_volume_reduction", "roles": {"exposure": "higher homocysteine", "regions": "nucleus accumbens, thalamus, and brain stem", "not_reported_region": "hippocampus"}, "conditions": ["A separate prior study of non-demented older adults; do not merge with the other studies."]},
        ])
    add("vascular-pathway-background", "Prior work links Hcy with pro-thrombotic and pro-atherogenic processes, small-vessel cerebrovascular disease, and greater WMH burden; WMH burden has also been associated with AD-like atrophy and diminished cognition.",
        "В прежних работах Hcy связывали с тромбозом, атерогенезом, болезнью мелких сосудов и большей нагрузкой гиперинтенсивности белого вещества; нагрузку WMH также связывали с атрофией, похожей на изменения при болезни Альцгеймера, и снижением когнитивной функции.",
        "prior_literature_connects_vascular_processes_wmh_atrophy_and_cognition", ["U10", "U11"], {"candidate_factor": "homocysteine-related vascular pathology", "intermediate_measure": "white matter hyperintensity (WMH) burden", "possible_outcomes": "brain atrophy and diminished cognitive function"},
        knowledge_type="assertion", origin="converging prior evidence summarized by the authors", modality="may", conditions=["Background synthesis; reported associations do not by themselves prove a causal chain."])
    add("mechanism-gap", "The pathway by which elevated Hcy may contribute to subcortical atrophy and cerebrovascular or Alzheimer’s disease risk is not fully understood.",
        "Путь, через который повышенный Hcy может способствовать подкорковой атрофии и риску цереброваскулярных заболеваний или болезни Альцгеймера, полностью не установлен.",
        "mechanism_remains_uncertain", ["U9", "U11"], {"exposure": "elevated homocysteine", "outcomes": "subcortical atrophy and cerebrovascular or Alzheimer’s disease risk"},
        knowledge_type="limitation", modality="uncertain", origin="explicit knowledge gap stated by the authors")
    add("ssm-background", "The Scaled Subprofile Model is a modified principal-component method used to detect regionally distributed covariance patterns without correction for multiple comparisons.",
        "Scaled Subprofile Model — модифицированный метод главных компонент для выявления распределённых по областям ковариационных паттернов без поправки на множественные сравнения.",
        "method_detects_regional_covariance_patterns", ["U12", "U13"], {"method": "Scaled Subprofile Model (SSM)", "target": "regional covariance across brain structures"},
        knowledge_type="method", origin="method description in the article")
    add("study-aim", "The study aimed to identify a plasma-Hcy-related covariance pattern across subcortical gray-matter volumes and test its associations with WMH, other vascular and Alzheimer’s risk factors, and cognition.",
        "Целью исследования было выявить связанный с Hcy плазмы паттерн ковариации объёмов подкоркового серого вещества и проверить его связи с WMH, сосудистыми и связанными с болезнью Альцгеймера факторами риска и когнитивными функциями.",
        "investigate_hcy_related_sgm_pattern_and_associations", ["U14"], {"study": "present study", "exposure": "plasma total Hcy", "candidate_pattern": "subcortical gray-matter (SGM) covariance pattern"},
        kind="action", knowledge_type="goal", status="planned", modality="aimed to", origin="stated study objective")
    add("study-hypothesis", "The authors hypothesized that greater Hcy-related SGM pattern expression would accompany aging and greater WMH burden and would relate to diminished cognitive performance.",
        "Авторы предположили, что более выраженный паттерн Hcy–SGM будет связан с возрастом и большей нагрузкой WMH и со снижением когнитивных показателей.",
        "hypothesize_hcy_pattern_links_age_wmh_and_cognition", ["U14"], {"pattern": "Hcy-related SGM covariance pattern", "predictors": "older age and greater WMH burden", "outcome": "diminished cognitive performance"},
        knowledge_type="goal", modality="hypothesized", origin="a priori hypothesis; not an observed result")

    # Cohort, measurements, and analytic operations.
    add("cohort-profile", "The cohort included 160 community-dwelling healthy volunteers aged 50–89 years (mean 69.66 ± 9.95; 53.8% women); 95.0% were White and mean education was 15.98 ± 2.57 years.",
        "В когорту вошли 160 здоровых добровольцев, живущих в сообществе, 50–89 лет (средний возраст 69,66 ± 9,95 года; 53,8% женщин); 95,0% были белыми, среднее образование — 15,98 ± 2,57 года.",
        "cohort_characteristics", ["U17"], {"population": "community-dwelling healthy volunteers", "study": "present study"},
        knowledge_type="observation", attrs={"sample_size": {"value": 160, "unit": "participants"}, "age_min": {"value": 50, "unit": "years"}, "age_max": {"value": 89, "unit": "years"}, "mean_age": {"value": "69.66 ± 9.95", "unit": "years"}, "women": {"value": 53.8, "unit": "%"}, "White_participants": {"value": 95.0, "unit": "%"}, "mean_education": {"value": "15.98 ± 2.57", "unit": "years"}},
        time="Study assessment visit", conditions=["Descriptive sample statistics; do not treat as population prevalence."])
    add("eligibility-screen", "Participants with significant medical, psychiatric, or neurological disorders, HAM-D scores above 9, or MMSE scores below 26 were excluded; the included sample had mean MMSE 29.01 ± 1.25.",
        "Исключали участников со значимыми соматическими, психиатрическими или неврологическими заболеваниями, HAM-D > 9 либо MMSE < 26; средний MMSE включённой выборки составил 29,01 ± 1,25.",
        "screening_and_exclusion_criteria", ["U17"], {"population": "study participants", "screening_instrument": "Hamilton Depression Rating Scale (HAM-D) and Mini-Mental State Exam (MMSE)"},
        knowledge_type="method", attrs={"HAM-D_exclusion_threshold": {"value": 9, "unit": "score; greater excluded"}, "MMSE_exclusion_threshold": {"value": 26, "unit": "score; lower excluded"}, "mean_MMSE": {"value": "29.01 ± 1.25", "unit": "score"}},
        conditions=["The cohort is selected and described as healthy older adults; findings do not automatically generalize to people with dementia or major disorders."])
    add("ethics-consent", "All participants gave informed written consent, and the University of Arizona Institutional Review Board approved the study.",
        "Все участники дали письменное информированное согласие; исследование одобрил институциональный этический комитет Университета Аризоны.",
        "consent_and_ethics_approval", ["U17"], {"participants": "all study participants", "review_body": "University of Arizona Institutional Review Board"},
        knowledge_type="method", origin="study procedures reported by the authors")
    add("plasma-hcy-assay", "Fasting blood was collected after at least 12 hours; plasma total Hcy was measured with one of two immunoassays, whose laboratory validation had a Deming regression coefficient above 0.999.",
        "Кровь брали натощак после минимум 12 часов; общий Hcy плазмы измеряли одним из двух иммуноанализов, лабораторная сверка которых дала коэффициент регрессии Деминга > 0,999.",
        "measure_plasma_total_hcy", ["U19"], {"specimen": "fasting blood plasma", "analyte": "total homocysteine", "measurement": "fluorescence polarization or chemiluminescence microparticle immunoassay"},
        kind="action", knowledge_type="method", status="performed", attrs={"minimum_fasting": {"value": 12, "unit": "hours"}, "Deming_regression_coefficient": {"value": ">0.999", "unit": None}},
        conditions=["Two analyzer platforms were used; the article reports laboratory validation between them."])
    add("b12-assay", "Serum vitamin B12 was measured by enhanced chemiluminescence immunoassay.",
        "Витамин B12 сыворотки измеряли методом усиленной хемилюминесцентной иммуноанализа.",
        "measure_serum_vitamin_b12", ["U19"], {"specimen": "serum", "analyte": "vitamin B12"}, kind="action", knowledge_type="method", status="performed")
    add("apoe-genotyping", "APOE genotype was determined from blood-derived genomic DNA using PCR/restriction-fragment methods; 48 participants (30.0%) carried ε4 and 112 (70.0%) did not.",
        "Генотип APOE определяли по геномной ДНК из крови методом ПЦР/рестрикционного анализа; ε4 несли 48 участников (30,0%), не несли — 112 (70,0%).",
        "determine_apoe_epsilon4_status", ["U20"], {"specimen": "blood-derived genomic DNA", "genotype": "APOE ε4 status"},
        kind="action", knowledge_type="method", status="performed", attrs={"epsilon4_carriers": {"value": 48, "unit": "participants"}, "carriers_percent": {"value": 30.0, "unit": "%"}, "noncarriers": {"value": 112, "unit": "participants"}, "noncarriers_percent": {"value": 70.0, "unit": "%"}}, time="Present study cohort")
    add("fitness-assessment", "VO2 was measured during a graded treadmill test; VO2max was accepted when at least two of three specified physiological criteria were met.",
        "VO2 измеряли при ступенчатой нагрузочной пробе на дорожке; VO2max считали достигнутым при выполнении как минимум двух из трёх заданных физиологических критериев.",
        "assess_cardiorespiratory_fitness", ["U22"], {"measure": "VO2max", "purpose": "cardiorespiratory fitness"},
        kind="action", knowledge_type="method", status="performed", attrs={"required_criteria": {"value": 2, "unit": "of 3"}},
        conditions=["Criteria were VO2 plateau despite increased workload, respiratory exchange ratio ≥1.1, and heart rate within 10 beats of age-predicted maximum."])
    add("mri-protocol", "The study acquired volumetric T1-weighted SPGR MRI and T2-weighted FLAIR MRI on a 3T GE Signa scanner with the reported sequence parameters.",
        "В исследовании получили объёмные T1-взвешенные SPGR- и T2-взвешенные FLAIR-снимки на сканере GE Signa 3T с указанными параметрами последовательностей.",
        "acquire_structural_brain_mri", ["U24"], {"instrument": "3T GE Signa MRI scanner", "sequences": "T1-weighted SPGR and T2-weighted FLAIR"},
        kind="action", knowledge_type="method", status="performed", attrs={"T1_TR": {"value": 5.3, "unit": "ms"}, "T1_TE": {"value": 2.0, "unit": "ms"}, "T1_TI": {"value": 500, "unit": "ms"}, "T1_slice_thickness": {"value": 1.0, "unit": "mm"}, "FLAIR_TR": {"value": 11000, "unit": "ms"}, "FLAIR_TE": {"value": 120, "unit": "ms"}, "FLAIR_TI": {"value": 2250, "unit": "ms"}, "FLAIR_slice_thickness": {"value": 2.6, "unit": "mm"}})
    add("sgm-segmentation", "FreeSurfer v5.3 processing produced bilateral volumes for seven subcortical gray-matter structures, with visual quality review and reprocessing when needed.",
        "Обработка FreeSurfer v5.3 дала двусторонние объёмы семи подкорковых структур серого вещества; качество сегментации визуально проверяли и при необходимости повторно обрабатывали.",
        "segment_subcortical_gray_matter_volumes", ["U25", "U26"], {"images": "T1-weighted MRI", "software": "FreeSurfer v5.3", "structures": "thalamus, caudate, putamen, pallidum, hippocampus, amygdala, nucleus accumbens"},
        kind="action", knowledge_type="method", status="performed", attrs={"structures_per_hemisphere": {"value": 7, "unit": "regions"}, "participants_illustrated": {"value": 160, "unit": "participants"}},
        conditions=["Figure 1 illustrates average SGM volumes; it is not a separate group comparison."])
    add("wmh-segmentation-validation", "WMH segmentation used T1 and FLAIR images with the lesion-growth algorithm; manual reference maps from 35 participants were used to select kappa 0.35 by spatial overlap.",
        "WMH сегментировали по T1 и FLAIR алгоритмом роста очагов; ручные референсные карты 35 участников использовали для выбора κ = 0,35 по пространственному перекрытию.",
        "validate_wmh_segmentation_threshold", ["U27", "U28"], {"input": "T1 and FLAIR MRI", "algorithm": "lesion growth algorithm", "reference": "manually segmented WMH maps"},
        kind="action", knowledge_type="method", status="performed", attrs={"manual_reference_subset": {"value": 35, "unit": "participants"}, "optimal_kappa": {"value": 0.35, "unit": None}},
        conditions=["Two expert raters and one geriatric-neurology specialist reviewed manual maps by consensus."])
    add("wmh-volume-and-tiv", "WMH maps were visually inspected, total lesion volume was computed by summing voxel volumes and natural-log transformed, and TIV was estimated from gray matter, white matter, and CSF segments.",
        "Карты WMH визуально проверяли; общий объём очагов вычисляли суммой объёмов вокселей и логарифмировали. TIV оценивали по сегментам серого и белого вещества и ликвора.",
        "derive_wmh_volume_and_total_intracranial_volume", ["U29"], {"derived_measure": "total WMH volume and total intracranial volume (TIV)", "software": "LGA and SPM12"},
        kind="action", knowledge_type="method", status="performed", conditions=["WMH volume was natural-log transformed for analyses."])
    add("processing-speed-measure", "Log-transformed TMT-A completion time was used as processing speed, with higher scores representing poorer performance.",
        "Логарифм времени выполнения TMT-A использовали как показатель скорости обработки; более высокие значения означали худший результат.",
        "operationalize_processing_speed", ["U31"], {"instrument": "Trail Making Test Part A (TMT-A)", "construct": "processing speed"},
        knowledge_type="method", attrs={"transformation": {"value": "natural logarithm of completion time", "unit": None}, "score_direction": {"value": "higher is poorer", "unit": None}}, conditions=["Operational definition used in this study; do not reverse the scale direction."])
    add("executive-function-measure", "The standardized residual of TMT-B after removing TMT-A processing-speed performance was used to measure cognitive flexibility and shifting.",
        "Стандартизованный остаток TMT-B после статистического удаления результата скорости обработки по TMT-A использовали для оценки когнитивной гибкости и переключения.",
        "operationalize_cognitive_flexibility", ["U31"], {"instrument": "residualized Trail Making Test Part B (TMT-B)", "construct": "cognitive flexibility and shifting"},
        knowledge_type="method", conditions=["This is a residualized outcome, not raw TMT-B completion time."])
    add("verbal-memory-measure", "Consistent long-term retrieval on the 12-trial, 12-word Buschke Selective Reminding Test was used as a measure of verbal episodic memory.",
        "Устойчивое долговременное воспроизведение в 12-пробной версии теста выборочного напоминания Бушке со списком из 12 слов использовали как показатель вербальной эпизодической памяти.",
        "operationalize_verbal_memory", ["U31"], {"instrument": "Buschke Selective Reminding Test (SRT)", "construct": "verbal episodic memory"},
        knowledge_type="method", attrs={"trials": {"value": 12, "unit": "trials"}, "word_list": {"value": 12, "unit": "words"}})
    add("ssm-analysis-operation", "SSM was applied to 14 bilateral subcortical regions; PCA-derived components and subject scores were selected using AIC, with the lowest-AIC sequential component set retained.",
        "SSM применили к 14 двусторонним подкорковым областям; компоненты и индивидуальные оценки после PCA отбирали по AIC, оставляя последовательный набор с минимальным AIC.",
        "fit_and_select_ssm_components", ["U33", "U34"], {"method": "Scaled Subprofile Model with PCA", "input": "bilateral volumes of seven SGM structures"},
        kind="action", knowledge_type="method", status="performed", attrs={"regions_of_interest": {"value": 14, "unit": "regions"}, "component_selection": {"value": "lowest Akaike information criterion", "unit": None}},
        conditions=["The outcome was a regionally distributed covariance pattern and participant expression scores, not an isolated volume of a single region."])
    add("bootstrap-and-univariate-analysis", "The SSM pattern weights were assessed with 10,000 bootstrap iterations; individual regional Hcy associations were tested with TIV adjustment and false-discovery-rate correction.",
        "Веса паттерна SSM оценивали 10 000 бутстрэп-итерациями; индивидуальные связи Hcy с областями проверяли с поправкой на TIV и контрольной процедурой FDR.",
        "assess_pattern_weight_reliability_and_regional_associations", ["U35"], {"method": "bootstrap and univariate regression", "target": "SSM weights and individual SGM volumes"},
        kind="action", knowledge_type="method", status="performed", attrs={"bootstrap_iterations": {"value": 10000, "unit": "iterations"}, "multiple_comparison_control": {"value": "false discovery rate", "unit": None}})
    add("blockwise-regression-method", "Block-wise regression entered TIV first, then WMH volume, then age and sex, then vascular and Alzheimer’s risk factors, and finally vitamin B12.",
        "В блочную регрессию сначала включали TIV, затем объём WMH, возраст и пол, сосудистые и связанные с болезнью Альцгеймера факторы риска и, наконец, витамин B12.",
        "adjust_hcy_pattern_regression_in_sequential_blocks", ["U36"], {"outcome": "Hcy-related SGM network pattern", "covariates": "TIV, WMH, age, sex, APOE ε4, hypertension, smoking, VO2max, vitamin B12"},
        kind="action", knowledge_type="method", status="performed", conditions=["Block order matters; later covariates were added after earlier blocks."])
    add("mediation-analysis-method", "Mediation models tested age, WMH burden, and the Hcy-SGM pattern in relation to processing speed, executive function, and verbal memory, with demographic, health, timing, and depression covariates as specified.",
        "Медиационные модели проверяли возраст, нагрузку WMH и паттерн Hcy–SGM в связи со скоростью обработки, исполнительной функцией и вербальной памятью с предусмотренными поправками на демографические, медицинские факторы, интервалы обследований и депрессию.",
        "test_serial_mediation_for_three_cognitive_outcomes", ["U37", "U38", "U39"], {"predictor": "age", "candidate_mediators": "WMH volume and Hcy-related SGM pattern", "outcomes": "processing speed, executive function, verbal memory"},
        kind="action", knowledge_type="method", status="performed", attrs={"bootstrap_iterations": {"value": 10000, "unit": "iterations"}, "confidence_interval": {"value": 95, "unit": "% percentile bootstrap CI"}},
        conditions=["A 95% bootstrap CI excluding zero was treated as statistically significant; mediation does not establish causal direction in this observational design."])

    # Main empirical findings. Component claims preserve contrasts and negative results.
    add("hcy-sgm-pattern", "In 160 healthy older adults, higher plasma total Hcy was associated with greater expression of an SSM-derived SGM pattern (9.4% of Hcy variance; F(1,158)=16.30, p<0.0001), marked by bilateral hippocampal and nucleus-accumbens volume reductions and relative caudate, putamen, and pallidum increases.",
        "У 160 здоровых пожилых участников более высокий общий Hcy плазмы был связан с большей выраженностью паттерна SGM по SSM (9,4% дисперсии Hcy; F(1,158)=16,30; p<0,0001). Паттерн включал двустороннее уменьшение объёма гиппокампа и прилежащего ядра и относительное увеличение хвостатого ядра, скорлупы и бледного шара.",
        "higher_hcy_associated_with_greater_ssm_pattern_expression", ["U6", "U41", "U42", "U53", "U55", "U67"], {"exposure": "plasma total homocysteine", "pattern": "Hcy-related subcortical gray-matter covariance pattern"},
        knowledge_type="result", attrs={"variance_explained": {"value": 9.4, "unit": "% of plasma total Hcy variance"}, "F_statistic": {"value": "F(1,158)=16.30", "unit": None}, "p_value": {"value": "<0.0001", "unit": None}, "sample_size": {"value": 160, "unit": "participants"}},
        conditions=["The increases in caudate, putamen, and pallidum are relative SSM pattern weights; they are not all confirmed as absolute positive volume associations."])
    add("regional-hcy-associations", "After TIV adjustment and FDR correction, Hcy was inversely associated with left and right hippocampal and nucleus-accumbens volumes; other regional positive associations were not statistically significant.",
        "После поправки на TIV и FDR Hcy был обратно связан с объёмом левого и правого гиппокампа и прилежащего ядра; положительные связи для других областей статистически значимыми не были.",
        "regional_volumes_associated_with_hcy_after_adjustment", ["U43", "U57"], {"exposure": "plasma Hcy", "regions_with_inverse_association": "bilateral hippocampus and nucleus accumbens", "other_regions": "bilateral caudate, putamen, and pallidum"},
        knowledge_type="comparison", logic="contrast", attrs={"left_hippocampus_beta": {"value": -0.295, "unit": None}, "left_hippocampus_p_FDR": {"value": 0.003, "unit": None}, "right_hippocampus_beta": {"value": -0.259, "unit": None}, "right_hippocampus_p_FDR": {"value": 0.008, "unit": None}, "left_nucleus_accumbens_beta": {"value": -0.247, "unit": None}, "left_nucleus_accumbens_p_FDR": {"value": 0.008, "unit": None}, "right_nucleus_accumbens_beta": {"value": -0.204, "unit": None}, "right_nucleus_accumbens_p_FDR": {"value": 0.028, "unit": None}},
        claims=[
            {"predicate": "inversely_associated_after_adjustment", "roles": {"exposure": "plasma Hcy", "outcome": "bilateral hippocampal and nucleus-accumbens volumes"}, "conditions": ["Adjusted for TIV; FDR-corrected regional tests."]},
            {"predicate": "positive_association_not_statistically_detected_after_adjustment", "roles": {"exposure": "plasma Hcy", "outcome": "caudate, putamen, and pallidum volumes"}, "conditions": ["Adjusted for TIV and FDR-corrected; non-significance is not proof of no effect."]},
        ])
    add("wmh-age-sex-associations", "After adjustment for TIV and other specified covariates, greater WMH volume, older age, and male sex remained associated with greater Hcy-SGM pattern expression; APOE ε4, hypertension, smoking, VO2max, and serum B12 did not add statistically significant contributions.",
        "После поправки на TIV и заданные ковариаты больший объём WMH, старший возраст и мужской пол сохраняли связь с большей выраженностью паттерна Hcy–SGM; APOE ε4, гипертензия, курение, VO2max и B12 сыворотки не дали статистически значимого дополнительного вклада.",
        "adjusted_predictors_and_noncontributing_covariates_for_hcy_pattern", ["U44", "U45", "U46", "U53", "U56"], {"outcome": "Hcy-related SGM pattern expression", "associated_factors": "WMH volume, older age, male sex", "tested_factors_without_additional_significance": "APOE ε4, hypertension, smoking, VO2max, vitamin B12"},
        knowledge_type="comparison", logic="contrast", attrs={"WMH_beta_TIV_only": {"value": 0.427, "unit": None}, "WMH_p_TIV_only": {"value": "9.0903E-9", "unit": None}, "age_beta_final": {"value": 0.297, "unit": None}, "age_p_final": {"value": 0.002, "unit": None}, "WMH_beta_final": {"value": 0.231, "unit": None}, "WMH_p_final": {"value": 0.004, "unit": None}, "male_sex_beta_final": {"value": 0.217, "unit": None}, "male_sex_p_final": {"value": 0.027, "unit": None}, "vitamin_B12_p": {"value": 0.889, "unit": None}},
        claims=[
            {"predicate": "positively_associated_after_adjustment", "roles": {"predictor": "greater WMH volume", "outcome": "greater Hcy-SGM pattern expression"}, "attrs": {"beta_TIV_only": {"value": 0.427, "unit": None}, "p_TIV_only": {"value": "9.0903E-9", "unit": None}, "beta_final": {"value": 0.231, "unit": None}, "p_final": {"value": 0.004, "unit": None}}},
            {"predicate": "positively_associated_after_adjustment", "roles": {"predictor": "older age", "outcome": "greater Hcy-SGM pattern expression"}, "attrs": {"beta_final": {"value": 0.297, "unit": None}, "p_final": {"value": 0.002, "unit": None}}},
            {"predicate": "associated_with_greater_expression_in_men", "roles": {"predictor": "male sex", "outcome": "Hcy-SGM pattern expression"}, "attrs": {"beta_final": {"value": 0.217, "unit": None}, "p_final": {"value": 0.027, "unit": None}}},
            {"predicate": "additional_association_not_statistically_detected", "roles": {"tested_factors": "APOE ε4, hypertension, smoking, VO2max, and serum vitamin B12", "outcome": "Hcy-SGM pattern expression"}, "conditions": ["Failure to detect additional statistical contribution in these models does not establish equivalence or absence of an effect."]},
        ], conditions=["Covariate-adjusted observational regression; coefficients are model-specific and are not causal effects."])
    add("age-wmh-path", "In the mediation analysis, older age predicted greater WMH volume (β=0.505, p<0.0001).",
        "В медиационном анализе старший возраст предсказывал больший объём WMH (β=0,505; p<0,0001).",
        "older_age_predicts_greater_wmh_volume_in_model", ["U47", "U50"], {"predictor": "older age", "outcome": "total WMH volume"},
        knowledge_type="result", attrs={"beta": {"value": 0.505, "unit": None}, "B": {"value": 0.055, "unit": None}, "SE": {"value": 0.009, "unit": None}, "p_value": {"value": "<0.0001", "unit": None}},
        conditions=["Path coefficient in an observational mediation model; it does not establish that age causally changes WMH."])
    add("wmh-pattern-path", "In the mediation analysis, greater WMH volume predicted greater Hcy-SGM pattern expression (β=0.236, p=0.007).",
        "В медиационном анализе больший объём WMH предсказывал большую выраженность паттерна Hcy–SGM (β=0,236; p=0,007).",
        "greater_wmh_predicts_greater_hcy_pattern_expression", ["U47", "U50"], {"predictor": "total WMH volume", "outcome": "Hcy-SGM pattern expression"},
        knowledge_type="result", attrs={"beta": {"value": 0.236, "unit": None}, "B": {"value": 0.218, "unit": None}, "SE": {"value": 0.080, "unit": None}, "p_value": {"value": 0.007, "unit": None}},
        conditions=["Path coefficient in an observational mediation model; it is not by itself evidence of causal mediation."])
    add("pattern-processing-speed-path", "Greater Hcy-SGM pattern expression was associated with poorer processing-speed performance in the serial mediation model (β=0.232, p=0.008).",
        "В модели последовательной медиации большая выраженность паттерна Hcy–SGM была связана с худшей скоростью обработки (β=0,232; p=0,008).",
        "greater_pattern_expression_associated_with_poorer_processing_speed", ["U50", "U62"], {"predictor": "Hcy-SGM pattern expression", "outcome": "poorer processing-speed performance on TMT-A"},
        knowledge_type="result", attrs={"beta": {"value": 0.232, "unit": None}, "B": {"value": 0.071, "unit": None}, "SE": {"value": 0.027, "unit": None}, "p_value": {"value": 0.008, "unit": None}},
        conditions=["TMT-A is coded so that a higher transformed time indicates poorer processing speed; observational path coefficient."])
    add("age-wmh-pattern-mediation", "WMH volume statistically mediated part of the age–Hcy-SGM pattern association; the indirect effect was 0.119 (95% CI 0.030–0.219), while the direct age association remained significant.",
        "Объём WMH статистически опосредовал часть связи возраста с паттерном Hcy–SGM; косвенный эффект составил 0,119 (95% ДИ 0,030–0,219), а прямая связь возраста оставалась значимой.",
        "wmh_partially_mediates_age_pattern_association", ["U47", "U48", "U54", "U61"], {"predictor": "age", "mediator": "WMH volume", "outcome": "Hcy-related SGM pattern expression"},
        knowledge_type="result", logic="conjunction", attrs={"indirect_effect": {"value": 0.119, "unit": None}, "indirect_effect_SE": {"value": 0.048, "unit": None}, "indirect_effect_95_CI": {"value": "0.030 to 0.219", "unit": None}, "total_effect": {"value": 0.418, "unit": None}, "direct_effect": {"value": 0.299, "unit": None}},
        claims=[
            {"predicate": "indirect_association_through", "roles": {"predictor": "age", "mediator": "WMH volume", "outcome": "Hcy-SGM pattern expression"}, "attrs": {"effect": {"value": 0.119, "unit": None}, "95%_CI": {"value": "0.030 to 0.219", "unit": None}}},
            {"predicate": "direct_association_remained", "roles": {"predictor": "age", "outcome": "Hcy-SGM pattern expression"}, "attrs": {"direct_effect": {"value": 0.299, "unit": None}, "95%_CI": {"value": "0.011 to 0.049", "unit": None}}},
        ], conditions=["Statistical mediation in observational data; the authors explicitly state that causal conclusions cannot be drawn."])
    add("serial-cognitive-mediation", "The serial indirect path from age through WMH volume and Hcy-SGM pattern expression to poorer processing speed was statistically significant (indirect effect 0.026, 95% bootstrap CI 0.001–0.069); adjustment for depressive symptoms did not remove it.",
        "Последовательный косвенный путь от возраста через объём WMH и выраженность паттерна Hcy–SGM к худшей скорости обработки был статистически значимым (косвенный эффект 0,026; 95% бутстрэп-ДИ 0,001–0,069); поправка на депрессивные симптомы не устранила его.",
        "age_wmh_pattern_serially_mediates_processing_speed_association", ["U49", "U50", "U48", "U62", "U67"], {"predictor": "age", "mediators": "WMH volume then Hcy-SGM pattern expression", "outcome": "poorer TMT-A processing-speed performance"},
        knowledge_type="result", attrs={"indirect_effect": {"value": 0.026, "unit": None}, "SE": {"value": 0.018, "unit": None}, "95%_bootstrap_CI": {"value": "0.001 to 0.069", "unit": None}, "depression_adjusted_effect": {"value": 0.027, "unit": None}},
        conditions=["Statistical serial mediation in an observational cohort, not proof of a causal pathway. Covariates included TIV, test timing, sex, education, APOE ε4, hypertension, smoking, VO2max, and B12; depression was added in follow-up."])
    add("cognitive-outcome-contrast", "The serial indirect effects were not statistically significant for residualized TMT-B executive function or SRT consistent long-term retrieval, unlike the processing-speed result.",
        "Последовательные косвенные эффекты не были статистически значимыми для остаточного показателя TMT-B (исполнительная функция) и устойчивого долговременного воспроизведения SRT, в отличие от результата по скорости обработки.",
        "serial_mediation_not_detected_for_other_cognitive_outcomes", ["U51", "U62"], {"tested_path": "age through WMH and Hcy-SGM pattern", "outcomes_without_significant_indirect_effect": "residualized TMT-B and SRT CLTR", "contrasted_outcome": "TMT-A processing speed"},
        knowledge_type="comparison", logic="contrast", attrs={"TMT_B_indirect_effect": {"value": -0.013, "unit": None}, "TMT_B_95_CI": {"value": "-0.050 to 0.010", "unit": None}, "SRT_indirect_effect": {"value": 0.005, "unit": None}, "SRT_95_CI": {"value": "-0.014 to 0.027", "unit": None}},
        claims=[
            {"predicate": "indirect_effect_not_statistically_significant", "roles": {"outcome": "residualized TMT-B executive-function score"}, "attrs": {"effect": {"value": -0.013, "unit": None}, "95%_CI": {"value": "-0.050 to 0.010", "unit": None}}},
            {"predicate": "indirect_effect_not_statistically_significant", "roles": {"outcome": "SRT consistent long-term retrieval score"}, "attrs": {"effect": {"value": 0.005, "unit": None}, "95%_CI": {"value": "-0.014 to 0.027", "unit": None}}},
        ], conditions=["The SRT total and direct effects were reported as significant; this does not make its serial indirect effect significant."])

    add("pattern-interpretation", "The authors interpret the Hcy-SGM pattern as a possible marker of cognitive aging and a potential link between vascular health and cognitive dysfunction in healthy older adults.",
        "Авторы трактуют паттерн Hcy–SGM как возможный маркер когнитивного старения и потенциальную связь сосудистого здоровья с когнитивной дисфункцией у здоровых пожилых людей.",
        "interpret_pattern_as_possible_marker_and_link", ["U6", "U53", "U67"], {"pattern": "Hcy-related SGM covariance pattern", "possible_role": "marker of cognitive aging and vascular-cognitive link"},
        knowledge_type="conclusion", modality="may", origin="authors’ qualified interpretation", conditions=["Potential interpretation, not validated diagnostic or prognostic performance."])
    add("relative-preservation-interpretation", "The authors interpret relative SSM increases in caudate, putamen, and pallidum as possible relative preservation; univariate analyses did not confirm significant positive volume associations in these regions.",
        "Авторы трактуют относительные повышения SSM для хвостатого ядра, скорлупы и бледного шара как возможное относительное сохранение; однофакторный анализ не подтвердил значимых положительных связей объёма в этих областях.",
        "interpret_relative_pattern_increases_as_possible_preservation", ["U43", "U57"], {"regions": "caudate, putamen, and pallidum", "pattern": "relative SSM increases", "univariate_test": "TIV-adjusted volume association"},
        knowledge_type="conclusion", modality="may", conditions=["Relative multivariate loadings must not be restated as absolute volume growth."])
    add("dementia-risk-interpretation", "The authors propose that the Hcy-related hippocampal and nucleus-accumbens pattern could be relevant to later dementia vulnerability, while stating that direct testing of the pattern as an early dementia-risk indicator is still needed.",
        "Авторы предполагают, что связанный с Hcy паттерн гиппокампа и прилежащего ядра может иметь отношение к последующей уязвимости к деменции, но отмечают необходимость прямой проверки паттерна как раннего индикатора риска.",
        "propose_but_not_validate_dementia_risk_indicator", ["U58", "U65"], {"candidate_pattern": "Hcy-related hippocampal and nucleus-accumbens SGM pattern", "candidate_outcome": "subsequent dementia vulnerability"},
        knowledge_type="conclusion", modality="could", conditions=["The study did not directly test dementia incidence or predictive accuracy; this remains a hypothesis for future research."])
    add("neurotoxicity-mechanism-hypothesis", "The discussion proposes Hcy-related neurotoxicity, blood-brain-barrier disruption, microvascular toxicity, excitotoxic or oxidative injury, and selective hippocampal or nucleus-accumbens vulnerability as possible mechanisms.",
        "В обсуждении как возможные механизмы предложены нейротоксичность Hcy, нарушение гематоэнцефалического барьера, токсическое воздействие на микрососуды, эксайтотоксическое или окислительное повреждение и избирательная уязвимость гиппокампа либо прилежащего ядра.",
        "candidate_neurotoxic_mechanisms", ["U59"], {"candidate_exposure": "homocysteine", "candidate_mechanisms": "blood-brain-barrier disruption, microvascular toxicity, excitotoxic and oxidative injury", "candidate_regions": "hippocampus and nucleus accumbens"},
        knowledge_type="assertion", modality="may", origin="mechanistic interpretation informed by prior laboratory and animal studies", conditions=["These mechanisms were not directly measured in the present human cohort."])
    add("vascular-mechanism-hypothesis", "The discussion proposes that Hcy-related vascular injury, including atherosclerosis, thrombosis, oxidative stress, inflammation, and endothelial injury, could contribute to brain lesions and WMH burden.",
        "В обсуждении предполагается, что сосудистое повреждение, связанное с Hcy, включая атеросклероз, тромбоз, окислительный стресс, воспаление и повреждение эндотелия, может способствовать поражениям мозга и нагрузке WMH.",
        "proposed_hcy_vascular_injury_mechanism", ["U60", "U61"], {"candidate_exposure": "high plasma Hcy", "candidate_process": "vascular injury", "candidate_intermediate": "WMH burden"},
        knowledge_type="assertion", modality="may", origin="authors’ interpretation with reference to prior studies", conditions=["Mechanistic pathway is proposed; vascular injury was not directly measured as a mediator here."])
    add("wmh-pathway-interpretation", "The authors interpret age-related WMH burden as a possible contributor to Hcy-related subcortical differences, but the observational mediation models do not establish causal influence.",
        "Авторы трактуют возрастную нагрузку WMH как возможный вклад в подкорковые различия, связанные с Hcy; однако наблюдательные медиационные модели не устанавливают причинное влияние.",
        "interpret_wmh_as_possible_contributor_without_causal_identification", ["U61", "U65"], {"age": "older age", "candidate_intermediate": "WMH burden", "pattern": "Hcy-related SGM differences"},
        knowledge_type="conclusion", modality="may", conditions=["Causal relationships cannot be concluded from these mediation results."])
    add("processing-speed-pathways-interpretation", "The authors propose two possible routes to poorer processing speed: Hcy-related SGM morphological differences and a WMH-related process that may exacerbate those differences; the association was observed for processing speed but not the other tested cognitive domains.",
        "Авторы предполагают два возможных пути к снижению скорости обработки: морфологические различия SGM, связанные с Hcy, и процесс, связанный с WMH, который может усиливать эти различия; связь обнаружена для скорости обработки, но не для других проверенных когнитивных доменов.",
        "propose_two_noncausal_routes_to_processing_speed_difference", ["U62", "U63"], {"candidate_exposure": "Hcy-related pattern", "candidate_routes": "SGM morphology and WMH burden", "outcome": "processing speed"},
        knowledge_type="conclusion", logic="contrast", modality="may", conditions=["The two-route explanation is interpretive; this study did not identify independent causal pathways."])
    add("effort-circuit-hypothesis", "The discussion speculates that processing-speed deficits could involve disruption of mesoaccumbal pathways relevant to effortful motivation, based on animal and human imaging studies.",
        "В обсуждении выдвигается предположение, что снижение скорости обработки может включать нарушение мезоаккумбального пути, связанного с мотивацией к усилию, на основании исследований животных и нейровизуализации человека.",
        "speculate_about_mesoaccumbal_circuit_and_processing_speed", ["U64"], {"candidate_circuit": "mesoaccumbal pathway", "candidate_construct": "effortful motivation", "candidate_outcome": "processing-speed deficits"},
        knowledge_type="assertion", modality="could", origin="cross-species interpretation based on cited studies", conditions=["Circuit disruption and motivation were not measured in this cohort."])
    add("generalizability-limitation", "The authors state that larger and more ethnically diverse cohorts are needed to test generalizability and whether other cognitive-domain associations emerge.",
        "Авторы указывают, что для проверки обобщаемости и возможных связей с другими когнитивными доменами нужны более крупные и этнически разнообразные когорты.",
        "need_larger_diverse_replication", ["U65"], {"current_sample": "160 participants; 95.0% White", "future_design": "larger and more ethnically diverse cohorts"},
        kind="action", knowledge_type="goal", status="unresolved", modality="needed", conditions=["Future research task; not an action completed by the present study."])
    add("causal-identification-limitation", "Although bootstrap mediation models showed indirect effects, the authors state that the findings do not permit clear causal conclusions and call for intervention and longitudinal neuroimaging studies.",
        "Хотя бутстрэп-медиационные модели показали косвенные эффекты, авторы подчёркивают, что результаты не позволяют сделать определённые причинные выводы, и призывают к интервенционным и продольным нейровизуализационным исследованиям.",
        "mediation_does_not_establish_causality_and_future_tests_needed", ["U65"], {"current_evidence": "observational mediation findings", "needed_designs": "intervention and longitudinal neuroimaging studies"},
        knowledge_type="limitation", modality="does not permit", conditions=["The paper calls for further work on whether Hcy-related regional volume differences lie on a causal pathway to cognitive decline, CVD, or dementia."])

    represented = {uid for item in records for uid in item["units"]}
    excluded = {}
    headings = {"U1", "U5", "U7", "U15", "U16", "U18", "U21", "U23", "U30", "U32", "U40", "U52", "U66"}
    metadata = {"U2": "Author metadata is retained in the full source, not modeled as scientific knowledge.",
                "U3": "Journal and publication year are retained as source metadata.",
                "U4": "DOI is retained as source metadata, not as scientific knowledge."}
    for uid in headings:
        excluded[uid] = "Section heading organizes the document; its content is represented by the adjacent source units."
    excluded.update(metadata)
    require(represented.isdisjoint(excluded), "A source unit is both represented and excluded")
    require(represented | set(excluded) == set(units), "Every non-reference source unit needs coverage accounting")
    return {
        "version": "pmc10002471-codex-manual-map-v1",
        "complete_source_reviewed": True,
        "complete_semantic_coverage": False,
        "table_cells_exhaustively_formalized": False,
        "knowledge": records,
        "transitions": [],
        "excluded_units": excluded,
        "source_limitations": [
            "Карта подготовлена Codex вручную из сохранённого полного английского Markdown; References оставлены в источнике и исключены из извлечения.",
            "Авторы и издательские метаданные, таблицы из отсутствующей в Markdown полной разметки и неподтверждённые детали рисунков не добавлялись; фигуры 1–3 представлены только по тексту подписей.",
            "Формализация не заявляется как исчерпывающе полная; все 67 фрагментов получили запись знаний или явную причину исключения.",
            "Результаты наблюдательные. Медиационный анализ и авторские механистические интерпретации не являются доказательством причинности.",
            "Расход токенов Codex неизвестен; провайдерские и локальные LLM, переводчик и эмбеддинги не использовались.",
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
    expected_hash = "3fef99e670facddc510de147c7b7244df3798cc5e72c33c26ab8542d5893e8b1"
    require(source_hash == expected_hash, "PMC10002471 source revision changed; refusing to author against a different text")
    source = prepare_source(ARTICLE_ID, text)
    require(source["references_excluded"] and source["offset_encoding"] == "unicode_codepoints", "Source boundary or offset encoding invalid")
    authored = build_authored(source)
    # Зависимости сформированы после всех знаний; убираем защитный маркер из локального черновика.
    authored["transitions"] = [
        {"sources": ["cohort-profile", "plasma-hcy-assay", "ssm-analysis-operation"], "target": "hcy-sgm-pattern", "usage": "method", "reason": "The cohort, measured plasma Hcy, and SSM analysis define the data and procedure that produced this multivariate pattern result.", "units": ["U17", "U19", "U33", "U34", "U41"]},
        {"sources": ["bootstrap-and-univariate-analysis", "regional-hcy-associations"], "target": "relative-preservation-interpretation", "usage": "result", "reason": "The TIV-adjusted regional analyses distinguish confirmed inverse associations from nonsignificant univariate increases, which is the basis for the cautious relative-preservation interpretation.", "units": ["U43", "U57"]},
        {"sources": ["blockwise-regression-method", "wmh-volume-and-tiv", "cohort-profile"], "target": "wmh-age-sex-associations", "usage": "method", "reason": "The stated regression blocks, derived WMH/TIV measures, and cohort define the adjusted model in which these associations were estimated.", "units": ["U29", "U36", "U44", "U45", "U46"]},
        {"sources": ["mediation-analysis-method", "age-wmh-path", "wmh-pattern-path"], "target": "age-wmh-pattern-mediation", "usage": "result", "reason": "The mediation result combines the tested age-to-WMH and WMH-to-pattern paths under the reported covariate model; it retains the direct age association.", "units": ["U37", "U47", "U48"]},
        {"sources": ["mediation-analysis-method", "age-wmh-path", "wmh-pattern-path", "pattern-processing-speed-path"], "target": "serial-cognitive-mediation", "usage": "result", "reason": "The serial mediation model evaluates the ordered age, WMH, pattern, and processing-speed path; its indirect effect is reported separately from each component path.", "units": ["U38", "U48", "U49", "U50"]},
        {"sources": ["serial-cognitive-mediation", "cognitive-outcome-contrast"], "target": "processing-speed-pathways-interpretation", "usage": "result", "reason": "The interpretation is limited to the observed processing-speed result and the explicit contrast with the nonsignificant indirect effects for residualized TMT-B and SRT.", "units": ["U51", "U62"]},
        {"sources": ["hcy-sgm-pattern", "wmh-age-sex-associations", "serial-cognitive-mediation", "causal-identification-limitation"], "target": "pattern-interpretation", "usage": "result", "reason": "The qualified conclusion summarizes the multivariate pattern and adjusted associations while preserving the paper's explicit causal limitation.", "units": ["U53", "U54", "U67"]},
        {"sources": ["regional-hcy-associations", "causal-identification-limitation"], "target": "dementia-risk-interpretation", "usage": "premise", "reason": "The proposed dementia-risk relevance is an extrapolation from regional findings and is explicitly left for direct future testing.", "units": ["U58", "U65"]},
        {"sources": ["age-wmh-pattern-mediation", "serial-cognitive-mediation", "causal-identification-limitation"], "target": "wmh-pathway-interpretation", "usage": "result", "reason": "The interpretation follows the fitted mediation associations but preserves the authors' statement that causal influence is not identified.", "units": ["U61", "U65"]},
    ]
    extraction_path, dependency_path = registered_prompt_paths(HISTORICAL_BINDING)
    prompts = (extraction_path.read_text(encoding="utf-8"), dependency_path.read_text(encoding="utf-8"))
    artifacts = prepare_manual_map(ARTICLE_ID, text, source_hash, authored, *prompts,
                                  prompt_binding_value=HISTORICAL_BINDING)
    graph = artifacts["map.json"]["graph"]
    require(len(artifacts["coverage.json"]["units"]) == len(source["units"]), "Coverage accounting incomplete")
    require(artifacts["coverage.json"]["references_excluded"] is True, "References were not excluded")
    artifacts["map.json"]["article_title"] = "Association of homocysteine-related subcortical brain atrophy with white matter lesion volume and cognition in healthy aging"
    artifacts["source-review.json"] = {
        "article_id": ARTICLE_ID, "doi": DOI, "source_sha256": source_hash,
        "prior_heldout_annotation_run_id": PRIOR_HELDOUT_RUN_ID,
        "prior_heldout_annotation_prompt_versions": {"extraction": "4", "dependencies": "16"},
        "same_article_reannotation": True, "eligible_as_new_training_source": False,
        "full_text_reviewed": True, "source_units": len(source["units"]),
        "references_excluded_from_extraction": True, "offset_encoding": "unicode_codepoints",
        "complete_semantic_coverage": False, "all_tables_exhaustively_formalized": False,
        "expert_validated": False, "author": "Codex", "generation_method": "manual_from_full_english_text",
        "external_llm_calls": 0, "local_llm_calls": 0, "translation_llm_calls": 0, "embedding_calls": 0,
        "token_usage": None,
    }
    artifacts["validation.json"].update({"doi": DOI, "source_sha256": source_hash,
        "external_llm_calls": 0, "local_llm_calls": 0, "translation_llm_calls": 0,
        "embedding_calls": 0, "scientific_accuracy": "not_assessed"})
    artifacts["report.ru.md"] = "\n".join([
        "# PMC10002471: альтернативная ручная аннотация",
        "",
        f"**DOI:** `{DOI}`  ",
        f"**SHA-256 источника:** `{source_hash}`  ",
        f"**Запуск:** `{artifacts['map.json']['run_id']}`  ",
        f"**Схема:** 6; **промпты:** KM.TEXT_TO_MAP 3 и зависимости 15; **узлы знаний:** {len(graph['knowledge'])}; **утверждения:** {graph['analysis']['statement_count']}; **переходы:** {len(graph['transitions'])}; **глубина DAG:** {graph['analysis']['depth']}",
        "",
        f"Эта статья уже была отложенной целью прежнего sealed-эксперимента; там сохранена отдельная карта `{PRIOR_HELDOUT_RUN_ID}` по промптам 4/16. Текущая карта — альтернативная ручная разметка того же текста по зарегистрированным промптам 3/15, а не независимый источник. Её нельзя добавлять в обучающую выборку или считать новой проверкой прогноза.",
        "",
        "Карта вручную составлена Codex по полному сохранённому английскому тексту. Внешние и локальные LLM, переводчик и эмбеддинги не вызывались. Расход токенов текущей сессии неизвестен и не оценивался.",
        "",
        "## Что отражено",
        "",
        "Разделены: сведения из предыдущей литературы, цель и гипотеза авторов, характеристики выборки, методы измерений и анализа, результаты текущей когорты, отрицательные результаты, интерпретации и нерешённые исследовательские задачи. Сохранены числовые оценки, единицы, направления шкал, набор ковариат и ограничения причинной интерпретации.",
        "",
        "Каждый из 67 фрагментов до References имеет либо связь с одним или несколькими знаниями, либо явную причину исключения. Координаты источника вычислены в Unicode code points; полные References сохранены в источнике и не использованы как доказательство.",
        "",
        "## Границы",
        "",
        "Семантическая полнота не заявлена; таблицы и графические данные, отсутствующие в текстовой версии, не реконструировались. Исследование наблюдательное: пути медиации и механистические объяснения не доказывают причинность. Паттерн не проверялся как диагностический или прогностический тест. Научная точность требует экспертной оценки.",
        "",
        "Результат предназначен только для диагностики различий ручной формализации и версий промптов. Предыдущая целевая карта и запечатанный прогноз не изменены; обучение и Neo4j не использовались.",
        "",
    ])
    artifacts["manifest.json"] = {
        "schema_version": 1, "pmc_id": ARTICLE_ID, "doi": DOI,
        "artifact_role": "same_article_cross_prompt_reannotation_not_training_data",
        "prior_heldout_run_id": PRIOR_HELDOUT_RUN_ID, "eligible_as_new_training_source": False,
        "article_id": artifacts["map.json"]["article_id"], "run_id": artifacts["map.json"]["run_id"],
        "source_sha256": source_hash, "prompt_binding": {
            "prompt": artifacts["map.json"]["prompt"],
            "dependency_prompt": artifacts["map.json"]["dependency_prompt"],
        },
        "generation": artifacts["map.json"]["generation"], "needs_expert_review": True,
        "files": {name: sha256((value if isinstance(value, bytes) else value.encode("utf-8") if isinstance(value, str)
                                else json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))).hexdigest()
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
