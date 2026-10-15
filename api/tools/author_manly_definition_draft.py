"""Начало полной формализации из нового источника: определения и их проверяемые следствия."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from domain.article_maps import fingerprint, require
from domain.categorical_logic import check
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

VERSION = 'manly-source-bound-definition-draft-1'
SOURCE_SHA256 = '9936c89964672d3882446b355e702050d557e8f2d262c4d4e043761b7293d5ee'
SUBTYPES = [
    ('amnestic', 'MCI-amnestic', 'амнестический MCI с изолированным нарушением памяти', 'U23'),
    ('executive', 'MCI-executive', 'MCI с изолированным нарушением исполнительных функций', 'U23'),
    ('language', 'MCI-language', 'MCI с изолированным нарушением языка', 'U23'),
    ('visuospatial', 'MCI-visuospatial', 'MCI с изолированным зрительно-пространственным нарушением', 'U23'),
    ('mcdm', 'MCI-MCDM', 'MCI с нарушением памяти и других когнитивных областей', 'U25'),
    ('mcdn', 'MCI-MCDN', 'MCI с несколькими нарушенными областями при сохранной памяти', 'U25'),
]
SCOPE = {'study_group': 'WHICAP operational classification', 'time': 'same diagnostic visit',
         'conditions': ['Retrospectively applied WHICAP operational MCI criteria, not all clinical definitions'],
         'modality': None}


def evidence(source, uid):
    unit = next(u for u in source['units'] if u['id'] == uid)
    require(type(unit['start']) is int and type(unit['end']) is int
            and 0 <= unit['start'] < unit['end'] <= source['content_end']
            and source['text'][unit['start']:unit['end']] == unit['text'], 'Definition source coordinates differ')
    return {'unit_id': uid, 'start': unit['start'], 'end': unit['end'],
            'sha256': sha256(unit['text'].encode()).hexdigest(), 'text': unit['text']}


def proposition(form, subject, object_):
    return {'form': form, 'subject': subject, 'object': object_, 'scope': SCOPE}


def build(source):
    require(source['sha256'] == SOURCE_SHA256
            and sha256(source['text'].encode()).hexdigest() == SOURCE_SHA256, 'Reviewed source changed')
    parents = []
    for slug, subtype, ru, uid in SUBTYPES:
        parents.append({'id': 'definition-' + slug,
                        'text_en': subtype + ' is a subtype of MCI under the WHICAP operational classification.',
                        'text_ru': ru.capitalize() + ' относится к MCI в операциональной классификации WHICAP.',
                        'proposition': proposition('A', subtype, 'WHICAP-classified MCI'),
                        'evidence': evidence(source, uid), 'source_interpretation_author': 'Codex',
                        'expert_validated': False})
    exclusions = [
        ('dementia', 'dementia diagnosed at the consensus conference',
         'диагноз деменции на согласительной диагностической конференции'),
        ('impaired-adl', 'failure of the WHICAP preserved-daily-function criterion',
         'несоответствие критерию сохранности повседневной функции WHICAP'),
    ]
    for slug, condition, ru in exclusions:
        parents.append({'id': 'criterion-' + slug,
                        'text_en': 'No WHICAP-classified MCI case meets: ' + condition + '.',
                        'text_ru': 'Случай, классифицированный как MCI по критериям WHICAP, исключает: ' + ru + '.',
                        'proposition': proposition('E', 'WHICAP-classified MCI', condition),
                        'evidence': evidence(source, 'U23'), 'source_interpretation_author': 'Codex',
                        'expert_validated': False})
    conclusions = []
    for parent in parents[:6]:
        for criterion, (_, condition, ru) in zip(parents[6:], exclusions):
            conclusion = proposition('E', parent['proposition']['subject'], condition)
            premises = [criterion['proposition'], parent['proposition']]
            proof = check(premises, conclusion)
            require(proof['entailed'] and proof['premises_consistent'], 'Licensed definition does not entail conclusion')
            ablations = [check([p], conclusion) for p in premises]
            require(all(not a['entailed'] for a in ablations), 'A claimed necessary premise is redundant')
            conclusions.append({'id': fingerprint({'premises': premises, 'conclusion': conclusion}),
                                'text_ru': 'В этой классификации ' + parent['text_ru'].split(' относится')[0].lower()
                                           + ' исключает ' + ru + ' на том же визите.',
                                'premise_ids': [criterion['id'], parent['id']], 'conclusion': conclusion,
                                'form': 'EAE-1', 'proof': proof, 'premise_removal_checks': ablations,
                                'new_empirical_result': False, 'empirical_forecast': False,
                                'expert_validated': False,
                                'deductive_given_codex_interpretation': True})
    return {'version': VERSION, 'source_sha256': SOURCE_SHA256, 'parents': parents,
            'conclusions': conclusions, 'logical_conclusions': len(conclusions),
            'empirical_forecasts': 0, 'graph_advantage_demonstrated': False,
            'full_map_created': False, 'complete_semantic_coverage': False, 'model_calls': 0,
            'scope_limitation_ru': 'Выводы действуют только внутри операциональных критериев WHICAP и того же визита. '
                                   'Не утверждают отсутствие последующего развития деменции, любой физической инвалидности '
                                   'или всех видов функционального нарушения.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    disable_network()
    root = args.root.resolve() / 'eval/whole_map_forecast/manly-complete-map-v1'
    source = json.loads((root / 'source-v1/source.json').read_text(encoding='utf-8'))
    result = build(source)
    result['implementation_sha256'] = {name: sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                                      for name in ('tools/author_manly_definition_draft.py', 'domain/categorical_logic.py',
                                                   'domain/article_maps.py')}
    run_id = fingerprint(result)
    folder = root / 'definition-draft' / run_id
    write_immutable(folder / 'data.json', json.dumps(result, ensure_ascii=False, indent=2).encode())
    report = ['# WHICAP: новый источник и черновик определений', '',
              'Новый полный английский источник построен непосредственно из PDF. Последняя страница не пересказана. '
              'Сохранена привязка извлечённых слов к координатам; текстовые подписи схемы набора выборки транскрибированы Codex по изображению.', '',
              f"Сформировано {len(result['parents'])} посылок из определений и {len(result['conclusions'])} логических следствий. "
              'Это начало полной формализации, не законченная карта и не новый эмпирический прогноз.', '',
              'Применена форма EAE первой фигуры: ни один M не принадлежит P; каждый S принадлежит M; '
              'следовательно, ни один S не принадлежит P. Перебор моделей подтвердил следование; '
              'удаление любой из двух посылок устраняет следование. Непустота классов не предполагается.', '',
              result['scope_limitation_ru'], '', '## Проверенные следствия', '']
    report.extend(f"{i}. {c['text_ru']}" for i, c in enumerate(result['conclusions'], 1))
    report += ['', '## Охват и ограничения', '',
               'Прежняя частичная карта не использовалась для извлечения. Интерпретация исходных определений подготовлена Codex '
               'и требует экспертной проверки; математическая проверка следования не проверяет истинность или полноту такой интерпретации. '
               'Сопоставление с независимым будущим исследованием и преимущество графа не установлены.', '',
               'Дальше формализуются остальные методы, результаты, все табличные строки, авторские объяснения и ограничения. '
               'Уже выявлены неоднозначности табличных подписей; они не исправляются догадкой. Старые источники, карты и прогоны сохранены. '
               'GOLD и сервисы не изменены. Внешних и локальных модельных вызовов — 0.', '']
    write_immutable(folder / 'report.ru.md', '\n'.join(report).encode())
    print(folder)
    print('Логических следствий:', len(result['conclusions']))


if __name__ == '__main__':
    main()
