"""Авторская формализация отбора и наблюдения WHICAP по исходным фрагментам."""


def append_sampling_records(add):
    # Числовые роли именуются фазой и группой; противоречащие оценки не усредняются.
    def record(key, en, ru, predicate, units, roles, values=None, kind='state', type='observation'):
        add(key, en, ru, predicate, units, roles=roles, kind=kind, type=type,
            attrs={name: {'value': value, 'unit': unit} for name, value, unit in (values or [])})

    record('background-progression-context',
           'The introduction cites annual MCI-to-dementia progression of 12-17% in clinic studies versus 4-15% in population/community studies; these are cited background ranges, not WHICAP estimates.',
           'Введение цитирует ежегодное прогрессирование MCI к деменции 12–17% в клинических и 4–15% в популяционных исследованиях; это фоновые диапазоны литературы, не оценки WHICAP.',
           'cited background rate ranges', ['U5'], {'evidence_origin':'studies cited by WHICAP introduction','outcome':'MCI-to-dementia progression'}, [('clinic_min','12','percent per year'),('clinic_max','17','percent per year'),('population_min','4','percent per year'),('population_max','15','percent per year')])
    record('background-reversion-range',
           'The introduction cites normal reclassification in 14-40% of population-based MCI cohorts, more frequently than in clinical cohorts; the cited range is separate from WHICAP results.',
           'Введение цитирует возврат к нормальной классификации у 14–40% популяционных когорт MCI, чаще, чем в клинических; диапазон отделён от собственных результатов WHICAP.',
           'cited background reclassification range', ['U5','U7'], {'evidence_origin':'studies cited by WHICAP introduction','outcome':'normal reclassification'}, [('minimum','14','percent'),('maximum','40','percent')])
    record('methodological-comparability-limit',
           'Authors identify diagnosis procedure, suitability of retrospective data, memory versus nonmemory and single versus multiple domain distinctions, impairment cutoff, demographic norms, complaint and function requirements, and knowledge of prior diagnoses as sources of cross-study variation.',
           'Авторы выделяют процедуру диагноза, пригодность ретроспективных данных, различения памяти/других областей и одной/нескольких областей, порог, демографические нормы, требования жалоб и функции и знание прежнего диагноза как источники различий между исследованиями.',
           'author-described methodological heterogeneity', ['U7','U13'], {'comparison':'MCI studies'}, type='limitation')
    record('figure-selection-counts',
           'Figure 1 reports baseline cohort sizes 2125 and 2183, 478 excluded for insufficient initial data, 3215 remaining after baseline dementia exclusion and 2430 remaining after no-follow-up exclusion.',
           'Рисунок 1 сообщает исходные когорты 2125 и 2183, исключение 478 из-за недостаточных исходных данных, 3215 после исключения исходной деменции и 2430 после исключения отсутствия наблюдения.',
           'reported flowchart counts', ['U17'], {'population':'WHICAP selection flow'}, [('cohort_1992','2125','participants'),('cohort_1999','2183','participants'),('insufficient_initial','478','participants'),('after_dementia','3215','participants'),('after_no_followup','2430','participants')])
    record('memory-nonmemory-incidence',
           'Over 7504.9 person-years, WHICAP observed 379 incident MCI cases: 170 memory-involved cases, rate 2.3 per 100 person-years (95% CI 1.9-2.6), and 209 nonmemory cases, rate 2.8 (95% CI 2.4-3.2). Printed percentages are rate notation here.',
           'За 7504,9 человеко-лет WHICAP наблюдал 379 случаев MCI: 170 с памятью, частота 2,3 на 100 человеко-лет (95% ДИ 1,9–2,6), и 209 без памяти, частота 2,8 (95% ДИ 2,4–3,2). Печатные проценты здесь обозначают частоту.',
           'reported incident case and rate contrast', ['U48','U50'], {'population':'WHICAP without baseline MCI','phase':'incident MCI follow-up'}, [('exposure','7504.9','person-year'),('total_cases','379','cases'),('memory_cases','170','cases'),('nonmemory_cases','209','cases'),('memory_rate','2.3','per 100 person-years'),('memory_ci_low','1.9','per 100 person-years'),('memory_ci_high','2.6','per 100 person-years'),('nonmemory_rate','2.8','per 100 person-years'),('nonmemory_ci_low','2.4','per 100 person-years'),('nonmemory_ci_high','3.2','per 100 person-years')], type='comparison')
    record('amnestic-mcdm-rate-difference',
           'Amnestic MCI incidence rate 1.4 exceeded MCDM rate 0.87 per 100 person-years; reported difference 0.53 (95% CI 0.19-0.87) was significant.',
           'Частота амнестического MCI 1,4 превышала частоту MCDM 0,87 на 100 человеко-лет; сообщённая разность 0,53 (95% ДИ 0,19–0,87) значима.',
           'reported incidence rate difference', ['U50'], {'population':'WHICAP without baseline MCI','comparison':'amnestic MCI versus MCDM'}, [('amnestic_rate','1.4','per 100 person-years'),('mcdm_rate','0.87','per 100 person-years'),('difference','0.53','per 100 person-years'),('difference_ci_low','0.19','per 100 person-years'),('difference_ci_high','0.87','per 100 person-years')], type='comparison')

    record('sampling-frame',
           'WHICAP recruited Medicare recipients aged at least 65 in three contiguous Northern Manhattan census tracts; people who spoke neither English nor Spanish were excluded.',
           'WHICAP набирал получателей Medicare от 65 лет из трёх соседних переписных участков Северного Манхэттена; не говорившие ни по-английски, ни по-испански исключались.',
           'sampling eligibility', ['U13'], {'population': 'Northern Manhattan Medicare recipients', 'language': 'English or Spanish'}, [('minimum_age', '65', 'year')], type='definition')
    record('recruitment-waves',
           'Combine community cohorts recruited beginning in 1992 and 1999; follow-up waves were approximately 18 to 30 months apart, and brain donation was offered beginning in 2002.',
           'Объединить общественные когорты набора с 1992 и 1999 годов; волны наблюдения разделяли примерно 18–30 месяцев, с 2002 года предлагали донорство мозга.',
           'performed recruitment and follow-up', ['U15'], {'population': 'WHICAP two recruitment cohorts'}, [('wave_min_interval', '18', 'month'), ('wave_max_interval', '30', 'month')], kind='action', type='operation')
    record('sample-selection-flow',
           'Of 4308 potential participants, 3830 had sufficient initial information; exclude 615 with baseline dementia and 785 without longitudinal data, then 66 with insufficient follow-up diagnostic data, leaving 2364.',
           'Из 4308 потенциальных участников 3830 имели достаточные исходные данные; исключены 615 с исходной деменцией, 785 без продольных данных и затем 66 без достаточных диагностических данных наблюдения; осталось 2364.',
           'observed selection counts', ['U15'], {'population': 'WHICAP selection flow'},
           [('potential', '4308', 'participants'), ('sufficient_initial', '3830', 'participants'), ('baseline_dementia_excluded', '615', 'participants'), ('no_longitudinal_excluded', '785', 'participants'), ('insufficient_followup_excluded', '66', 'participants'), ('final_sample', '2364', 'participants')])
    record('no-followup-reasons',
           'Among 785 participants without longitudinal data, 38% refused, 24% died, 20% could not be located, 11% moved, 6% could not be scheduled, and 1% had another reason.',
           'Среди 785 без продольных данных 38% отказались, 24% умерли, 20% не удалось найти, 11% переехали, 6% не удалось назначить визит, 1% имели другую причину.',
           'reported attrition distribution', ['U15'], {'population': '785 without longitudinal data'},
           [(name, value, 'percent') for name, value in [('refusal','38'),('death','24'),('unlocated','20'),('moved','11'),('unscheduled','6'),('other','1')]])
    record('followup-denominator',
           'Reported follow-up was 76% including deaths and 81% among those alive at follow-up; these denominators are different.',
           'Сообщённый охват наблюдением — 76% с учётом умерших и 81% среди живых к моменту наблюдения; знаменатели различаются.',
           'follow-up proportions', ['U15'], {'population': 'WHICAP initial eligible follow-up population'}, [('including_deaths','76','percent'),('alive','81','percent')])
    record('selection-age-education',
           'The selection paragraph reports final-sample age 75.8 (SD 6.4) and schooling 10.0 (SD 4.8) years versus 76.6 (SD 6.8) and 9.2 (SD 4.4) in 1329 excluded participants; retained participants were younger and better educated.',
           'Абзац отбора сообщает возраст включённых 75,8 (SD 6,4) и образование 10,0 (SD 4,8) лет против 76,6 (SD 6,8) и 9,2 (SD 4,4) у 1329 исключённых; включённые моложе и более образованы.',
           'reported selection contrast', ['U15'], {'included': 'WHICAP final sample', 'excluded': 'missing-data or no-follow-up group'},
           [('included_age','75.8','year'),('included_age_sd','6.4','year'),('excluded_age','76.6','year'),('excluded_age_sd','6.8','year'),('included_education','10.0','year'),('included_education_sd','4.8','year'),('excluded_education','9.2','year'),('excluded_education_sd','4.4','year'),('excluded_n','1329','participants')], type='comparison')
    record('selection-sex-and-burden',
           'Women comprised 68.6% of retained versus 64.9% of excluded participants; racial composition did not differ and excluded participants did not have more medical illnesses on the summary measure.',
           'Женщины составляли 68,6% включённых против 64,9% исключённых; этнический состав не различался, а исключённые не имели большего медицинского бремени по сводной мере.',
           'reported selection contrast', ['U15','U19'], {'included': 'WHICAP final sample', 'excluded': 'excluded participants'}, [('included_women','68.6','percent'),('excluded_women','64.9','percent')], type='comparison')
    record('no-followup-cognitive-selection',
           'Participants without follow-up more often had scores below the 1.5-SD normative cutoff than retained participants: memory 25 versus 17%, executive 21.5 versus 13%, visuospatial 21.5 versus 17.4%, language 23.1 versus 17.5%.',
           'Без наблюдения чаще встречались результаты ниже порога 1,5 SD, чем у включённых: память 25 против 17%, исполнительная функция 21,5 против 13%, зрительно-пространственная 21,5 против 17,4%, язык 23,1 против 17,5%.',
           'reported selection contrast', ['U19'], {'excluded': 'without follow-up', 'included': 'WHICAP final sample'},
           [(group+'_'+domain,value,'percent') for domain,a,b in [('memory','25','17'),('executive','21.5','13'),('visuospatial','21.5','17.4'),('language','23.1','17.5')] for group,value in [('excluded',a),('included',b)]], type='comparison')
    record('observed-followup-interval',
           'In the final sample, mean time between follow-up visits was 24.3 months (SD 6.4).',
           'В окончательной выборке средний интервал между визитами составлял 24,3 месяца (SD 6,4).',
           'observed follow-up interval', ['U19'], {'population': 'WHICAP final sample'}, [('mean_interval','24.3','month'),('interval_sd','6.4','month')])
    record('reevaluation-distribution',
           'Numbers of reevaluations and participants were 1:823, 2:901, 3:192, 4:174, 6:165, 7:89, 8:9, 9:11. No five-reevaluation category is reported.',
           'Число повторных обследований и участников: 1:823, 2:901, 3:192, 4:174, 6:165, 7:89, 8:9, 9:11. Категория пяти обследований не приведена.',
           'observed reevaluation distribution', ['U19'], {'population': 'WHICAP final sample'}, [('visits_'+v,n,'participants') for v,n in [('1','823'),('2','901'),('3','192'),('4','174'),('6','165'),('7','89'),('8','9'),('9','11')]])
    record('death-autopsy-selection',
           'During follow-up 388 of 2364 participants died (16.4%); 27 of those who died were autopsied (7%).',
           'В наблюдении умерли 388 из 2364 (16,4%); вскрытие выполнено у 27 умерших (7%).',
           'observed nested sample counts', ['U19'], {'parent_population': 'WHICAP final sample', 'autopsy_denominator': 'participants who died'}, [('deaths','388','participants'),('death_percent','16.4','percent'),('autopsies','27','participants'),('autopsy_percent_of_deaths','7','percent')])
    record('adl-operational-cutoff',
           'WHICAP preserved functioning means difficulty in fewer than three of six daily-function items, using participant or collateral information; the cutoff captures 95% of the normative sample.',
           'Сохранная функция WHICAP означает трудности менее чем в трёх из шести повседневных пунктов по данным участника или информанта; порог охватывает 95% нормативной выборки.',
           'operational functional criterion', ['U19','U21'], {'criterion': 'WHICAP preserved-daily-function criterion'}, [('items','6','items'),('exclusive_difficulty_limit','3','items'),('normative_coverage','95','percent')], type='definition')
    record('complaint-operational-cutoff',
           'WHICAP memory complaint is at least one reported problem among eleven memory-difficulty items.',
           'Жалоба на память WHICAP — хотя бы одна сообщённая проблема среди одиннадцати пунктов трудностей памяти.',
           'operational complaint criterion', ['U21'], {'criterion': 'memory complaint'}, [('items','11','items'),('minimum_positive','1','items')], type='definition')
    record('blinded-consensus',
           'After each assessment, physicians and neuropsychologists reached DSM-III-R dementia consensus using clinical and cognitive data; at follow-up they were shielded from prior consensus diagnoses.',
           'После каждого обследования врачи и нейропсихологи согласовывали диагноз деменции по DSM-III-R и клиническим/когнитивным данным; при наблюдении прежние согласованные диагнозы были скрыты.',
           'performed diagnostic procedure', ['U21'], {'procedure': 'WHICAP dementia consensus', 'blinding': 'prior consensus diagnoses'}, kind='action', type='operation')
    record('psychiatric-inclusion',
           'WHICAP assessed current and past psychiatric conditions; depression and other psychiatric disorders were not exclusion criteria.',
           'WHICAP оценивал текущие и прежние психиатрические состояния; депрессия и другие психические расстройства не служили критериями исключения.',
           'reported psychiatric inclusion policy', ['U19'], {'population': 'WHICAP enrolled participants'})
    record('results-sample-profile',
           'The Results section reports mean age 76.1 (SD 6.2) years and schooling 10.0 (SD 4.8) for 2364 participants; age differs from the selection paragraph and is preserved separately.',
           'Раздел результатов сообщает возраст 76,1 (SD 6,2) и образование 10,0 (SD 4,8) лет у 2364 участников; возраст отличается от абзаца отбора и сохранён отдельно.',
           'reported sample profile', ['U29','U15'], {'population': 'WHICAP final sample', 'report_location': 'Results sample characteristics'}, [('n','2364','participants'),('age','76.1','year'),('age_sd','6.2','year'),('education','10.0','year'),('education_sd','4.8','year')])
    record('results-duration-and-genotype',
           'The final cohort had a mean 2.3 follow-up evaluations and 4.7 years follow-up (SD 2.8); APOE genotype was available for 2067 participants (87%), distinct from the 1572-person MCI-risk subset.',
           'В окончательной когорте в среднем 2,3 повторных обследования и 4,7 года наблюдения (SD 2,8); APOE доступен для 2067 (87%), что отличается от подвыборки риска MCI из 1572.',
           'reported follow-up and data availability', ['U29','U76'], {'population': 'WHICAP final sample'}, [('mean_evaluations','2.3','evaluations'),('mean_followup','4.7','year'),('followup_sd','2.8','year'),('genotyped','2067','participants'),('genotyped_percent','87','percent')])
    record('results-cohort-composition',
           'Among 2364 participants, 28.4% were non-Hispanic white, 32.6% non-Hispanic black and 39.0% Hispanic; 68.6% were women. Only 8% of Hispanic participants were interviewed and tested in English.',
           'Среди 2364 участников 28,4% были нелатиноамериканскими белыми, 32,6% нелатиноамериканскими чернокожими и 39,0% латиноамериканскими; 68,6% — женщины. Только 8% латиноамериканских участников проходили интервью и тестирование на английском.',
           'reported cohort composition', ['U29'], {'population':'WHICAP final sample'}, [('n','2364','participants'),('nonhispanic_white','28.4','percent'),('nonhispanic_black','32.6','percent'),('hispanic','39.0','percent'),('women','68.6','percent'),('hispanic_tested_english','8','percent')], type='comparison')
    record('autopsy-subset-selection',
           'The 27 autopsied participants were older (79.3, SD 6.8 years) and more educated (12.5, SD 4.7 years) than the 2337 nonautopsied participants (76.1, SD 6.2; 9.9, SD 4.8); ethnicity, sex and MCI proportions did not differ.',
           '27 участников с вскрытием были старше (79,3; SD 6,8 года) и образованнее (12,5; SD 4,7 года), чем 2337 без вскрытия (76,1; SD 6,2; 9,9; SD 4,8); этнический состав, пол и доля MCI не различались.',
           'reported autopsy selection contrast', ['U19'], {'autopsied':'WHICAP autopsy subset','comparison':'nonautopsied participants'}, [('autopsy_n','27','participants'),('nonautopsy_n','2337','participants'),('autopsy_age','79.3','year'),('autopsy_age_sd','6.8','year'),('nonautopsy_age','76.1','year'),('nonautopsy_age_sd','6.2','year'),('autopsy_education','12.5','year'),('autopsy_education_sd','4.7','year'),('nonautopsy_education','9.9','year'),('nonautopsy_education_sd','4.8','year')], type='comparison')
    record('clinical-medical-evaluation',
           'At baseline and each follow-up, a physician recorded medical history and medications using a semistructured format and performed neurological and physical examinations including extrapyramidal signs and functional status.',
           'На исходном и каждом повторном визите врач полуструктурированно записывал анамнез и лекарства и проводил неврологический и физический осмотр, включая экстрапирамидные признаки и функцию.',
           'performed repeated clinical assessment', ['U19'], {'population':'WHICAP participants','phase':'baseline and each follow-up'}, type='method', kind='action')
    record('psychiatric-assessment-method',
           'Current depression was assessed with nine DSM-IV-aligned questions and ten CES-D symptom items; past depression, anxiety, psychosis, hallucinations, delusions, hospitalization, psychiatric medication and alcohol or drug dependence were also assessed. Psychiatric disorders did not exclude enrollment.',
           'Текущую депрессию оценивали девятью вопросами по DSM-IV и десятью пунктами CES-D; также оценивали прежнюю депрессию, тревогу, психоз, галлюцинации, бред, госпитализацию, психиатрические лекарства и зависимость от алкоголя или наркотиков. Психические расстройства не исключали участие.',
           'psychiatric assessment protocol', ['U19'], {'population':'WHICAP participants'}, [('current_depression_questions','9','items'),('symptom_scale_items','10','items')], type='method', kind='action')
    record('neuropsychological-test-battery',
           'The battery assessed learning and memory, orientation, reasoning, language and visuospatial abilities using Selective Reminding, BVRT, MMSE items, WAIS-R Similarities, Mattis Identities and Oddities, Boston Naming, Controlled Word Association, BDAE fluency/repetition/comprehension and Rosen Drawing; norms adjusted for age, education, sex and ethnicity.',
           'Батарея оценивала обучение и память, ориентировку, мышление, язык и зрительно-пространственные способности тестами Selective Reminding, BVRT, заданиями MMSE, сходствами WAIS-R, Identities and Oddities Mattis, Boston Naming, Controlled Word Association, беглостью/повторением/пониманием BDAE и рисованием Rosen; нормы учитывали возраст, образование, пол и этническую группу.',
           'neuropsychological measurement protocol', ['U21'], {'population':'WHICAP participants','domains':'memory; orientation; reasoning; language; visuospatial'}, type='method', kind='action')
    record('informant-measurement-context',
           'Daily-function information was supplied primarily by participants (97%); informants were primary for 3%, a group more likely to have function complaints, memory complaints and MCI. Informants were present at 6.7% of initial interviews and at some visit for 18% of participants.',
           'Данные о повседневной функции в основном сообщали участники (97%); у 3% основным источником был информант, и в этой группе чаще отмечались функциональные и мнемонические жалобы и MCI. Информант присутствовал на 6,7% исходных интервью и хотя бы на одном визите у 18% участников.',
           'reported measurement-source distribution', ['U29'], {'population':'WHICAP final sample','instrument':'daily-function and memory complaints'}, [('participant_primary','97','percent'),('informant_primary','3','percent'),('informant_initial_presence','6.7','percent'),('informant_any_visit_presence','18','percent')], type='comparison')
    record('baseline-medical-profile',
           'At initial visit, reported histories were hypertension 74.2%, heart disease 36.3%, diabetes 23.1% and stroke 8.7%.',
           'На исходном визите сообщались: гипертония в анамнезе 74,2%, болезнь сердца 36,3%, диабет 23,1%, инсульт 8,7%.',
           'reported baseline medical profile', ['U29'], {'population':'WHICAP final sample','phase':'initial visit'}, [('hypertension','74.2','percent'),('heart_disease','36.3','percent'),('diabetes','23.1','percent'),('stroke','8.7','percent')])
    record('recruitment-cohort-differences',
           'Compared with the 1992 cohort, the 1999 cohort had more education (10.9 vs 8.6 years, p<0.001), fewer Hispanic participants (33.4 vs 47.3%) and more non-Hispanic white participants (33.8 vs 20.3%), more stroke (9.8 vs 7.1%) and heart disease (39.2 vs 32.1%), similar hypertension and diabetes, lower baseline MCI (21.8 vs 26.9%, p=0.005), and shorter follow-up (3.3 vs 6.7 years).',
           'По сравнению с когортой 1992 года в когорте 1999 года было больше лет образования (10,9 против 8,6; p<0,001), меньше латиноамериканских участников (33,4 против 47,3%) и больше нелатиноамериканских белых (33,8 против 20,3%), чаще инсульт (9,8 против 7,1%) и болезнь сердца (39,2 против 32,1%), сходная частота гипертонии и диабета, ниже исходная распространённость MCI (21,8 против 26,9%; p=0,005) и короче наблюдение (3,3 против 6,7 года).',
           'reported recruitment-cohort contrast', ['U29'], {'population':'WHICAP recruitment cohorts','cohort_1992':'recruited 1992','cohort_1999':'recruited 1999'},
           [('education_1992','8.6','year'),('education_1999','10.9','year'),('hispanic_1992','47.3','percent'),('hispanic_1999','33.4','percent'),('white_1992','20.3','percent'),('white_1999','33.8','percent'),('stroke_1992','7.1','percent'),('stroke_1999','9.8','percent'),('heart_1992','32.1','percent'),('heart_1999','39.2','percent'),('baseline_mci_1992','26.9','percent'),('baseline_mci_1999','21.8','percent'),('followup_1992','6.7','year'),('followup_1999','3.3','year')], type='comparison')
