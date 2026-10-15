"""Русский отчёт нового логического следствия и полного реестра определений."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines


def main():
    parser = argparse.ArgumentParser()
    for name in ('run', 'control', 'inventory', 'tests', 'review'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); root = Path(args.run).resolve(); control = Path(args.control).resolve()
    current = FilePredictionStore(root.parent).read_seal(root.name)
    previous = FilePredictionStore(control.parent).read_seal(control.name)
    for field in ('sources', 'families', 'metadata', 'map_hashes', 'implementation', 'context_audit_sha256',
                  'model_audit_sha256', 'origin_audit_sha256', 'limits', 'version', 'dictionary_sha256'):
        require(current['binding'][field] == previous['binding'][field], 'Definition paired input differs')
    for field in ('predictions', 'numeric_consequences', 'categorical_inference'):
        require(current[field] == previous[field], 'Unrelated inference changed')
    logic, old = current['licensed_categorical_inference'], previous['licensed_categorical_inference']
    before = {c['id'] for c in old['consequences']['without_dependencies']}
    after = {c['id'] for c in logic['consequences']['without_dependencies']}
    added = [c for c in logic['consequences']['without_dependencies'] if c['id'] not in before]
    require(before <= after and len(added) == 1 and len(after) == 3, 'Expected one extra logical consequence')
    require(all(c['proof']['entailed'] and c['proof']['countermodels'] == 0 for c in added), 'Extra consequence is not entailed')
    raw_inventory = Path(args.inventory).read_bytes(); inventory = json.loads(raw_inventory)
    require(inventory['categorical_license_sha256'] == logic['audit_sha256']
            and inventory['definition_blocks'] == len(inventory['rows']) == 26
            and inventory['canonical_blocks'] == current['canonical_blocks'] == 943, 'Definition inventory differs')
    raw_tests = Path(args.tests).read_bytes(); suites = ET.fromstring(raw_tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == int(s.attrib.get('skipped', 0)) == 0
                          for s in suites), 'Definition tests did not pass')
    tests = sum(int(s.attrib['tests']) for s in suites)
    names = {'graph': 'Совместные предпосылки исходной карты', 'without_dependencies': 'Семантический поиск без стрелок',
             'source_neighborhood': 'Соседство источника', 'permuted_dependencies': 'Перемешанные зависимости'}
    lines = ['# Логический вывод из структурного противопоставления', '',
        '**Один дополнительный условный логический вывод. Всего три; новых эмпирических прогнозов — ноль. '
        'Преимущество исходного DAG не установлено.**', '',
        'Обработаны те же 11 карт и 943 канонических знания. Источниковые определения проверяются отдельно '
        'от ассоциаций и результатов вмешательств. Код, научные источники и остальные аудиты двух прогонов '
        'одинаковы; изменена только явно заданная логическая лицензия.', '', '## Дополнительный вывод', '',
        '**Классы TNFR1 и TNFR2 в структурном описании данного обзора не пересекаются.**', '',
        'Первая посылка: TNFR1 в этом описании содержит внутриклеточный death domain. Вторая: TNFR2 '
        'его не содержит. Поэтому один объект не может одновременно принадлежать обоим описанным классам.', '',
        'Это EAE второй фигуры: ни один P не относится к M; все S относятся к M; следовательно, '
        'ни один S не относится к P. Здесь S — TNFR1, P — TNFR2, M — структуры с указанным доменом. '
        'Большая и малая посылки упорядочены по их логической роли, независимо от порядка в тексте.', '',
        'Источник — обзор PMC5436834, полный составной блок K11. Обе части противопоставления '
        'прямо утверждены в исходном абзаце U13. Канонический блок, противопоставление, лиганд, '
        'атрибуты и исходные фрагменты сохранены. Для свойства не придуман отдельный исходный concept_id: '
        'оно привязано к существующему предикату и отпечатку всех дополнительных ограничений.', '',
        'Область — структурные определения именно этого обзора. Вывод не относится автоматически '
        'к генетически изменённым конструкциям, не предсказывает апоптоз, выживание, ответ на препарат '
        'или эффективность у человека. Научная новизна не заявляется: это формализация следствия '
        'известного противопоставления. Разметка Codex требует экспертной проверки.', '',
        '## Полный реестр определений', '',
        f"Во всех 943 знаниях найдено {inventory['definition_blocks']} блоков с меткой определения "
        f"и {inventory['definition_statements']} их семантических утверждений. Реестр перечисляет каждый блок "
        'с полным родителем, исходными фрагментами, хешами и русской причиной решения. Три родителя '
        'имеют отдельные лицензии частей; остальные 23 сохранены без категорического преобразования.', '',
        'Метка определения сама по себе не даёт универсального квантора. Числовые пороги требуют '
        'интервальных операторов; механизм — отдельного предметного оператора; модальность сохраняется. '
        'Например, минимальное влияние на повседневную жизнь не объявлено полным отсутствием влияния, '
        'а критерии Petersen не отождествлены с классом пациентов. Реестр не доказывает, что среди '
        'других видов знания нет неверно размеченных определений.', '',
        '| Статья | Блок | Решение и ограничение |', '| --- | --- | --- |']
    lines += [f"| {row['pmcid'].upper()} | {row['knowledge_id']} | {row['reason_ru']} |" for row in inventory['rows']]
    lines += ['', '## Контрольные режимы', '', '| Поиск посылок | Прежняя лицензия | Расширенная лицензия |', '| --- | ---: | ---: |']
    lines += [f"| {names[mode]} | {len(old['consequences'][mode])} | {len(values)} |" for mode, values in logic['consequences'].items()]
    lines += ['', 'Два прежних вывода о критерии MCI для его подтипов сохранены. Новый вывод требует '
        'двух самостоятельных утверждений одного составного родителя. Это не два независимых исследования. '
        'Граф доказательства хранится отдельно; стрелки исходной карты задним числом не добавлены.', '',
        'Поиск с исходными зависимостями не сформировал эти выводы. Семантический поиск без стрелок '
        'дал три. Следовательно, результат пока показывает полезность типизированных операторов '
        'и скрытой семантики, а не преимущество существующих зависимостей.', '',
        '## Остальные результаты', '',
        'Эмпирические генераторы во всех режимах по-прежнему дают ноль новых гипотез. '
        'Сохранился 151 арифметический результат интерпретации уже опубликованных чисел. '
        'По 20 выбранных элементов известных знаний и частотной базы не являются совпадениями '
        'с будущей целью. Логическое следствие не подменяет требуемое независимое эмпирическое подтверждение.', '',
        '## Проверка и продолжение', '',
        f'{tests} проверок через Poetry прошли: сохранность прежних лицензий, отрицания, независимость '
        'частей противопоставления, контекст свойства, отсутствие скрытого существования, '
        'неизменяемая публикация и отказ при недопустимых посылках.', '',
        'Следующие содержательные направления: типизированные операции для остальных определений '
        'и независимый эмпирический перенос. Вклад зависимости следует измерять отдельно от '
        'вклада семантики на одинаковых знаниях и бюджете; правильность нового силлогизма '
        'не является доказательством преимущества карты.', '',
        'Модельных и сетевых вызовов нет. Старые артефакты, GOLD и production-карты сохранены. '
        'Живые сервисы не менялись; перезапуск не требуется. Экспертная и визуальная проверки не заявляются.', '',
        f"Основной запуск: `{current['run_id']}`. Контроль: `{previous['run_id']}`.", '']
    markdown = '\n'.join(lines)
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Источниковые логические определения</title><style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1150px;padding:0 18px;background:#f3f6fa;color:#172435}main{background:white;padding:28px;border:1px solid #cbd7e4;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd7e4;padding:10px;text-align:left}th{background:#edf3f9}code{overflow-wrap:anywhere}.table{overflow:auto}</style><main>' + render_lines(lines) + '</main></html>'
    data = {'run_id': current['run_id'], 'control_run_id': previous['run_id'], 'sources': 11, 'canonical_blocks': 943,
        'definition_blocks': 26, 'definition_statements': inventory['definition_statements'], 'licensed_parents': 3,
        'licensed_views': logic['licensed_views'], 'added_conclusions': added, 'conclusions_total': 3,
        'logical_counts': {mode: len(values) for mode, values in logic['consequences'].items()},
        'previous_logical_counts': {mode: len(values) for mode, values in old['consequences'].items()},
        'tests': tests, 'new_empirical_predictions': 0, 'graph_advantage_demonstrated': False, 'model_calls': 0}
    files = {'report.ru.md': markdown.encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data),
             'definition-inventory.json': raw_inventory}
    output = Path(args.review).resolve(); output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items(): write_immutable(output / name, content)
    builders = {str(p): sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(__file__).with_name('render_template_barrier_audit.py'))}
    write_immutable(output / 'verification.json', FilePredictionStore.encode({'files': {name: sha256(content).hexdigest() for name, content in files.items()},
        'builders': builders, 'tests_sha256': sha256(raw_tests).hexdigest(), 'main_snapshot': str(root), 'control_snapshot': str(control)}))
    print(json.dumps({k: v for k, v in data.items() if k != 'added_conclusions'}, ensure_ascii=False))


if __name__ == '__main__': main()
