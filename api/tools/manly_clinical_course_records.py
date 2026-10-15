"""Изменения классификации, валидация и ограничения WHICAP из полного текста."""


def append_clinical_course_records(add):
    def record(key, en, ru, predicate, units, roles, values=(), type='observation', kind='state', claims=None, logic='single'):
        add(key, en, ru, predicate, units, roles=roles, kind=kind,
            type='goal' if type == 'task' else 'assertion' if type == 'hypothesis' else type,
            claims=claims, logic=logic,
            status='unresolved' if type == 'task' else None,
            modality='possible' if type == 'hypothesis' else None,
            attrs={n: {'value': v, 'unit': u} for n, v, u in values})

    add('abstract-outcome-summary',
        'The article abstract reports overall incidence and follow-up course summaries for the WHICAP cohort; the reported course phase is not specified more narrowly in the abstract.',
        'Аннотация статьи сообщает общие частоты и ход наблюдения когорты WHICAP; фаза для распределения исходов точнее в аннотации не указана.',
        'abstract-reported outcome summary', ['U3'],
        roles={'population':'WHICAP cohort','evidence_origin':'direct observation in this primary study','report_location':'article abstract'},
        type='comparison', logic='conjunction', claims=[
            {'predicate':'progressed from normal to MCI','roles':{'baseline_group':'normal at baseline','phase':'follow-up'},
             'attrs':{'proportion':{'value':'21','unit':'percent'},'annual_incidence_rate':{'value':'5.1','unit':'percent per year'},'confidence_low':{'value':'4.6','unit':'percent per year'},'confidence_high':{'value':'5.6','unit':'percent per year'},'exposure_time':{'value':'10517','unit':'person-years'}}},
            {'predicate':'progressed from baseline MCI to AD','roles':{'baseline_group':'MCI at baseline','phase':'follow-up'},
             'attrs':{'proportion':{'value':'21.8','unit':'percent'},'annual_incidence_rate':{'value':'5.4','unit':'percent per year'},'confidence_low':{'value':'4.7','unit':'percent per year'},'confidence_high':{'value':'6.3','unit':'percent per year'}}},
            {'predicate':'remained MCI','roles':{'baseline_group':'MCI at baseline','phase':'follow-up, abstract phase unspecified'},'attrs':{'proportion':{'value':'47','unit':'percent'}}},
            {'predicate':'reverted to normal','roles':{'baseline_group':'MCI at baseline','phase':'follow-up, abstract phase unspecified'},'attrs':{'proportion':{'value':'31','unit':'percent'}}},
            {'predicate':'relative likelihood of AD development','roles':{'comparison':'baseline MCI versus normal elderly','outcome':'AD at follow-up'},'attrs':{'relative_likelihood':{'value':'2.8','unit':'fold'}}},
        ])
    add('table-abbreviation-glossary',
        'Table notes define the abbreviations MCI, CI, AD, MCD, MCDM and MCDN used in the reported results.',
        'Примечания к таблицам расшифровывают сокращения MCI, CI, AD, MCD, MCDM и MCDN, используемые в результатах.',
        'abbreviation glossary', ['U46','U74','U101','U120','U121','U122','U123'],
        roles={'document':'WHICAP tables'}, type='definition', logic='conjunction', claims=[
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'MCI','expansion':'mild cognitive impairment'},'units':['U46','U74','U101','U120']},
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'CI','expansion':'confidence interval'},'units':['U46','U74','U101','U120']},
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'AD','expansion':"Alzheimer's disease"},'units':['U101']},
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'MCD','expansion':'multiple cognitive domains'},'units':['U46']},
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'MCDM','expansion':'multiple cognitive domains with memory impairment'},'units':['U121']},
            {'predicate':'abbreviation_expands_to','roles':{'abbreviation':'MCDN','expansion':'multiple cognitive domains without memory impairment'},'units':['U122','U123']},
        ])

    record('reversion-all-visits',
           'Among 564 baseline-MCI participants across all follow-ups, 170 (30.2%) had neither MCI nor dementia at any follow-up; 264 (46.8%) remained MCI without normal reversion or dementia progression.',
           'Среди 564 с исходным MCI за все визиты 170 (30,2%) не имели MCI или деменции ни на одном повторном визите; 264 (46,8%) оставались с MCI без возврата к норме и прогрессирования к деменции.',
           'reported diagnostic course', ['U127'], {'population':'WHICAP baseline MCI', 'phase':'all available follow-ups'},
           [('baseline_n','564','participants'),('normal_n','170','participants'),('normal_percent','30.2','percent'),('persistent_n','264','participants'),('persistent_percent','46.8','percent')])
    record('first-followup-course',
           'At first follow-up of 564 baseline-MCI participants: 255 (45.2%) normal, 230 (40.8%) MCI, 72 (12.8%) AD and 7 (1.2%) non-AD dementia.',
           'На первом повторном визите 564 участников с исходным MCI: норма 255 (45,2%), MCI 230 (40,8%), AD 72 (12,8%), другая деменция 7 (1,2%).',
           'reported diagnostic course', ['U127'], {'population':'WHICAP baseline MCI', 'phase':'first follow-up only'},
           [(n,v,u) for n,v,u in [('normal_n','255','participants'),('normal_percent','45.2','percent'),('mci_n','230','participants'),('mci_percent','40.8','percent'),('ad_n','72','participants'),('ad_percent','12.8','percent'),('other_dementia_n','7','participants'),('other_dementia_percent','1.2','percent')]])
    record('course-observation-duration',
           'Baseline-MCI participants subsequently normal had mean follow-up 3.4 years and 1.7 visits, versus 4.7 years/2.3 visits for persistent MCI and 5.8 years/2.9 visits for dementia; these observation durations differ.',
           'У исходного MCI с последующей нормой среднее наблюдение 3,4 года и 1,7 визита, при сохранении MCI — 4,7 года/2,3 визита, при деменции — 5,8 года/2,9 визита; длительности различаются.',
           'reported observation-duration contrast', ['U127'], {'population':'WHICAP baseline MCI', 'phase':'all available follow-ups'},
           [(g+'_'+n,v,u) for g,y,k in [('normal','3.4','1.7'),('mci','4.7','2.3'),('dementia','5.8','2.9')] for n,v,u in [('years',y,'year'),('visits',k,'visits')]], type='comparison')
    record('reversion-overlapping-criteria',
           'Among MCI participants reverting to normal, 21% no longer met functional-complaint criteria, 35% memory-complaint criteria and 67% neuropsychological criteria; these proportions overlap.',
           'Среди вернувшихся к нормальной классификации 21% больше не соответствовали функциональным критериям, 35% критериям жалоб на память, 67% нейропсихологическим; доли пересекаются.',
           'reported overlapping criterion changes', ['U127','U156'], {'population':'WHICAP baseline MCI reverting to normal'}, [('functional','21','percent'),('complaint','35','percent'),('cognitive','67','percent')])
    record('reversion-exclusive-criteria',
           'Reported exclusive reasons for normal reclassification were cognitive criteria only 48%, functional criteria only 12% and memory complaint only 17%; the remainder involved multiple criteria.',
           'Исключительные причины нормальной переклассификации: только когнитивные критерии 48%, только функциональные 12%, только жалобы на память 17%; остальные — несколько критериев.',
           'reported exclusive criterion changes', ['U156','U158'], {'population':'WHICAP baseline MCI reverting to normal'}, [('cognitive_only','48','percent'),('functional_only','12','percent'),('complaint_only','17','percent')])
    record('isolated-versus-multidomain-reversion',
           'Across available visits, isolated-domain MCI reverted to normal more often than multidomain MCI: 38.0% versus 19.3%, chi-square 22.2, df 1, n=557, p<0.001; comparisons within the isolated and within multidomain categories were not significant.',
           'За доступные визиты изолированный MCI чаще возвращался к норме, чем многодоменный: 38,0% против 19,3%, хи-квадрат 22,2, df 1, n=557, p<0,001; различия внутри изолированных и внутри многодоменных подтипов незначимы.',
           'reported reversion contrast', ['U158'], {'population':'WHICAP baseline MCI subtype comparison', 'phase':'all available follow-ups'}, [('isolated_percent','38.0','percent'),('multidomain_percent','19.3','percent'),('chi_square','22.2','dimensionless'),('df','1','degrees of freedom'),('n','557','participants')], type='comparison')
    for slug, marker, ru_marker, endpoint, ru_endpoint, sensitivity, specificity in [
        ('persistent-mci-ad','nonreverting prevalent or incident MCI or incident AD','MCI или AD без возврата к норме','AD neuropathology','нейропатология AD','60','94'),
        ('stable-cognition-ad','stable impairment in any cognitive domain irrespective of diagnosis','устойчивое нарушение любой когнитивной области независимо от диагноза','AD neuropathology','нейропатология AD','60','59'),
        ('complaint-ad','memory complaints','жалобы на память','AD neuropathology','нейропатология AD','70','35'),
        ('stable-cognition-any','stable impairment in any cognitive domain','устойчивое нарушение любой когнитивной области','any brain pathology','любая патология мозга','62','100')]:
        record('autopsy-marker-'+slug,
               f'In the 27-person autopsy subset, {marker} had sensitivity {sensitivity}% and specificity {specificity}% for {endpoint}; these are sample diagnostic measures, not population guarantees.',
               f'В подвыборке 27 вскрытий показатель «{ru_marker}» имел чувствительность {sensitivity}% и специфичность {specificity}% для исхода «{ru_endpoint}»; это выборочные диагностические меры, не гарантии для популяции.',
               'reported diagnostic validity', ['U158','U176'], {'population':'WHICAP 27-person autopsy subset','clinical_marker':marker,'reference_outcome':endpoint}, [('sensitivity',sensitivity,'percent'),('specificity',specificity,'percent'),('n','27','participants')])
    record('reverted-autopsy-findings',
           'Three autopsied participants reverted from MCI to normal: two had no detectable brain-tissue abnormality and one had an asymptomatic infarct; none had AD neuropathology. This small subset does not establish absence of AD in all reverters.',
           'Трое вскрытых вернулись от MCI к нормальной классификации: у двоих не обнаружено тканевых изменений, у одного бессимптомный инфаркт; AD не обнаружена. Эта малая подвыборка не доказывает отсутствие AD у всех вернувшихся к норме.',
           'observed postmortem findings', ['U176','U182'], {'population':'WHICAP three autopsied MCI reverters'}, [('n','3','participants'),('no_abnormality','2','participants'),('infarct','1','participants'),('ad_pathology','0','participants')])
    record('clinical-death-interval',
           'Autopsy cases had mean last-evaluation-to-death interval 24.8 months (SD 21.3). Among AD-pathology cases, clinically unrecognized cases had 34.7 (SD 31.4) versus 18.8 (SD 11.1) months for clinically recognized MCI/AD; the difference was not significant.',
           'У вскрытых средний интервал от последней оценки до смерти 24,8 месяца (SD 21,3). При патологии AD клинически нераспознанные случаи имели 34,7 (SD 31,4) против 18,8 (SD 11,1) месяца при распознанном MCI/AD; различие незначимо.',
           'reported diagnostic timing contrast', ['U176'], {'population':'WHICAP autopsy subset', 'comparison':'AD-pathology cases by clinical recognition'}, [('mean','24.8','month'),('sd','21.3','month'),('unrecognized_mean','34.7','month'),('unrecognized_sd','31.4','month'),('recognized_mean','18.8','month'),('recognized_sd','11.1','month')], type='comparison')
    record('cutoff-fluctuation-hypothesis',
           'The authors propose that ordinary test variability near a diagnostic cutoff may change MCI classification without a true clinical-state transition; they do not establish this explanation for every reversion.',
           'Авторы предполагают, что обычная вариабельность теста у порога может менять классификацию MCI без истинного перехода клинического состояния; объяснение не установлено для каждого возврата.',
           'author-proposed explanation', ['U182'], {'explanation':'test variability near cutoff','outcome':'MCI classification fluctuation'}, type='hypothesis')
    record('continued-followup-task',
           'Continue follow-up of normal-reclassified participants to distinguish early dementia fluctuation, persistent variability and misclassification associated with cerebrovascular or age-related changes.',
           'Продолжить наблюдение нормализованной классификации, чтобы различить колебания ранней деменции, устойчивую вариабельность и ошибочную классификацию при сосудистых или возрастных изменениях.',
           'unresolved research task', ['U182'], {'population':'MCI reverters','question':'origin of diagnostic fluctuation'}, type='task', kind='action')
    record('unobserved-death-outcomes',
           'The authors cannot estimate the proportion developing MCI or dementia before death when death occurred before the next follow-up.',
           'Авторы не могут оценить долю развивших MCI или деменцию перед смертью, если смерть наступила до следующего обследования.',
           'unidentified outcome proportion', ['U182','U184'], {'population':'participants dying before next evaluation','outcome':'predeath MCI or dementia'}, type='limitation')
    record('dementia-cause-classification',
           'After consensus dementia diagnosis, cause was classified using published criteria for probable or possible AD, vascular dementia, Lewy body dementia and other dementias; severity was rated with the Clinical Dementia Rating.',
           'После согласованного диагноза деменции причину определяли по опубликованным критериям вероятной или возможной AD, сосудистой деменции, деменции с тельцами Леви и других деменций; тяжесть оценивали Clinical Dementia Rating.',
           'performed dementia subtype classification', ['U21','U23'], {'procedure':'WHICAP consensus dementia assessment','cause_categories':'AD; vascular; Lewy body; other'}, type='method', kind='action')
    record('larger-autopsy-task',
           'A much larger autopsy cohort is needed before broad conclusions about MCI diagnostic accuracy for neuropathology.',
           'До широких выводов о точности диагноза MCI относительно нейропатологии необходима существенно большая когорта вскрытий.',
           'unresolved validation task', ['U182'], {'question':'generalizability of MCI neuropathological accuracy'}, type='task', kind='action')
    record('age-progression-discussion',
           'The discussion identifies age over 75 as the strongest predictor of progression from baseline MCI to AD; MCI status at baseline also helped predict subsequent AD.',
           'В обсуждении возраст старше 75 лет назван сильнейшим предиктором перехода от исходного MCI к AD; исходный статус MCI также помогал предсказывать последующую AD.',
           'author synthesis of progression predictors', ['U178','U180'], {'population':'WHICAP baseline MCI','outcome':'incident Alzheimer disease','phase':'follow-up'}, type='result')
    record('ad-baseline-mci-comparison',
           'Over 10517.4 person-years, 309 incident AD cases were observed. At follow-up, AD was diagnosed in 186/1800 (10.3%) initially without MCI and 123/564 (21.8%) with MCI at baseline.',
           'За 10517,4 человеко-лет наблюдали 309 случаев AD. При наблюдении AD диагностирована у 186/1800 (10,3%) исходно без MCI и 123/564 (21,8%) с исходным MCI.',
           'reported incident AD contrast', ['U78'], {'population':'WHICAP final sample','phase':'follow-up','comparison':'baseline MCI versus no baseline MCI'}, [('exposure','10517.4','person-years'),('ad_cases','309','cases'),('no_mci_n','1800','participants'),('no_mci_ad_n','186','participants'),('no_mci_ad_percent','10.3','percent'),('mci_n','564','participants'),('mci_ad_n','123','participants'),('mci_ad_percent','21.8','percent')], type='comparison')
    record('diagnostic-instability-null',
           'The authors report finding no demographic or medical factors associated with instability of MCI diagnosis; this is a reported null finding, not proof that such factors have no effect.',
           'Авторы сообщают, что не нашли демографических или медицинских факторов, связанных с нестабильностью диагноза MCI; это отрицательный результат анализа, не доказательство отсутствия эффекта.',
           'association not statistically detected', ['U182'], {'population':'WHICAP participants with MCI','outcome':'diagnostic instability','phase':'follow-up'})
    record('single-versus-multidomain-course',
           'Authors summarize that MCI with impairment in multiple domains, with or without memory impairment, was less likely to revert than single-domain MCI; the interpretation attributes this possibly to greater distance from the test cutoff.',
           'Авторы обобщают, что многодоменный MCI с нарушением памяти или без него реже возвращался к норме, чем однодоменный; возможное объяснение — большая удалённость результатов от порога теста.',
           'author synthesis of reversion pattern', ['U178','U182'], {'population':'WHICAP MCI subtypes','outcome':'normal reclassification','phase':'follow-up'}, type='comparison')
    record('mci-memory-progression-synthesis',
           'Authors conclude that MCI subtypes including memory impairment had the greatest risk of progression to AD; this summarizes the reported WHICAP subtype models.',
           'Авторы заключают, что подтипы MCI с нарушением памяти имели наибольший риск прогрессирования к AD; это обобщение модельных результатов WHICAP.',
           'author synthesis of subtype progression', ['U178','U180'], {'population':'WHICAP baseline MCI subtypes','outcome':'incident Alzheimer disease','phase':'follow-up'}, type='result')
    record('cohort-criteria-comparison-limit',
           'The discussion says cross-study MCI incidence comparisons are difficult because cohorts differ in mean age, follow-up duration and diagnostic criteria.',
           'Авторы указывают, что сравнивать частоты MCI между исследованиями сложно из-за различий среднего возраста, длительности наблюдения и диагностических критериев.',
           'cross-study comparability limitation', ['U178'], {'comparison':'MCI incidence across cohorts'}, type='limitation')
    record('autopsy-generalization-limit',
           'The authors state that the 27-case autopsy subset is insufficient for sweeping conclusions about MCI accuracy for neuropathology.',
           'Авторы считают подвыборку 27 вскрытий недостаточной для широких выводов о точности MCI относительно нейропатологии.',
           'limited validation evidence', ['U182'], {'population':'WHICAP 27-person autopsy subset'}, type='limitation')
    record('followup-duration-limit',
           'Mean follow-up of 4.7 years limits comparisons of later AD progression and may change conclusions about normal reclassification with longer observation.',
           'Среднее наблюдение 4,7 года ограничивает сравнения дальнейшего прогрессирования к AD; более длительное наблюдение может изменить выводы о нормальной переклассификации.',
           'limited observation window', ['U182'], {'population':'WHICAP longitudinal sample'}, [('mean_followup','4.7','year')], type='limitation')
    record('attention-measurement-limit',
           'The battery lacked traditional attention measures separating attention impairment from other domains; authors suggest memory and language measures may be more attention-loaded than drawing measures.',
           'Батарея не имела традиционных мер внимания для отделения его нарушения от других областей; авторы предполагают большую нагрузку на внимание у памяти и языка, чем у рисования.',
           'author-described measurement limitation', ['U184'], {'method':'WHICAP neuropsychological battery'}, type='limitation')
    record('postdeath-questionnaire-method',
           'To address unobserved predeath decline, the investigators report now administering the Dementia Questionnaire to family members after learning of a participant death.',
           'Для изучения ненаблюдаемого снижения перед смертью исследователи сообщают, что теперь опрашивают семью Dementia Questionnaire после известия о смерти участника.',
           'reported corrective procedure', ['U184'], {'method':'Dementia Questionnaire','informant':'family members','outcome':'predeath cognition and function'}, type='operation', kind='action')
    record('neuropathology-processing',
           'After death, one hemisphere was dissected and frozen; the other was fixed in buffered 10% formalin. At least 18 standardized blocks were sampled, and 7-micrometer sections received general and targeted stains; neuritic plaques were counted in five random 100x fields from seven blocks.',
           'После смерти одно полушарие рассекали и замораживали; другое фиксировали в буферном 10% формалине. Отбирали не менее 18 стандартных блоков; срезы 7 мкм окрашивали общими и специальными методами; бляшки считали в пяти случайных полях 100× из семи блоков.',
           'performed neuropathology protocol', ['U25'], {'population':'WHICAP autopsy cases','reference_method':'postmortem neuropathology'}, [('minimum_blocks','18','blocks'),('section_thickness','7','micrometer'),('plaque_fields','5','fields'),('magnification','100','times'),('plaque_blocks','7','blocks')], type='method', kind='action')
    record('neuropathology-diagnostic-criteria',
           'Neuropathological AD used CERAD and NIA-Reagan criteria with Braak staging; Lewy body variant additionally required dementia, AD-significant neuronal loss, plaques and tangles, and cortical and subcortical Lewy bodies.',
           'Для нейропатологической AD использовали критерии CERAD и NIA-Reagan со стадированием Braak; вариант с тельцами Леви требовал также деменции, значимой для AD потери нейронов, бляшек и клубков, корковых и подкорковых телец Леви.',
           'neuropathological classification criteria', ['U25'], {'reference_method':'postmortem neuropathology','criteria':'CERAD; NIA-Reagan; Braak'}, type='definition')
    record('autopsy-false-negative-pattern',
           'False-negative clinical findings for AD pathology included combined pathologies and AD pathology alone.',
           'Ложноотрицательные клинические результаты при патологии AD включали сочетанные патологии и только патологию AD.',
           'reported false-negative composition', ['U176'], {'population':'WHICAP autopsy subset','reference_outcome':'AD neuropathology'})
    record('autopsy-false-positive-pattern',
           'False-positive clinical findings for AD pathology primarily included infarcts or vascular dementia, and also lobar atrophy, Parkinson disease or no recognized abnormality.',
           'Ложноположительные клинические результаты для патологии AD преимущественно включали инфаркты или сосудистую деменцию, а также долевую атрофию, болезнь Паркинсона или отсутствие распознанных изменений.',
           'reported false-positive composition', ['U176'], {'population':'WHICAP autopsy subset','reference_outcome':'AD neuropathology'})
    record('weight-objective-criteria-proposal',
           'Based on clinical and neuropathological results, authors suggest retaining both objective scores and subjective complaints in MCI classification but perhaps giving objective criteria more weight; this is a proposal, not a validated weighting formula.',
           'На основании клинических и нейропатологических результатов авторы предлагают сохранять объективные показатели и жалобы в классификации MCI, возможно увеличив вес объективных критериев; это предложение, не проверенная формула весов.',
           'author-proposed classification change', ['U184','U186'], {'method':'MCI classification','proposal':'greater weight for objective neuropsychological criteria'}, type='task', kind='action')
    record('subtype-progression-discussion',
           'In the authors discussion, amnestic, language and MCDN MCI had greater AD progression risk than no MCI, whereas visuospatial and executive subtypes did not; MCDM had the greatest progression rate, with a reported relative estimate about 4.3.',
           'В обсуждении авторов амнестический, языковой и MCDN подтипы имели больший риск AD, чем отсутствие MCI, зрительно-пространственный и исполнительный — нет; MCDM имел наибольшее прогрессирование с оценкой около 4,3.',
           'author-reported subtype contrast', ['U180'], {'population':'WHICAP without baseline dementia','comparison':'baseline MCI subtypes versus no MCI','outcome':'incident AD'}, [('mcdm_relative_estimate','4.3','dimensionless')], type='comparison')
    record('subtype-underlying-pathology-hypothesis',
           'The authors suggest that less AD progression in visuospatial and executive MCI may indicate less underlying AD pathology; this inference is not a demonstrated neuropathological difference between all subtypes.',
           'Авторы предполагают, что меньшее прогрессирование к AD при зрительно-пространственном и исполнительном MCI может означать меньшую скрытую патологию AD; различие нейропатологии всех подтипов не доказано.',
           'author-proposed pathology interpretation', ['U180'], {'population':'WHICAP visuospatial and executive MCI','outcome':'underlying AD pathology'}, type='hypothesis')
    record('subtype-biomarker-hypothesis',
           'Authors predict that plasma amyloid-beta, insulin levels or hippocampal volume should differ from healthy controls in amnestic, language and MCDN MCI; the printed MCDN label is retained and no biomarker measurement is claimed here.',
           'Авторы ожидают отличий плазменного амилоида-бета, инсулина или объёма гиппокампа от здорового контроля при амнестическом, языковом и MCDN MCI; обозначение MCDN сохранено по тексту, измерения здесь не заявляются.',
           'author-proposed biomarker differences', ['U180'], {'population':'amnestic, language and MCDN MCI','comparison':'healthy controls','outcome':'plasma amyloid-beta, insulin or hippocampal volume'}, type='hypothesis')
    record('cardiovascular-genetic-task',
           'Because cardiovascular and genetic analyses were exploratory, authors request further study of subtype correlates and their interaction with memory function on dementia risk.',
           'Поскольку сердечно-сосудистые и генетические анализы были поисковыми, авторы требуют дальнейшего изучения коррелятов подтипов и их взаимодействия с памятью в отношении риска деменции.',
           'unresolved exploratory-analysis task', ['U180'], {'question':'cardiovascular and genetic subtype correlates interacting with memory','outcome':'dementia risk'}, type='task', kind='action')


