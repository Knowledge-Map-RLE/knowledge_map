"""Русский отчёт источниковых ролей с контролем на том же полном корпусе."""
import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines, MODE_RU
from domain.template_barrier_audit import POLICY_RU


def load(path):
    p = Path(path).resolve()
    return FilePredictionStore(p.parent).read_seal(p.name)


def check_variants(result, control):
    original = {tuple(v['key']): v for v in control['part_views']}
    current = {tuple(v['key']): v for v in result['part_views']}
    require(all(current[k] == v for k, v in original.items()), 'Original semantic parts changed')
    extra = [v for key, v in current.items() if key not in original]
    for view in extra:
        p = view['projection_proof']['role_binding_proof']
        old = original[tuple(p['source_part_key'])]
        require(p['source_frame_sha256'] == fingerprint(old['frame']), 'Role source frame differs')
        restored = deepcopy(view['frame']); s = restored['statements'][0]
        for alias in p['aliases']:
            r = next(r for r in s['roles'] if r['role'] == alias['role'])
            require(r['value'] == alias['canonical'], 'Role alias differs'); r['value'] = alias['original']
        for added in p['entry']['add_roles']:
            s['roles'] = [r for r in s['roles'] if r['role'] != added['role']]
        for renamed in p['entry']['rename_roles']:
            next(r for r in s['roles'] if r['role'] == renamed['to'])['role'] = renamed['from']
        expected = deepcopy(old['frame'])
        for f in [restored, expected]: f['statements'][0]['roles'].sort(key=lambda r: r['role'])
        require(restored == expected, 'Binding changed another scientific field')
        require(view['projection_proof']['complete_native_knowledge'] == old['projection_proof']['complete_native_knowledge'],
                'Complete parent changed')
        require(not p['scope_or_number_changed'] and not p['experiments_declared_equivalent']
                and not p['participant_groups_merged'] and not p['new_empirical_result'], 'Binding claims unsupported equivalence')
    return extra


