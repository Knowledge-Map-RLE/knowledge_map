"""Определения, методы и модельные результаты WHICAP из дословной ревизии текста."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable
from tools.author_manly_definition_draft import SOURCE_SHA256
from tools.run_free_prediction import disable_network
from tools.manly_sampling_records import append_sampling_records
from tools.manly_clinical_course_records import append_clinical_course_records, clinical_argument_transitions


def build(source):
    require(source['sha256'] == SOURCE_SHA256 and sha256(source['text'].encode()).hexdigest() == SOURCE_SHA256,
            'Reviewed source differs')
    units = {u['id']: u for u in source['units']}
    records = []
    def add(key, en, ru, predicate, uids, *, roles=None, attrs=None, kind='state', type='observation',
            claims=None, logic='single', quantifier=None, unknown=False, model=None, status=None, modality=None):
        for uid in uids:
            u = units[uid]
            require(source['text'][u['start']:u['end']] == u['text'] and u['end'] <= source['content_end'],
                    'Prose source coordinates differ')
        item = {'key': key, 'en': en, 'ru': ru, 'predicate': predicate,
                'roles': {'cohort': 'WHICAP', **(roles or {})}, 'units': uids,
                'attrs': attrs or {}, 'kind': kind, 'type': type,
                'conditions': [] if unknown else ['Source-grounded WHICAP observation or operational method',
                                                  'No causal effect is established by these observational analyses'],
                'time': None if unknown else 'Reported WHICAP assessment and follow-up',
                'logic': logic, 'quantifier': quantifier, 'modality': modality}
        if model:
            item['roles']['analysis_model'] = model
        if status:
            item['status'] = status
        if claims:
            item['claims'] = claims
        records.append(item)

    add('mci-core-criteria',
        'WHICAP MCI classification at each visit requires a memory complaint, objective impairment in at least one cognitive domain at a 1.5-SD demographic-norm cutoff, essentially preserved daily functioning, and no consensus diagnosis of dementia.',
        'Классификация MCI в WHICAP на каждом визите требует жалобы на память, объективного нарушения хотя бы одной когнитивной области при пороге 1,5 SD по демографическим нормам, существенно сохранной повседневной функции и отсутствия согласованного диагноза деменции.',
        'diagnostic criteria', ['U23'], roles={'classification': 'WHICAP MCI'}, type='definition', quantifier='all',
        logic='conjunction', claims=[
            {'predicate': 'requires memory complaint', 'roles': {'criterion': 'memory complaint'}},
            {'predicate': 'requires objective impairment', 'roles': {'criterion': 'at least one impaired cognitive domain'},
             'attrs': {'threshold': {'value': '1.5', 'unit': 'SD'}, 'norm_adjustments': {'value': 'age, education, ethnicity, sex', 'unit': None}}},
            {'predicate': 'requires preserved daily function', 'roles': {'criterion': 'WHICAP preserved-daily-function criterion'}},
            {'predicate': 'excludes dementia diagnosis', 'roles': {'criterion': 'dementia diagnosed at the same consensus visit'}}])
    subtype_definitions = [
        ('amnestic', 'MCI-amnestic', 'Амнестический MCI', 'isolated memory impairment; executive, language and visuospatial composites within norms', 'изолированное нарушение памяти при исполнительных, языковых и зрительно-пространственных показателях в пределах норм', 'U23'),
        ('executive', 'MCI-executive', 'Исполнительный MCI', 'isolated executive impairment on Letter Fluency, Category Fluency and WAIS-R Similarities', 'изолированное исполнительное нарушение по буквенной и категориальной беглости и субтесту сходства WAIS-R', 'U23'),
        ('language', 'MCI-language', 'Языковой MCI', 'isolated language impairment on Boston Naming, BDAE Repetition and Comprehension', 'изолированное языковое нарушение по Boston Naming, повторению и пониманию BDAE', 'U23'),
        ('visuospatial', 'MCI-visuospatial', 'Зрительно-пространственный MCI', 'isolated visuospatial impairment on Rosen Drawing and BVRT matching', 'изолированное зрительно-пространственное нарушение по рисованию Rosen и сопоставлению BVRT', 'U23'),
        ('mcdm', 'MCI-MCDM', 'Многодоменный MCI с нарушением памяти', 'memory composite impairment and impairment in at least one other domain', 'нарушение составного показателя памяти и хотя бы одной другой области', 'U25'),
        ('mcdn', 'MCI-MCDN', 'Многодоменный MCI без нарушения памяти', 'impairment in at least two of three nonmemory domains with memory within norms', 'нарушение хотя бы двух из трёх непамятных областей при памяти в пределах норм', 'U25')]
    for slug, name, ru_name, criterion, ru_criterion, uid in subtype_definitions:
        add('subtype-' + slug, name + ' uses the shared WHICAP MCI criteria plus ' + criterion + '.',
            ru_name + ': общие критерии MCI WHICAP и ' + ru_criterion + '.', 'subtype diagnostic criteria', ['U23', uid] if uid != 'U23' else ['U23'],
            roles={'subtype': name}, type='definition', quantifier='all', logic='conjunction',
            claims=[{'predicate': 'subtype_of', 'roles': {'subject': name, 'class': 'WHICAP MCI'}},
                    {'predicate': 'requires shared diagnostic criteria', 'roles': {'shared_criteria': '@mci-core-criteria'},
                     'attrs': {'specific_criteria': {'value': criterion, 'unit': None}}}])
    add('exclusive-subtypes', 'The six WHICAP MCI subtypes are mutually exclusive at a classification visit.',
        'Шесть подтипов MCI WHICAP взаимоисключающие на классификационном визите.', 'classification partition', ['U25'], type='definition',
        roles={'classification': 'WHICAP six MCI subtypes'})
    add('calculate-incidence', 'Calculate age-, sex-, ethnicity- and education-stratified MCI incidence among participants without baseline MCI; calculate 95% confidence intervals assuming a Poisson distribution.',
        'Рассчитать частоту MCI по возрасту, полу, этнической группе и образованию среди участников без исходного MCI; рассчитать 95%-ные ДИ при предположении распределения Пуассона.',
        'estimate incidence rate', ['U27'], kind='action', type='operation', roles={'outcome': 'incident MCI', 'baseline_group': 'without baseline MCI'},
        attrs={'confidence_level': {'value': '95', 'unit': 'percent'}, 'education_split': {'value': '0-11 versus 12 or more years', 'unit': None}})
    add('fit-mci-cox', 'Fit Cox models for time to first MCI; candidate predictors include age, education, ethnicity, sex, cohort, APOE and baseline medical/psychiatric history. APOE-complete results are reported in a separate subset.',
        'Построить модели Кокса времени до первого MCI: возраст, образование, этническая группа, пол, когорта, APOE и исходный медицинский/психиатрический анамнез. Результаты при наличии APOE сообщаются для отдельной подвыборки.',
        'fit Cox proportional-hazards model', ['U27', 'U76'], kind='action', type='operation', roles={'outcome': 'incident MCI', 'baseline_group': 'without baseline MCI'}, model='MCI model series')
    add('event-time', 'Time to first MCI is days from baseline neuropsychological evaluation to the examination first diagnosing MCI; noncases use time to the last evaluation.',
        'Время до первого MCI — дни от исходного нейропсихологического обследования до первого установления MCI; у остальных используют время до последнего обследования.',
        'define analysis time', ['U27'], type='definition', roles={'outcome': 'incident MCI'},
        attrs={'unit': {'value': 'day', 'unit': None}})
    add('calculate-ad-incidence', 'Calculate age-specific AD incidence rates separately among participants with and without MCI at baseline.',
        'Рассчитать частоту AD по возрасту отдельно у участников с исходным MCI и без него.',
        'estimate incidence rate', ['U27'], kind='action', type='operation',
        roles={'outcome':'incident Alzheimer disease','stratifier':'baseline MCI status'})
    add('fit-ad-cox', 'Fit Cox models for first AD diagnosis, first entering demographic, genetic and medical predictors and then baseline MCI status; a component analysis uses forward stepwise selection.',
        'Построить модели Кокса первого диагноза AD: сначала демографические, генетические и медицинские предикторы, затем исходный статус MCI; компоненты классификации проверяются пошаговым включением.',
        'fit Cox proportional-hazards model', ['U27'], kind='action', type='operation', roles={'outcome': 'incident Alzheimer disease'}, model='AD model series')
    add('compare-reversion', 'Compare baseline-MCI participants who revert, remain MCI or develop AD using ANOVA with Tukey comparisons and chi-square analyses.',
        'Сравнить участников с исходным MCI, вернувшихся к нормальной классификации, оставшихся с MCI или развивших AD: ANOVA с тестами Tukey и анализы хи-квадрат.',
        'performed method', ['U27'], kind='action', type='operation', roles={'outcome': 'MCI diagnostic course', 'baseline_group': 'baseline MCI'})
    add('clinical-pathology-validation', 'Evaluate sensitivity, specificity and accuracy of clinical classifications against postmortem neuropathological diagnosis; AD pathology must cross the specified neuropathological threshold.',
        'Оценить чувствительность, специфичность и точность клинической классификации относительно посмертного нейропатологического диагноза; изменения AD должны достигать установленного порога.',
        'performed method', ['U25', 'U27', 'U29'], kind='action', type='operation', roles={'reference_standard': 'postmortem neuropathology'})

    def association(key, factor, factor_ru, contrast, contrast_ru, outcome, outcome_ru, estimate, low, high, uid,
                    *, model, baseline, finding='detected', unknown=False):
        en = f'In the WHICAP {model}, {factor} ({contrast}) was reported for {outcome}'
        ru = f'WHICAP, {model}: {factor_ru} ({contrast_ru}) — результат для исхода «{outcome_ru}»'
        attrs = {'reported_statistical_finding': {'value': finding, 'unit': None},
                 'causal_identification': {'value': 'not established', 'unit': None}}
        if estimate is not None:
            en += f': RR {estimate}, 95% CI {low}-{high}'
            ru += f': RR {estimate}, 95% ДИ {low}–{high}'
            attrs.update(relative_estimate={'value': estimate, 'unit': 'dimensionless'},
                         confidence_low={'value': low, 'unit': 'dimensionless'},
                         confidence_high={'value': high, 'unit': 'dimensionless'},
                         confidence_level={'value': '95', 'unit': 'percent'},
                         source_estimate_label={'value': 'RR', 'unit': None})
        else:
            en += '; no numerical estimate is supplied in this paragraph'
            ru += '; числовая оценка в этом абзаце не приведена'
        en += '. This is an observational model result, not a causal effect.'
        ru += '. Это результат наблюдательной модели, не причинный эффект.'
        add(key, en, ru, 'association not statistically detected' if finding == 'not detected' else 'estimated association', [uid],
            roles={'factor': factor, 'contrast': contrast, 'outcome': outcome, 'baseline_group': baseline}, attrs=attrs,
            type='result', model=model, unknown=unknown)

    for slug, factor, ru, contrast, cru, est, lo, hi in [
        ('age70', 'age', 'возраст', '70-74 versus 65-69 years', '70–74 против 65–69 лет', '1.6', '1.1', '2.4'),
        ('age75', 'age', 'возраст', '75-79 versus 65-69 years', '75–79 против 65–69 лет', '1.9', '1.3', '2.8'),
        ('age80', 'age', 'возраст', '80 or older versus 65-69 years', 'от 80 против 65–69 лет', '2.5', '1.7', '3.6'),
        ('black', 'ethnicity', 'этническая группа', 'black versus non-Hispanic white', 'чернокожие против нелатиноамериканских белых', '1.4', '1.0', '1.8'),
        ('hispanic', 'ethnicity', 'этническая группа', 'Hispanic versus non-Hispanic white', 'латиноамериканские против нелатиноамериканских белых', '1.4', '1.0', '1.9'),
        ('hypertension', 'hypertension history', 'гипертония в анамнезе', 'present versus absent', 'есть против отсутствует', '1.4', '1.1', '1.9')]:
        association('mci-' + slug, factor, ru, contrast, cru, 'incident total MCI', 'MCI в целом', est, lo, hi, 'U76', model='primary MCI Cox model', baseline='without baseline MCI')
    for factor, ru in [('sex', 'пол'), ('education', 'образование'), ('recruitment cohort', 'когорта набора'),
                       ('heart disease history', 'болезнь сердца в анамнезе'), ('diabetes history', 'диабет в анамнезе'),
                       ('stroke history', 'инсульт в анамнезе'), ('psychiatric history', 'психиатрический анамнез')]:
        association('mci-null-' + factor.replace(' ', '-'), factor, ru, 'reported model coding', 'кодировка модели',
                    'incident total MCI', 'MCI в целом', None, None, None, 'U76', model='primary MCI Cox model',
                    baseline='without baseline MCI', finding='not detected')
    add('genotype-subset-contrast', 'In the APOE-complete MCI subset (n=1572), age and hypertension remained predictors, ethnicity was no longer significant, and APOE epsilon4 did not predict greater MCI risk.',
        'В подвыборке MCI с данными APOE (n=1572) возраст и гипертония оставались предикторами; этническая группа больше не была значимой, APOE ε4 не предсказывал повышенный риск MCI.',
        'reported model contrast', ['U76'], type='comparison', roles={'outcome': 'incident total MCI', 'baseline_group': 'without baseline MCI, complete APOE data'},
        attrs={'sample_n': {'value': '1572', 'unit': 'participants'}}, model='APOE-complete MCI Cox model')
    add('memory-mci-predictors', 'Older age and hypertension predicted incident MCI with memory impairment in subtype-specific Cox models; a history of heart disease had a lower relative estimate.',
        'В моделях подтипа возраст и гипертония предсказывали MCI с нарушением памяти; болезнь сердца в анамнезе имела меньшую относительную оценку.',
        'reported subtype association', ['U76'], type='result', roles={'outcome': 'incident MCI with memory impairment', 'baseline_group': 'without baseline MCI'}, model='memory MCI Cox model')
    association('memory-mci-heart', 'heart disease history', 'болезнь сердца в анамнезе', 'present versus absent', 'есть против отсутствует',
                'incident MCI with memory impairment', 'MCI с нарушением памяти', '0.70', '0.50', '0.98', 'U76', model='memory MCI Cox model', baseline='without baseline MCI')
    association('nonmemory-mci-education', 'education', 'образование', 'fewer than 12 versus at least 12 years', 'менее 12 против хотя бы 12 лет',
                'incident MCI without memory impairment', 'MCI без нарушения памяти', '1.4', '1.0', '1.9', 'U78', model='nonmemory MCI Cox model', baseline='without baseline MCI')
    for slug, factor, ru, contrast, cru, est, lo, hi in [
        ('education', 'education', 'образование', 'fewer than 12 versus at least 12 years', 'менее 12 против хотя бы 12 лет', '2.0', '1.4', '2.7'),
        ('black', 'ethnicity', 'этническая группа', 'black versus non-Hispanic white', 'чернокожие против нелатиноамериканских белых', '2.3', '1.5', '3.5'),
        ('hispanic', 'ethnicity', 'этническая группа', 'Hispanic versus non-Hispanic white', 'латиноамериканские против нелатиноамериканских белых', '2.4', '1.6', '3.7'),
        ('apoe', 'APOE epsilon4', 'APOE ε4', 'carrier versus noncarrier', 'носитель против неносителя', '1.4', '1.0', '1.7'),
        ('diabetes', 'diabetes history', 'диабет в анамнезе', 'present versus absent', 'есть против отсутствует', '1.5', '1.1', '1.9'),
        ('stroke', 'stroke history', 'инсульт в анамнезе', 'present versus absent', 'есть против отсутствует', '2.3', '1.6', '3.3')]:
        association('ad-' + slug, factor, ru, contrast, cru, 'incident Alzheimer disease', 'болезнь Альцгеймера', est, lo, hi, 'U125', model='AD Cox analysis', baseline='without baseline dementia')
    for factor, ru in [('sex', 'пол'), ('recruitment cohort', 'когорта набора'), ('hypertension history', 'гипертония в анамнезе'),
                       ('heart disease history', 'болезнь сердца в анамнезе'), ('psychiatric history', 'психиатрический анамнез')]:
        association('ad-null-' + factor.replace(' ', '-'), factor, ru, 'reported model coding', 'кодировка модели',
                    'incident Alzheimer disease', 'болезнь Альцгеймера', None, None, None, 'U125', model='AD Cox analysis', baseline='without baseline dementia', finding='not detected')
    for age, est, lo, hi in [('70-74', '2.6', '1.4', '4.8'), ('75-79', '5.0', '2.7', '9.3'), ('80 or older', '11.2', '6.0', '20.1')]:
        association('ambiguous-ad-section-age-' + age.replace(' ', '-'), 'age', 'возраст', age + ' versus 65-69 years', age + ' против 65–69 лет',
                    'printed as MCI within the AD-analysis section; endpoint unresolved', 'в разделе AD напечатан MCI; исход неоднозначен',
                    est, lo, hi, 'U125', model='endpoint-ambiguous analysis paragraph', baseline='analytical population unresolved', unknown=True)
    append_sampling_records(add)
    append_clinical_course_records(add)
    # Проверенные первичные результаты; введение и авторские гипотезы сюда не входят.
    primary_keys = {
        'genotype-subset-contrast', 'memory-mci-predictors', 'memory-mci-heart', 'nonmemory-mci-education',
        'sample-selection-flow', 'no-followup-reasons', 'followup-denominator',
        'selection-age-education', 'selection-sex-and-burden', 'no-followup-cognitive-selection',
        'observed-followup-interval', 'reevaluation-distribution', 'death-autopsy-selection',
        'results-sample-profile', 'results-duration-and-genotype', 'figure-selection-counts',
        'memory-nonmemory-incidence', 'amnestic-mcdm-rate-difference',
        'reversion-all-visits', 'first-followup-course', 'course-observation-duration',
        'reversion-overlapping-criteria', 'reversion-exclusive-criteria',
        'isolated-versus-multidomain-reversion', 'reverted-autopsy-findings', 'clinical-death-interval',
        'autopsy-marker-persistent-mci-ad', 'autopsy-marker-stable-cognition-ad',
        'autopsy-marker-complaint-ad', 'autopsy-marker-stable-cognition-any',
        'age-progression-discussion', 'diagnostic-instability-null',
        'single-versus-multidomain-course', 'mci-memory-progression-synthesis',
        'results-cohort-composition', 'abstract-outcome-summary', 'informant-measurement-context',
        'baseline-medical-profile', 'recruitment-cohort-differences',
        'autopsy-subset-selection', 'clinical-medical-evaluation',
        'psychiatric-assessment-method', 'neuropsychological-test-battery',
        'ad-baseline-mci-comparison', 'table-abbreviation-glossary', 'calculate-ad-incidence',
    }
    for item in records:
        if item['key'] in primary_keys or item['predicate'] in {'estimated association', 'association not statistically detected'}:
            item['roles']['evidence_origin'] = 'direct observation in this primary study'
    require(len({k['key'] for k in records}) == len(records), 'Duplicate prose key')
    return {'version': 'manly-prose-method-and-model-stage-11', 'source_sha256': SOURCE_SHA256,
            'transitions_draft': clinical_argument_transitions(),
            'knowledge_draft': records, 'blocks': len(records), 'complete_semantic_coverage': False,
            'model_calls': 0, 'full_map_created': False, 'expert_validated': False,
            'remaining_ru': ['Валидатор карты сохраняет статус семантической полноты неопределённым, хотя таблицы обработаны полностью и непривязанные к знаниям единицы просмотрены как PDF-разметка или метаданные.',
                             'Провести независимую экспертную проверку научной точности перед подтверждающим прогнозом.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    disable_network()
    root = args.root.resolve() / 'eval/whole_map_forecast/manly-complete-map-v1'
    source = json.loads((root / 'source-v1/source.json').read_text(encoding='utf-8'))
    result = build(source)
    result['implementation_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    result['sampling_implementation_sha256'] = sha256(Path(__file__).with_name('manly_sampling_records.py').read_bytes()).hexdigest()
    result['clinical_course_implementation_sha256'] = sha256(Path(__file__).with_name('manly_clinical_course_records.py').read_bytes()).hexdigest()
    folder = root / 'prose-stage' / fingerprint(result)
    write_immutable(folder / 'data.json', json.dumps(result, ensure_ascii=False, indent=2).encode())
    report = ['# WHICAP: определения, методы и результаты моделей', '',
              f"Подготовлены {result['blocks']} блоков непосредственно из полного текста новой ревизии.",
              'Это следующий этап полной формализации; карта всей статьи и прогнозы ещё не завершены.', '',
              'Различены исходы MCI в целом, MCI с нарушением памяти, MCI без нарушения памяти и болезнь Альцгеймера. '
              'Основная модель и анализ при наличии APOE не объединены. Статистическая незначимость не превращается в нулевой эффект.', '',
              'Сохранена неоднозначность исхода в абзаце возрастных оценок раздела AD: сам текст называет MCI. '
              'Три блока оставлены с неизвестным контекстом; догадкой исход не заменён.', '', '## Блоки', '']
    report += [f"{i}. {k['ru']}" for i, k in enumerate(result['knowledge_draft'], 1)]
    report += ['', '## Оставшаяся работа', '', *result['remaining_ru'], '',
               'Источник и прежние карты не изменены. Авторство интерпретации — Codex; требуется экспертная проверка. '
               'Модельных вызовов — 0. Независимые будущие результаты не оценивались.', '']
    write_immutable(folder / 'report.ru.md', '\n'.join(report).encode())
    print(folder)
    print('Блоков:', result['blocks'])


if __name__ == '__main__':
    main()
