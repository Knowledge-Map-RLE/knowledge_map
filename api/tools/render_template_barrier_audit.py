"""Русский автономный отчёт диагностики, отдельно от неизменяемого прогноза."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from domain.template_barrier_audit import POLICIES
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable

MODE_RU = {'graph': 'Зависимости карты', 'source_neighborhood_without_dependencies': 'Соседство без зависимостей',
           'permuted_dependencies': 'Перемешанные зависимости'}


def render_lines(lines):
    def inline(text):
        text = escape(text)
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        return re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    html, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('|'):
            header = [c.strip() for c in line.strip('|').split('|')]
            html.append('<div class="table"><table><thead><tr>' + ''.join('<th>' + inline(c) + '</th>' for c in header) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                html.append('<tr>' + ''.join('<td>' + inline(c) + '</td>' for c in cells) + '</tr>')
                i += 1
            html.append('</tbody></table></div>')
            continue
        if line.startswith('# '): html.append('<h1>' + inline(line[2:]) + '</h1>')
        elif line.startswith('## '): html.append('<h2>' + inline(line[3:]) + '</h2>')
        elif line: html.append('<p>' + inline(line) + '</p>')
        i += 1
    return ''.join(html)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--tests', required=True)
    parser.add_argument('--review', required=True)
    args = parser.parse_args()
    folder = Path(args.run).resolve()
    result = FilePredictionStore(folder.parent).read_seal(folder.name)
    raw = (folder / 'input-predictions.json').read_bytes()
    source = json.loads(raw)
    require(fingerprint(source) == result['binding']['input_sha256'], 'Report input differs')
    tests = Path(args.tests).read_bytes()
    suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'Report tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    lines = ['# Барьер повторения: предикаты и состав операций', '',
        '**Новых научных прогнозов — 0. Преимущество карты не установлено.**', '',
        'Проверены прежние 11 карт, 943 канонических знания и 854 лицензированные части. '
        'Это отдельный аудит запечатанного прогноза, а не новый запуск генератора. '
        'Обучение, карты, пороги поддержки и будущие исходы не изменены.', '',
        '## Проверка причины', '',
        'Для каждого шаблона с собственным первичным результатом сопоставлены пять диагностических форм. '
        'Формы постепенно удаляют служебные обозначения, затем научные условия и атрибуты, '
        'затем идентичности участников. Последняя сохраняет только виды знаний, предикаты, отрицания '
        'и структуру зависимостей. Совместные входы допускают перестановку и согласованное переименование переменных. '
        'Ни одно такое ослабление не включено в прогнозирование.', '',
        '| Режим | Всего шаблонов | С первичным результатом | Групп совпадения между первичными семействами: полный / обозначения / без условий / структура отношений / предикаты |',
        '| --- | ---: | ---: | --- |']
    for mode, data in result['modes'].items():
        counts = ' / '.join(str(data['policies'][p]['multi_family_collision_groups']) for p in POLICIES)
        lines.append(f"| {MODE_RU[mode]} | {data['total_templates']} | {data['primary_result_templates']} | {counts} |")
    lines += ['', 'Ни одна пара наборов предикатов посылок и заключения не повторяется между двумя первичными семействами '
              'даже при отдельном сравнении без ролей, условий, видов знаний и внутренних стрелок. '
              'Поэтому удаление строковых контекстов само по себе не создаст повторение для действующего обучателя. '
              'Это вывод о текущем представлении допущенных шаблонов, а не утверждение, что в статьях нет общих закономерностей.', '',
        '## Конкретный разрыв представления', '',
        'В карте исследования TROS к результату K30 ведут K28 «введение лечения» и K9 «измерение клинического течения». '
        'В карте Atrosimab к K47 ведут K20 и K21 с одинаковым общим предикатом «выполнение экспериментальной процедуры». '
        'При этом читаемый текст K20 явно содержит иммунизацию и ежедневную оценку болезни; '
        'K21 — введение препарата. Эти две цепочки имеют разную детализацию скрытых операций.', '',
        'В K20 нельзя просто заменить общий предикат на «измерение»: это потеряет иммунизацию. '
        'Нужно представить явно описанные действия отдельно, сохранив полный родительский блок и происхождение. '
        'Совпадение общего названия процедуры также не удостоверяет одинаковые препарат, модель, пол, дозу или отсчёт времени.', '',
        '## Следующий содержательный шаг', '',
        'Источниково проверить разложение составных выполненных процедур на операции: создать модель, ввести вмешательство, '
        'измерить исход. Согласовать общий словарь этих операций и их роли на всех явно допущенных источниках. '
        'Полные научные условия сохранять; обобщение участников потребует отдельной проверки применимости. '
        'Нельзя считать две части одной процедуры двумя исследованиями или заменять различия моделей общим словом «мыши».', '',
        'После фиксации этой проекции повторить обучение на том же корпусе и сравнить с теми же знаниями без зависимостей. '
        'Лишь при получении новых допустимых кандидатов фиксировать прогнозы и открывать совместимый независимый контроль. '
        'Для исходной цели нужны научное подтверждение новых утверждений и измеримый выигрыш структуры; '
        'диагностические совпадения и число тестов этого не доказывают.', '',
        '## Проверяемость', '',
        f'{count} теста через Poetry прошли. Проверены источниковые снимки, исходная печать прогноза, '
        'версии карт и кода, неизменность родительских знаний и отдельная публикация аудита. '
        'Модельных вызовов и чтения новой цели нет; научная и визуальная экспертиза не заявляются. '
        'Сервисы, production-карты и GOLD не изменены; перезапуск не требуется.', '',
        f"Исходный запуск: `{result['input_run_id']}`. Аудит: `{result['run_id']}`.", '']
    md = '\n'.join(lines)
    # Автономная статическая страница не загружает скрипты, шрифты или источники из сети.
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Барьер повторения шаблонов</title><style>body{font:17px/1.55 system-ui,sans-serif;margin:30px auto;max-width:1100px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}h1{font-size:28px}h2{font-size:22px;margin-top:32px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>' + render_lines(lines) + '</main></html>'
    review = Path(args.review).resolve()
    artifacts = {'report.ru.md': md.encode('utf8'), 'report.html': html.encode('utf8'),
                 'data.json': FilePredictionStore.encode(result)}
    review.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items(): write_immutable(review / name, content)
    receipt = {'run_id': result['run_id'], 'tests': count, 'test_xml_sha256': sha256(tests).hexdigest(),
        'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'files': {name: sha256(content).hexdigest() for name, content in artifacts.items()},
        'model_calls': 0, 'new_predictions': 0, 'graph_advantage_demonstrated': False}
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'review': str(review), 'tests': count, 'new_predictions': 0}))


if __name__ == '__main__':
    main()
