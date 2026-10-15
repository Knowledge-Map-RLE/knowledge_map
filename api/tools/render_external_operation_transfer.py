"""Русский отчёт внешнего переноса сохраняет временные ограничения отдельно."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.external_operation_inputs import FileExternalReceivers, FileExternalOutcomes
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network

MODE_RU = {'graph': 'Совместные предпосылки карты', 'without_dependencies': 'Те же знания без зависимостей',
           'permuted_dependencies': 'Перемешанные зависимости'}


def main():
    parser = argparse.ArgumentParser()
    for field in ('run', 'evaluation', 'tests', 'review'): parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network(); folder = Path(args.run).resolve()
    result = FilePredictionStore(folder.parent).read_seal(folder.name)
    evaluation_path = folder / 'evaluations' / (args.evaluation + '.json')
    evaluation = json.loads(evaluation_path.read_bytes())
    require(fingerprint(evaluation) == args.evaluation and evaluation['forecast_sha256'] == fingerprint(result), 'Evaluation differs')
    methods = FileExternalReceivers(folder / 'external-methods.json', folder / 'external-source.json').load()
    outcomes = FileExternalOutcomes(folder / 'external-outcomes.json', folder / 'external-source.json').load()
    require(fingerprint(methods) == result['binding']['receiver_packet_sha256'], 'Methods differ')
    descriptor = json.loads((folder / 'input-corpus.json').read_bytes())
    applicability_root = Path(descriptor['snapshot'])
    upstream_root = Path(json.loads((applicability_root / 'input-corpus.json').read_bytes())['snapshot'])
    upstream_index = json.loads((upstream_root / 'inputs-manifest.json').read_bytes())
    exposure = []
    for entry in upstream_index['sources']:
        raw_map = (upstream_root / entry['map_path']).read_bytes()
        require(sha256(raw_map).hexdigest() == entry['map_file_sha256'], 'Exposure map bytes differ')
        m = json.loads(raw_map)
        if '10.1038/s41598-018-31957-7' not in m['source']['text']: continue
        units = [u for u in m['source']['units'] if 'atrosab' in u['text'].lower()
                 and any(t in u['text'].lower() for t in ('eae', 'encephalomyelitis', 'multiple sclerosis'))]
        exposure.append({'article_id': m['article_id'], 'run_id': m['run_id'],
            'source_sha256': m['source']['sha256'], 'citation_doi': '10.1038/s41598-018-31957-7',
            'units': units, 'scope_ru': 'Ссылка и тематические фрагменты уже входят в полный обучающий источник; '
                'это аудит прежнего доступа, не автоматическое установление эквивалентности каждого результата.'})
    require(exposure, 'Expected secondary exposure audit missing')
    tests_path = Path(args.tests).resolve(); test_bytes = tests_path.read_bytes()
    suites = ET.fromstring(test_bytes).findall('testsuite')
    require(suites and all(int(s.attrib.get(k, 0)) == 0 for s in suites for k in ('failures', 'errors', 'skipped')), 'Tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    rows = []
    for mode, folds in result['modes'].items():
        candidates = [c for f in folds for c in f['predictions']]
        assessed = evaluation['modes'][mode]
        require(len(candidates) == len(assessed) and all(not r['independent_scientific_confirmation'] for r in assessed), 'External assessment differs')
        rows.append({'mode': mode, 'name_ru': MODE_RU[mode], 'hypotheses': len(candidates),
            'coarse_direction_matches': sum(r['coarse_direction_matches'] for r in assessed),
            'temporal_unresolved': sum(r['relation'] == 'direction_match_temporal_scope_unresolved' for r in assessed),
            'scientific_confirmations': 0})
    lines = ['# Внешний перенос: совпадение направления и границы времени', '',
        '**Две условные гипотезы, два диагностических совпадения общего направления. '
        'Новых подтверждённых научных знаний — ноль; преимущество исходного DAG не установлено.**', '',
        '## Входы и способ получения', '',
        f"Обучающий корпус прежний: {result['coverage']['sources']} карт, {result['coverage']['canonical_blocks']} канонических знаний. "
        'Отдельный файл внешних исходов не передан обучающему оператору. Оператор использует три ранее размеченных контракта '
        'TROS и Atrosimab; терапевтический паттерн поддержан двумя семействами. Остальные знания корпуса '
        'не получили автоматически вымышленных контрактов этого оператора.', '',
        'Внешний источник — PMC6133964, DOI 10.1038/s41598-018-31957-7. Сохранены полный XML, '
        'Markdown, 70 фрагментов и все 50 библиографических ссылок. Из него подготовлены только две '
        'проекции методов: первоначальный четырёхдозовый курс ATROSAB и первоначальный курс H398. '
        'Это не полная карта новой статьи, не двенадцатая обучающая карта и не два независимых исследования.', '',
        'Схема оператора: выполненное введение селективного антагониста человеческого TNFR1 и '
        'измерение клинического течения в той же популяции с индуцированным EAE → гипотеза меньшего '
        'клинического бремени относительно явно связанного контроля. Это эмпирическое обобщение '
        'структуры действий и участников, а не силлогизм или доказанный причинный закон.', '',
        'Совпали семь грубых осей: мыши, модель MOG35–55 EAE, внеклеточная человеческая мишень TNFR1, '
        'селективное подавление, внутрибрюшинное введение, проявившаяся болезнь и порядковая клиническая шкала. '
        'Полные дозы, генотипы, пол, контроль, шкалы и расписания сохранены как ограничения переноса. '
        'Совпадение этих семи осей не удостоверяет эквивалентность опытов.', '',
        '## Две гипотезы и оценка', '',
        'ATROSAB: при описанном первоначальном введении 20 мг/кг в дни 1, 4, 8 и 12 после начала EAE '
        'ожидается меньшее клиническое бремя относительно контрольного антитела.', '',
        'H398: при описанном первоначальном введении 20 мг/кг в те же дни ожидается меньшее '
        'клиническое бремя относительно контрольного IgG. Размер эффекта и значимость не предсказываются.', '',
        '| Режим | Гипотезы | Совпадение общего направления | Время не разрешено | Полные научные подтверждения |',
        '| --- | ---: | ---: | ---: | ---: |']
    lines += [f"| {r['name_ru']} | {r['hypotheses']} | {r['coarse_direction_matches']} | {r['temporal_unresolved']} | 0 |" for r in rows]
    lines += ['', '## Обнаруженное ограничение', '',
        'Генератор пока не задаёт временное окно заключения. Поэтому совпадение направления нельзя '
        'читать как обещание устойчивого эффекта на всём протяжении наблюдения.', '',
        'Для ATROSAB текст результатов описывает уменьшение тяжести до дня 24 при наблюдении до дня 28. '
        'У части животных к завершению опыта ответ терялся. Корреляция с антителами к препарату '
        '(r=0,75; n=6; p=0,086) не доказывает причинный механизм потери ответа.', '',
        'Для H398 улучшение описано примерно до дня 35, затем — рецидив. Повторный курс является '
        'изменением вмешательства и не приписывается исходному четырёхдозовому курсу. День 85 относится '
        'к гистопатологии; он не подставлен как явно установленный конец клинического наблюдения.', '',
        'В подписи ATROSAB и основном тексте сроки сформулированы по-разному; дальнейшее временное '
        'сопоставление должно сохранять оба сообщения. Один общий знак эффекта этого не разрешает.', '',
        '## Что показывает сравнение', '',
        'Исходные зависимости и те же знания без зависимостей дали одинаковые две гипотезы. '
        'Перемешивание не дало кандидатов. Последнее подтверждает чувствительность данного оператора '
        'к неправильной группировке, но не преимущество перед сильной семантической базой без стрелок. '
        'Поиск посылок этой базы здесь ограничен теми же размеченными контрактами, а не всеми возможными '
        'комбинациями полного корпуса.', '',
        '## Ограничения дизайна', '',
        'Исходы статьи уже были раскрыты поиском и прочитаны Codex до подготовки проекций. '
        'Работа 2018 года старше части обучающих источников, включая Atrosimab 2021 года. '
        'Это ретроспективная инженерная проверка переноса, не слепой и не хронологический будущий контроль. '
        'Адаптер читает полный текст для проверки координат; генератор получает только методы и контекст. '
        'Отдельный порт исходов открывается после сохранения неизменяемых кандидатов.', '',
        'Дополнительный аудит обнаружил ссылку на этот внешний DOI в полном обучающем тексте Atrosimab. '
        'Там прямо упомянута терапевтическая активность ATROSAB при EAE; соответствующие фрагменты сохранены '
        'в отдельном аудите. Поэтому отсутствие внешнего файла исходов в генераторе не означает отсутствия '
        'прежнего доступа к содержанию через цитирующий источник. Новизна двух гипотез относительно '
        'полных обучающих текстов не установлена; ATROSAB уже описан в таком тексте.', '',
        'Результат не даёт оценки точности всей системы и не является экспертной научной проверкой. '
        'Два режима одной статьи учитываются как одно принимающее семейство. Исходные GOLD, '
        'одобренная PMC10000452 и прежние карты не изменены.', '',
        '## Следующая проверка', '',
        'Нужен типизированный временной контракт: начало, окно оценки, первоначальный курс, повторное '
        'лечение и рецидив. Сначала следует применить его к прежнему корпусу и отдельно учитывать '
        'неизвестные сроки; длительности будущего эффекта нельзя копировать из обучающего опыта. '
        'Затем нужен заранее фиксируемый независимый контроль с совместимыми методами. Общая цель '
        'свободного прогноза по всей карте и проверенного преимущества остаётся недостигнутой.', '',
        '## Воспроизводимость', '',
        f'{count} проверок через Poetry прошли. Проверены утечка внешнего исследования, разные семьи, '
        'неизвестные условия, временная неопределённость, координаты Unicode, сохранность прогноза '
        'при ошибке оценщика и повторное выполнение. Модельных вызовов нет; CLI прогноза работает без сети. '
        'Получение исходного XML было отдельной сетевой операцией. Сервисы не менялись; перезапуск не нужен.', '',
        f"Запуск: `{result['run_id']}`. Оценка: `{args.evaluation}`."]
    review = Path(args.review).resolve(); review.mkdir(parents=True, exist_ok=True)
    source = json.loads((folder / 'external-source.json').read_bytes())
    data = {'run_id': result['run_id'], 'evaluation_id': args.evaluation, 'run_path': str(folder),
        'tests_path': str(tests_path), 'summary': rows, 'coverage': result['coverage'],
        'methods': methods, 'outcomes': outcomes, 'source': source, 'forecast': result, 'evaluation': evaluation,
        'secondary_source_exposure_audit': exposure,
        'model_calls': 0, 'expert_validated': False}
    detail = []
    for receiver in methods['receivers']:
        name = 'ATROSAB' if 'atrosab' in receiver['id'] else 'H398'
        quotes = next(q['quotes'] for q in methods['method_evidence'] if q['receiver_id'] == receiver['id'])
        observed = outcomes[receiver['id']]
        blocks = '<h3>Методы — исходные английские фрагменты</h3>' + ''.join('<blockquote>' + escape(q['text']) + '</blockquote>' for q in quotes)
        blocks += '<h3>Исходы — открыты оценщиком</h3>' + ''.join('<blockquote>' + escape(q['text']) + '</blockquote>' for q in observed['evidence'])
        blocks += ''.join('<p>' + escape(s) + '</p>' for s in observed['limitations_ru'])
        detail.append('<details><summary>' + name + ': происхождение и ограничения</summary>' + blocks + '</details>')
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Внешний перенос и время</title><style>body{font:17px/1.6 system-ui;background:#101827;color:#e6edf7;max-width:1100px;margin:auto;padding:28px}h1,h2{color:#9bd7ff}table{border-collapse:collapse;width:100%}th,td{border:1px solid #40516a;padding:10px}details{background:#1b2a40;padding:16px;margin:18px 0;border:1px solid #536989;border-radius:10px}summary{cursor:pointer;font-weight:700}blockquote{border-left:4px solid #78baff;padding-left:16px;white-space:pre-wrap}code{overflow-wrap:anywhere}.table{overflow:auto}</style><main>' + render_lines(lines) + '<h2>Исходные фрагменты</h2>' + ''.join(detail) + '</main></html>'
    files = {'report.ru.md': ('\n'.join(lines) + '\n').encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    for name, value in files.items(): write_immutable(review / name, value)
    receipt = {'run_id': result['run_id'], 'evaluation_id': args.evaluation,
        'files': {name: sha256(value).hexdigest() for name, value in files.items()},
        'tests_sha256': sha256(test_bytes).hexdigest(), 'tests_passed': count,
        'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'render_helper_sha256': sha256(Path(__file__).with_name('render_template_barrier_audit.py').read_bytes()).hexdigest()}
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'review': str(review), 'tests': count, 'model_calls': 0}))


if __name__ == '__main__': main()