def main():
    parser = argparse.ArgumentParser()
    for name in ('run', 'control', 'barrier', 'control-barrier', 'tests', 'review'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    result, control, barrier, oldbarrier = map(load, [args.run, args.control, args.barrier, args.control_barrier])
    for field in ('references', 'map_hashes', 'families', 'context_audit_sha256', 'model_audit_sha256',
                  'origin_audit_sha256', 'compound_licenses_sha256', 'method_clauses_sha256', 'implementation', 'version', 'limits'):
        require(result['binding'][field] == control['binding'][field], 'Corpus or code differs')
    metadata = deepcopy(result['binding']['metadata']); metadata['input_audit_file_sha256'].pop('role-bindings')
    require(metadata == control['binding']['metadata'], 'Comparison changes more than roles')
    require(control['operation_role_bindings'] is None, 'Explicit role control required')
    require(result['method_clause_projection'] == control['method_clause_projection'], 'Method input differs')
    for forecast, diagnostic in [(result, barrier), (control, oldbarrier)]:
        require(diagnostic['input_run_id'] == forecast['run_id']
                and diagnostic['binding']['input_sha256'] == fingerprint(forecast), 'Diagnosis input differs')
        require(all(not v for v in forecast['predictions'].values()), 'Report must be revised for nonempty forecast')
    require(barrier['binding']['implementation'] == oldbarrier['binding']['implementation'], 'Diagnosis implementation differs')
    extra = check_variants(result, control)
    projection = result['operation_role_bindings']
    require(len(extra) == projection['added_views'] == 12, 'Role projection count differs')
    require(len(result['binding']['references']) == 11 and result['canonical_blocks'] == 943
            and result['licensed_parts'] == 906 and control['licensed_parts'] == 894, 'Report corpus differs')
    tests = Path(args.tests).read_bytes(); suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'Tests failed')
    test_count = sum(int(s.attrib['tests']) for s in suites)
    collision = barrier['modes']['graph']['policies']['relational_structure']['collision_groups']
    require(len(collision) == 1 and len(collision[0]['primary_families']) == 2, 'Structural diagnosis differs')
    lines = ['# Участники операций и границы переноса', '',
        '**Новых научных прогнозов — 0. Преимущество Карты Знаний не установлено.**', '',
        'На том же корпусе 11 карт и 943 канонических знаний введён отдельный источниковый слой участников операций. '
        'Исходные 894 представления сохранены без изменений; добавлено 12, всего стало 906. '
        'Детальная разметка касается двух экспериментальных цепочек, а не всей научной семантики корпуса. '
        'Генератор по-прежнему рассматривает весь доступный корпус без заданного вопроса.', '',
        '## Что изменилось', '',
        'В цепочке TROS клиническое измерение привязано к явно описанной группе лечения; '
        'биологическая модель заболевания представлена ролью вызванного заболевания. '
        'Введён явный контроль PBS для вмешательства и пяти частей его результата. '
        'В Atrosimab выделены объекты ежедневного измерения — клинический балл и масса тела; '
        'индукция EAE связана с введением лечения и двумя частями результата. '
        'Каждое дополнение имеет точную исходную цитату, координаты Unicode, хеши и полный родительский блок. '
        'Связывание через соседние знания разрешено только внутри существующей авторской группы и по явному источниковому свидетельству.', '',
        'Разметка подготовлена Codex и требует экспертной проверки. Она не добавляет наблюдений и не считает '
        'разные части одного опыта независимыми исследованиями. Авторские стрелки и GOLD-карты не изменены. '
        'Из исходных ролей модель общего вида остаётся неразрешённой; роль статистической модели автоматически '
        'не превращается в заболевание. Неизвестные типы и группы сохраняются неизвестными.', '',
        '## Получен общий рисунок участников', '',
        '**Введение лечения в группу с вызванным заболеванием + измерение в этой группе → сообщённое уменьшение проявления относительно контроля.**', '',
        'Раньше совпадали только предикаты без участников. Теперь одна общая форма обнаруживается с сохранением '
        'названий ролей и связности участников, после диагностического обобщения констант и удаления условий. '
        'Она имеет свидетельства двух заявленных первичных семейств — TROS и Atrosimab. '
        'Независимость лабораторий и экспериментальная эквивалентность этим не установлены. '
        'Форма также найдена по соседству без зависимостей, поэтому сама по себе не доказывает преимущество DAG.', '',
        '## Диагностика с сохранением исходных правил', '',
        '| Представление для диагностики | Совпадений между семействами без слоя | Со слоем |',
        '| --- | ---: | ---: |']
    for policy, values in barrier['modes']['graph']['policies'].items():
        lines.append(f"| {POLICY_RU[policy]} | {oldbarrier['modes']['graph']['policies'][policy]['multi_family_collision_groups']} | {values['multi_family_collision_groups']} |")
    lines += ['', 'Ослабления используются исключительно для диагностики. Генератор не получает разрешения '
        'стирать дозы, сроки, ограничения, отрицания или подменять группы ради совпадения.', '',
        '## Повтор полного прогноза', '',
        '| Режим | Неподдержанных шаблонов без слоя / со слоем | Первичных правил | Новых прогнозов |',
        '| --- | ---: | ---: | ---: |']
    for mode, learned in result['learning_by_mode'].items():
        a = control['learning_by_mode'][mode]['learning']['unsupported_templates']
        b = learned['learning']['unsupported_templates']
        lines.append(f"| {MODE_RU[mode]} | {a} / {b} | {len(learned['primary_supported_rules'])} | {len(result['predictions'][mode])} |")
    lines += ['', 'Применение тех же правил без зависимостей тоже даёт ноль прогнозов. '
        'Корпус, код, прежние аудиты, минимальная поддержка двух первичных семейств и бюджет 20 кандидатов одинаковы. '
        'Различается только явно подключённый слой ролей. Рост числа неподдержанных шаблонов не считается научным успехом.', '',
        '## Почему форма пока не является правилом', '',
        'В TROS и Atrosimab различаются генотипы и группы мышей, препараты, контроль PBS и контрольное антитело, '
        'дозы и единицы дозирования, сроки профилактики после иммунизации и лечения проявленной болезни. '
        'Одни названия измерений также не делают их шкалы и итоговые показатели эквивалентными. '
        'В TROS методы указывают шкалу 0–6, а подпись рисунка 3 — 0–5; оба фрагмента сохранены, причина расхождения не установлена. '
        'Неизвестные поля не превращаются в универсальные переменные.', '',
        'Следующий содержательный шаг — отделить форму оператора от области его применимости: '
        'типизированные участники, источник механизма вмешательства, явные ограничения на модель, '
        'объект измерения и фазу лечения. Обобщение разных условий должно иметь собственное основание '
        'и выдавать проверяемую гипотезу с перечисленными отличиями. Оно не должно заявлять тождество экспериментов. '
        'После фиксации такого оператора повторить весь корпус и те же сильные базы; '
        'новый будущий контроль открывать лишь после фиксации допустимых кандидатов.', '',
        '## Проверки', '',
        f'{test_count} тестов через Poetry прошли: происхождение, Unicode-координаты, отказ при смене источника '
        'или версии, запрет копирования между разными популяциями, модальные и отрицательные процедуры, '
        'сохранение отрицаний результатов, отдельные неизменяемые запуски, права доступа, '
        'отсутствие публикации после ошибки и регрессия прогнозирования. '
        'Сеть и модельные вызовы CLI запрещены; будущая цель не читалась. '
        'Это разработка на уже известных источниках, не слепая научная проверка. '
        'Экспертная и визуальная проверка не заявляются.', '',
        'Сервисы и текущие карты UI не менялись; перезапуск не требуется. Цель остаётся недостигнутой.', '',
        f"Основной запуск: `{result['run_id']}`. Контроль: `{control['run_id']}`.", '']
    md = '\n'.join(lines)
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Роли операций и границы переноса</title><style>body{font:17px/1.6 system-ui,sans-serif;margin:30px auto;max-width:1150px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}h1{font-size:28px}h2{font-size:22px;margin-top:32px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>' + render_lines(lines) + '</main></html>'
    data = {'run_id': result['run_id'], 'control_run_id': control['run_id'], 'barrier_run_id': barrier['run_id'],
            'control_barrier_run_id': oldbarrier['run_id'], 'tests': test_count, 'sources': 11, 'knowledge': 943,
            'base_parts': 894, 'parts': 906, 'added_role_views': len(extra),
            'native_role_types': projection['native_role_types'], 'structural_form_families': collision[0]['primary_families'],
            'new_predictions': 0, 'graph_advantage_demonstrated': False, 'model_calls': 0}
    files = {'report.ru.md': md.encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    review = Path(args.review).resolve(); review.mkdir(parents=True, exist_ok=True)
    for name, content in files.items(): write_immutable(review / name, content)
    code = {str(p): sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), Path(__file__).with_name('render_template_barrier_audit.py')]}
    receipt = {'files': {k: sha256(v).hexdigest() for k, v in files.items()}, 'builders': code,
               'tests_sha256': sha256(tests).hexdigest(), 'run_id': result['run_id'], 'control_run_id': control['run_id'],
               'barrier_run_id': barrier['run_id'], 'control_barrier_run_id': oldbarrier['run_id'],
               'new_predictions': 0, 'graph_advantage_demonstrated': False}
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'review': str(review), 'new_predictions': 0, 'added_role_views': len(extra)}))


if __name__ == '__main__':
    main()
