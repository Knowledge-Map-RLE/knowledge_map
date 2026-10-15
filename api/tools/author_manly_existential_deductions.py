"""Частные логические следствия с источниковым свидетельством непустоты подтипов."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from domain.article_maps import fingerprint, require
from domain.categorical_logic import check
from domain.source_count_witness import positive_count_witness, check_with_witness
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--definitions', type=Path, required=True)
    parser.add_argument('--tables', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    disable_network()
    source, definitions, tables = [json.loads(p.read_text(encoding='utf-8'))
                                    for p in (args.source, args.definitions, args.tables)]
    require(source['sha256'] == definitions['source_sha256'] == tables['source_sha256'], 'Inputs belong to different sources')
    parents = {p['id']: p for p in definitions['parents']}
    table1 = {r['row_index']: r for r in tables['rows'] if r['table'] == 1}
    mapping = [('amnestic', 2), ('executive', 5), ('language', 6), ('visuospatial', 7), ('mcdm', 3), ('mcdn', 8)]
    results = []
    for slug, row_index in mapping:
        parent = parents['definition-' + slug]
        row = table1[row_index]
        cell = next(c for c in row['cells'] if c['column'] == 'cases')
        subject = parent['proposition']['subject']
        witness = positive_count_witness(source, cell, subject, parent['proposition']['scope'],
            {'subject': subject, 'source_unit_id': row['source_unit_id'], 'source_row_id': row['id'], 'author': 'Codex',
             'printed_row_label': row['label_en'], 'definition_binding': parent['id'],
             'scope_interpretation_ru': 'Случаи первого MCI при последующих визитах в той же операциональной классификации; '
                                        'каждый случай рассматривается на его собственном диагностическом визите.',
             'expert_validated': False})
        for criterion_id in ('criterion-dementia', 'criterion-impaired-adl'):
            criterion = parents[criterion_id]
            conclusion = {**parent['proposition'], 'form': 'O', 'object': criterion['proposition']['object']}
            premises = [criterion['proposition'], parent['proposition']]
            proof = check_with_witness(premises, conclusion, witness)
            without_existence = check(premises, conclusion)
            removed = [check([p], conclusion, (subject,)) for p in premises]
            require(proof['entailed'] and not without_existence['entailed']
                    and all(not p['entailed'] for p in removed), 'Three necessary grounds were not established')
            results.append({'subtype': subject, 'source_reported_cases': cell['value'], 'conclusion': conclusion,
                            'form': 'EAO-1', 'premise_ids': [criterion_id, parent['id']], 'proof': proof,
                            'without_existence': without_existence, 'removed_universal_premises': removed,
                            'empirical_prediction': False, 'expert_validated': False})
    result = {'version': 'manly-source-existence-eao-1', 'source_sha256': source['sha256'], 'conclusions': results,
              'logical_conclusions': len(results), 'new_empirical_predictions': 0, 'graph_advantage_demonstrated': False,
              'model_calls': 0, 'full_map_created': False,
              'input_hashes': {name: sha256(path.read_bytes()).hexdigest() for name, path in
                               [('source', args.source), ('definitions', args.definitions), ('tables', args.tables)]},
              'implementation_sha256': {name: sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                                       for name in ('domain/source_count_witness.py', 'domain/categorical_logic.py',
                                                    'tools/author_manly_existential_deductions.py', 'domain/article_maps.py')}}
    folder = args.output / fingerprint(result)
    write_immutable(folder / 'data.json', json.dumps(result, ensure_ascii=False, indent=2).encode())
    report = ['# WHICAP: силлогизм со свидетельством существования', '',
              'Получены 12 частных логических следствий по форме EAO первой фигуры. Это следствия '
              'подготовленной Codex интерпретации определений и напечатанных счётчиков, а не 12 новых клинических результатов.', '',
              'Три основания: ни один M не принадлежит P; все S принадлежат M; в источнике зарегистрировано '
              'положительное число S. Следовательно, некоторые S не принадлежат P. Без свидетельства существования '
              'этот вывод недопустим. Удаление любой универсальной посылки также нарушает следование.', '',
              '| Подтип | Положительное число случаев в таблице 1 |', '| --- | ---: |']
    for slug, row_index in mapping:
        row = table1[row_index]
        cases = next(c['value'] for c in row['cells'] if c['column'] == 'cases')
        report.append(f"| {row['label_ru']} | {cases} |")
    report += ['', 'Для каждого из этих шести подтипов получены два заключения: в напечатанной выборке '
               'существовали классифицированные случаи, исключавшие диагноз деменции на том же визите; '
               'существовали случаи, не нарушавшие принятого операционального критерия сохранности повседневной функции.', '',
               'Не утверждается отсутствие последующей деменции, любой физической инвалидности или скрытой AD-патологии. '
               'Существование относится к зарегистрированным случаям классификации, а не к любому одноимённому классу '
               'из другой статьи. Положительная ставка или процент сами по себе не принимаются как счётчик пациентов.', '',
               'Форма EAO-1 относится к формам, требующим существования. В прежнем черновике использовалась EAE-1 '
               'без такого требования. Теперь показано применение обеих форм к одному источнику с явным различением оснований. '
               'Остальные силлогистические формы автоматически не считаются применёнными.', '',
               'Проверка моделей подтверждает математическое следование при заданной интерпретации посылок. '
               'Точность клинической классификации и истинность напечатанных счётчиков экспертно не проверены. '
               'Полная карта и преимущество прогнозирования ещё не достигнуты. Модельных вызовов — 0.', '']
    write_immutable(folder / 'report.ru.md', '\n'.join(report).encode())
    print(folder)
    print('Частных логических следствий:', len(results))


if __name__ == '__main__':
    main()
