"""Русский отчёт пары одинаковых корпусов с единственным новым источниковым слоем."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines, MODE_RU


def load(path):
    path = Path(path).resolve()
    return FilePredictionStore(path.parent).read_seal(path.name)


def main():
    parser = argparse.ArgumentParser()
    for flag in ('run', 'control', 'barrier', 'tests', 'review'):
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    result, control, barrier = load(args.run), load(args.control), load(args.barrier)
    for field in ('references', 'map_hashes', 'families', 'context_audit_sha256', 'model_audit_sha256',
                  'origin_audit_sha256', 'compound_licenses_sha256', 'implementation', 'version', 'limits'):
        require(result['binding'][field] == control['binding'][field], 'Comparison input or code differs')
    metadata = json.loads(json.dumps(result['binding']['metadata']))
    metadata['input_audit_file_sha256'].pop('method-clauses')
    require(metadata == control['binding']['metadata'], 'Comparison changes more than method clauses')
    require(control['method_clause_projection'] is None and result['method_clause_projection'] is not None,
            'Explicit method control required')
    require(barrier['input_run_id'] == result['run_id'] and barrier['binding']['input_sha256'] == fingerprint(result),
            'Barrier diagnosis belongs to a different forecast')
    baseline = {tuple(v['key']): v for v in control['part_views']}
    current = {tuple(v['key']): v for v in result['part_views']}
    require(all(current[k] == v for k, v in baseline.items()), 'Original semantic parts changed')
    extra = [v for k, v in current.items() if k not in baseline]
    for v in extra:
        p = v['projection_proof']['method_clause_proof']
        original = baseline[tuple(p['source_part_key'])]
        restored = json.loads(json.dumps(v['frame']))
        restored['statements'][0]['predicate'] = p['original_predicate']
        require(restored == original['frame'], 'Method operation removed a participant or constraint')
    tests = Path(args.tests).read_bytes(); suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'Tests failed')
    test_count = sum(int(s.attrib['tests']) for s in suites)
    projection = result['method_clause_projection']
    lines = ['# Источниковые операции выполненных процедур', '',
        '**Новых научных прогнозов — 0. Преимущество карты не установлено.**', '',
        'На прежнем корпусе 11 карт и 943 канонических знаний добавлен отдельный слой анализа методов. '
        'Из 136 выполненных действий в допущенном срезе 111 имеют происхождение собственного метода первичного исследования. '
        'У 33 общий предикат не описывает операцию. Проверены 57 связанных исходных фрагментов; '
        'разметка Codex имеет статус «требует экспертной проверки». Это не аудит полноты семантики всех статей.', '',
        '## Что представлено', '',
        'Из 31 общего описания выделены 40 явно описанных операций: введение вмешательства, создание модели заболевания, '
        'измерение клинического течения, биомаркеров, когниции и концентрации препарата, подготовка образца, '
        'микроскопия, связывание рецептора и анализ данных. Участники, числа, отрицания и ограничения исходной части '
        'не удаляются. Они наследуются из полного родителя, а не переадресуются новому действию как его собственные параметры.', '',
        'Исходные 854 части сохранены без изменений; всего стало 894 представления. '
        'Новые операции не являются новыми наблюдениями или независимыми исследованиями. '
        'Авторские группы и направления исходного DAG сохранены; новые стрелки не добавлены.', '',
        '78 методов с конкретными предикатами оставлены без угадывания синонимов. Два общих описания не разделены: '
        'несколько модельных линий в первичной работе по болезни Альцгеймера и два режима проверки Atrosimab '
        'с наличием и отсутствием TNF. Им нужно раздельное связывание контекстов; условия не стираются ради допуска.', '',
        '## Повторение формы появилось', '',
        'После разложения K20 Atrosimab на иммунизацию и ежедневное измерение, а K21 — на введение лечения, '
        'появилась общая форма с исследованием TROS:', '',
        '**Введение лечения + измерение клинического течения → уменьшение измеренного проявления.**', '',
        'Она встречается в двух заявленных первичных экспериментальных семействах: TROS и Atrosimab. '
        'Разные части результата или повторные применения одной статьи не считаются новыми семействами. '
        'Независимость лабораторий не заявляется.', '',
        'Это совпадение предикатов и структуры, не подтверждённое правило переноса. '
        'При сохранении ролей, их связности, доз, моделей и времени полные шаблоны не совпадают. '
        'Такая же грубая форма появляется в базе соседства без зависимостей; преимущества графа она не доказывает.', '',
        '## Полный контрольный прогон', '',
        '| Режим | Неподдержанных шаблонов без слоя / со слоем | Поддержанных первичных правил | Прогнозов |',
        '| --- | ---: | ---: | ---: |']
    for mode, learned in result['learning_by_mode'].items():
        a = control['learning_by_mode'][mode]['learning']['unsupported_templates']
        b = learned['learning']['unsupported_templates']
        lines.append(f"| {MODE_RU[mode]} | {a} / {b} | {len(learned['primary_supported_rules'])} | {len(result['predictions'][mode])} |")
    lines += ['', 'Применение тех же правил без зависимостей также даёт ноль прогнозов. '
        'Код, карты, прежние аудиты и настройки двух запусков одинаковы. '
        'Различается только явное подключение нового источникового слоя. Рост числа шаблонов не считается научным улучшением.', '',
        '## Следующий барьер', '',
        'Нужно источниково связать роли операций: что введено, в какой группе, что измерено и каким способом. '
        'Сейчас клиническое измерение TROS содержит роли модели и исхода, а общее описание Atrosimab — модели и популяции; '
        'одно переименование предиката не восстанавливает отсутствующие роли. '
        'Точные генотипы, разные препараты, дозы и отсчёты времени остаются научными различиями, '
        'а не служебными обозначениями.', '',
        'Следующий слой должен хранить типизированные роли и явные ограничения применимости, '
        'позволяя сравнивать структуру операций без объявления разных экспериментов эквивалентными. '
        'После него повторить тот же корпус и сильные базы; новые будущие результаты открывать лишь после фиксации допустимого прогноза.', '',
        '## Воспроизводимость', '',
        f'{test_count} тестов через Poetry прошли. Проверены отказ при изменённых источниках, координатах, '
        'родителях и версиях, отказ для цитируемых, запланированных, отрицательных и модальных процедур, '
        'сохранность чисел и областей действия и регрессия обучателя. '
        'Сеть и модельные вызовы в CLI запрещены. Экспертная научная и визуальная проверка не заявляются.', '',
        'Сервисы, production-карты и GOLD не изменены; перезапуск не требуется. '
        'Исходная цель свободного прогнозирования по всей карте с преимуществом её структуры остаётся недостигнутой.', '',
        f"Основной запуск: `{result['run_id']}`. Контроль: `{control['run_id']}`. Диагностика: `{barrier['run_id']}`.", '']
    md = '\n'.join(lines)
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Источниковые операции методов</title><style>body{font:17px/1.6 system-ui,sans-serif;margin:30px auto;max-width:1100px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}h1{font-size:28px}h2{font-size:22px;margin-top:32px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>' + render_lines(lines) + '</main></html>'
    data = {'run_id': result['run_id'], 'control_run_id': control['run_id'], 'barrier_run_id': barrier['run_id'],
            'projection': projection, 'tests': test_count, 'new_predictions': 0, 'graph_advantage_demonstrated': False}
    files = {'report.ru.md': md.encode('utf8'), 'report.html': html.encode('utf8'), 'data.json': FilePredictionStore.encode(data)}
    review = Path(args.review).resolve(); review.mkdir(parents=True, exist_ok=True)
    for name, content in files.items(): write_immutable(review / name, content)
    code = {str(p): sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), Path(__file__).with_name('render_template_barrier_audit.py')]}
    receipt = {'files': {k: sha256(v).hexdigest() for k, v in files.items()}, 'builders': code,
               'tests_sha256': sha256(tests).hexdigest(), 'run_id': result['run_id'], 'control_run_id': control['run_id'],
               'barrier_run_id': barrier['run_id'], 'new_predictions': 0, 'graph_advantage_demonstrated': False}
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'review': str(review), 'new_predictions': 0, 'added_method_views': len(extra)}))


if __name__ == '__main__':
    main()