def clinical_argument_transitions():
    # Только переходы, непосредственно выраженные аргументацией автора.
    transitions = [
        {'sources':['isolated-versus-multidomain-reversion'], 'target':'single-versus-multidomain-course', 'usage':'evidence',
         'reason':'The discussion summarizes the subtype reversion comparison and proposes a cutoff-distance explanation.', 'units':['U158','U182']},
        {'sources':['mci-memory-progression-synthesis'], 'target':'subtype-underlying-pathology-hypothesis', 'usage':'evidence',
         'reason':'The authors use the progression pattern to motivate, but not establish, a pathology interpretation.', 'units':['U180']},
        {'sources':['subtype-progression-discussion'], 'target':'subtype-underlying-pathology-hypothesis', 'usage':'evidence',
         'reason':'Authors explicitly infer a possible pathology difference from subtype progression; the inference remains hypothetical.', 'units':['U180']},
        {'sources':['subtype-progression-discussion'], 'target':'subtype-biomarker-hypothesis', 'usage':'premise',
         'reason':'Authors use subtype longitudinal outcomes to motivate expected biomarker differences; no measured biomarker effect is supplied.', 'units':['U180']},
        {'sources':['cutoff-fluctuation-hypothesis'], 'target':'continued-followup-task', 'usage':'premise',
         'reason':'The author proposes continued follow-up to distinguish explanations for classification fluctuation.', 'units':['U182']},
        {'sources':['autopsy-generalization-limit'], 'target':'larger-autopsy-task', 'usage':'premise',
         'reason':'The limited autopsy evidence motivates the explicitly requested larger validation cohort.', 'units':['U182']},
        {'sources':['unobserved-death-outcomes'], 'target':'postdeath-questionnaire-method', 'usage':'premise',
         'reason':'The authors introduce family questionnaires explicitly to address unobserved predeath decline.', 'units':['U184']},
        {'sources':['autopsy-marker-stable-cognition-ad','autopsy-marker-complaint-ad'], 'target':'weight-objective-criteria-proposal', 'usage':'evidence',
         'reason':'The authors jointly contrast objective impairment and complaint validity as grounds for reconsidering criterion weights; this does not calculate optimal weights.', 'units':['U176','U184','U186']},
    ]
    for subtype in ['amnestic','executive','language','visuospatial','mcdm','mcdn']:
        transitions.append({'sources':['mci-core-criteria'], 'target':'subtype-'+subtype, 'usage':'definition',
            'reason':'The subtype definition explicitly requires the shared WHICAP MCI criteria and its domain-specific rule.', 'units':['U23','U25'] if subtype in {'mcdm','mcdn'} else ['U23']})
    transitions.append({'sources':['mci-core-criteria'], 'target':'exclusive-subtypes', 'usage':'definition',
        'reason':'The mutually exclusive classification concerns the six subtypes defined under the shared MCI classification.', 'units':['U25']})

    mci_results = ['mci-age70','mci-age75','mci-age80','mci-black','mci-hispanic','mci-hypertension',
        'mci-null-sex','mci-null-education','mci-null-recruitment-cohort','mci-null-heart-disease-history',
        'mci-null-diabetes-history','mci-null-stroke-history','mci-null-psychiatric-history',
        'genotype-subset-contrast','memory-mci-predictors','memory-mci-heart','nonmemory-mci-education']
    for result in mci_results:
        transitions.append({'sources':['fit-mci-cox','event-time'], 'target':result, 'usage':'method',
            'reason':'This result is reported from the WHICAP time-to-first-MCI Cox analysis; the model and event-time definition delimit its interpretation.', 'units':['U76','U78'] if result == 'nonmemory-mci-education' else ['U76']})

    ad_results = ['ad-education','ad-black','ad-hispanic','ad-apoe','ad-diabetes','ad-stroke',
        'ad-null-sex','ad-null-recruitment-cohort','ad-null-hypertension-history',
        'ad-null-heart-disease-history','ad-null-psychiatric-history']
    for result in ad_results:
        transitions.append({'sources':['fit-ad-cox'], 'target':result, 'usage':'method',
            'reason':'The reported coefficient or non-detection is from the described WHICAP time-to-first-AD model.', 'units':['U125']})

    for result in ['reversion-all-visits','first-followup-course','isolated-versus-multidomain-reversion',
                   'reversion-overlapping-criteria','reversion-exclusive-criteria']:
        transitions.append({'sources':['compare-reversion'], 'target':result, 'usage':'method',
            'reason':'This comparison is an outcome of the stated baseline-MCI follow-up analysis; its visit phase remains in the target knowledge.',
            'units':['U127'] if result in {'reversion-all-visits','first-followup-course'} else ['U158'] if result == 'isolated-versus-multidomain-reversion' else ['U156','U158']})

    for result in ['autopsy-marker-persistent-mci-ad','autopsy-marker-stable-cognition-ad',
                   'autopsy-marker-complaint-ad','autopsy-marker-stable-cognition-any']:
        transitions.append({'sources':['clinical-pathology-validation'], 'target':result, 'usage':'method',
            'reason':'These diagnostic measures compare clinical markers with postmortem neuropathological reference outcomes under the described validation procedure.', 'units':['U176']})
    for method in ['calculate-incidence','calculate-ad-incidence','fit-mci-cox','fit-ad-cox','compare-reversion']:
        transitions.append({'sources':['sample-selection-flow'], 'target':method, 'usage':'condition',
            'reason':'The analysis method uses participants formed by the stated selection and exclusion flow.', 'units':['U27']})
    return transitions
