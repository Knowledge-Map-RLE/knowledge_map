"""Русский автономный отчёт времени, прежнего доступа и отдельного вывода источника."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser()
    for field in ('run', 'tests', 'review'): parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network(); folder = Path(args.run).resolve()
    result = FilePredictionStore(folder.parent).read_seal(folder.name)
    require(result['version'] == 'frozen-forecast-claim-qualification-3', 'Wrong qualification version')
    audit = json.loads((folder / 'audit.json').read_bytes())
    require(fingerprint(audit) == result['binding']['audit_sha256'], 'Qualification audit differs')
    descriptor = json.loads((folder / 'input-corpus.json').read_bytes()); forecast_path = Path(descriptor['forecast'])
    frozen = FilePredictionStore(forecast_path.parent).read_seal(forecast_path.name)
    require(fingerprint(frozen) == result['binding']['forecast_sha256'], 'Frozen forecast differs')
    test_path = Path(args.tests).resolve(); raw_tests = test_path.read_bytes(); suites = ET.fromstring(raw_tests).findall('testsuite')
    require(suites and all(int(s.attrib.get(k, 0)) == 0 for s in suites for k in ('failures', 'errors', 'skipped')), 'Qualification tests failed')
    tests = sum(int(s.attrib['tests']) for s in suites)
    require(result['canonical_blocks'] == 943 and result['semantic_statements'] == 1897
            and len(result['candidates']) == 2 and len(result['source_consequences']) == 1, 'Unexpected audit scope')
    lines = ['# Время, новизна и отдельное временное следствие', '',
        '**Старые гипотезы не исправлены по ответу. Одно источниковое временное следствие; '
        'новых подтверждённых научных прогнозов — ноль.**', '', '## Полный объём проверки', '',
        'Рассмотрены все 11 явно сохранённых карт: 943 канонических знания и 1897 семантических '
        'утверждений. У каждого знания сохранён отпечаток нормализованной семантики, исходный '
        'текстовый временной контекст и признак неизвестного контекста. Это полный аудит имеющихся '
        'карт, а не доказательство исчерпывающей формализации смысла всех статей.', '',
        'Проверены две уникальные гипотезы прежнего внешнего прогона. Одинаковые кандидаты '
        'в режимах с зависимостями и без них учитываются один раз. Все старые прогнозы, карты '
        'и GOLD сохраняются; новый аудит имеет отдельную неизменяемую версию.', '',
        '## Новизна и цитирование', '',
        '| Кандидат | Решение о новизне | Временной контракт старого прогноза |', '| --- | --- | --- |',
        '| ATROSAB, первоначальный курс | Общее направление уже описано в тексте обучения | Отсутствует |',
        '| H398, первоначальный курс | Новизна не установлена | Отсутствует |', '',
        'В полном тексте обучающей статьи Atrosimab найдено предложение о терапевтической '
        'активности ATROSAB при EAE. Его координаты Unicode и хеш проверены. Это известный '
        'общий паттерн; точное тождество всех доз, групп, временных фаз и исходов не утверждается.', '',
        'Там же обнаружена библиографическая ссылка на DOI 10.1038/s41598-018-31957-7. '
        'Наличие ссылки означает прежний доступ к источнику, а не эквивалентность всех его фактов. '
        'Отсутствие лицензированного совпадения для H398 не означает доказанную новизну. '
        'Ссылка ищется по всему полному тексту, включая отдельно сохранённую библиографию; '
        'References не становятся графовыми знаниями.', '',
        '## Что означает временной контракт', '',
        'Явно различаются: некоторый измеренный момент; все измеренные моменты окна; '
        'конкретная точка; непрерывный интервал. Сохраняются событие начала отсчёта, единица, '
        'популяция, вмешательство, контроль, показатель, уровень агрегации и эпизод лечения.', '',
        'Дни после иммунизации не отождествляются с днями после начала EAE. Повторное введение '
        'не относится к первоначальному курсу. День гистопатологии не становится концом '
        'клинического наблюдения. Примерный срок не считается точной точкой; месяцы и годы '
        'не переводятся автоматически в постоянное число дней.', '',
        'Ежедневные измерения не доказывают непрерывность. Один противоположный результат '
        'может опровергнуть утверждение о всех измеренных моментах, но не утверждение о '
        'существовании эффекта в другом месте окна. Необнаруженное различие не считается '
        'установленным нулевым эффектом. Рецидив или ухудшение относительно прежнего состояния '
        'не превращаются в противоположный эффект относительно контрольной группы.', '',
        'У обоих старых кандидатов контракт отсутствует. Даже известный оценщику третий '
        'день ATROSAB не добавлен задним числом в прогноз. Поэтому их временное подтверждение '
        'по-прежнему отсутствует.', '',
        '## Отдельный вывод из источника', '',
        '**В описанном первоначальном опыте ATROSAB между первым введением на день 1 '
        'и завершением клинического наблюдения на день 28 существует измеренная точка '
        'с меньшей тяжестью заболевания относительно контроля.**', '',
        'Посылки: расписание первоначального курса 1, 4, 8, 12; конец клинического наблюдения '
        '28; прямо описанное снижение тяжести с третьего дня. Правило: точка 3 входит '
        'в закрытое окно [1; 28], следовательно, в этом окне существует такая точка. '
        'Сохраняются одинаковые участники, контроль и показатель. Это включение во временное '
        'окно и введение квантора существования — логическая операция, не эмпирическое '
        'обобщение и не один из категорических силлогизмов.', '',
        'Вывод не говорит, что эффект сохранялся во всех точках до дня 28 или у каждого '
        'животного. Он вычисляется после чтения исхода и хранится отдельно от прогноза. '
        'Это следствие известного источника, а не новое научное открытие. Для H398 не '
        'подставлен день 85: явное клиническое окно для этой операции не установлено.', '',
        '## Роль карты и ограничения', '',
        'Операция использует скрытые роли, числовые границы и кванторы. Удаление видимых '
        'зависимостей при сохранении той же семантики не изменяет квалификацию. В прежнем '
        'эмпирическом прогоне оба основных режима дали те же две гипотезы. Поэтому преимущество '
        'исходного DAG не установлено. Граф обоснования можно хранить для аудита, но его наличие '
        'само по себе не доказывает лучшего прогнозирования.', '',
        'Это ретроспективный диагностический опыт: результаты уже прочитаны Codex, источник '
        '2018 года цитируется в более позднем обучении. Научная экспертная проверка отсутствует. '
        'Точный временной вывод и устранение ложного заявления о новизне не подменяют общую '
        'цель свободного прогнозирования по всей карте.', '',
        '## Проверки и продолжение', '',
        f'{tests} тестов Poetry прошли: кванторы времени, открытые границы, единицы, смена '
        'часов и контекста, точные и примерные сроки, источниковые цитаты, полный реестр, '
        'атомарная публикация, неизменность кандидатов и контроль без зависимостей. Первый '
        'прогон сохранил 53 успешных теста и две ошибки создания временного каталога; каталог '
        'подготовлен, следующие квитанции сохранены отдельно.', '',
        'Следующий этап: создавать новый кандидат сразу как полный семантический факт с '
        'собственным временным квантором, сохраняя полный контекст и статус гипотезы. '
        'Контракты методов и правила фиксируются до исходов; неизвестный срок не угадывается. '
        'Новизну нужно проверять отдельно по картам и цитирующим текстам. Затем необходим '
        'независимый контроль и сравнение режимов на одинаковых данных и бюджете.', '',
        'Модельных, сетевых и переводческих вызовов в этом этапе нет. Рабочие сервисы, '
        'production-карты и GOLD не менялись; перезапуск не требуется.', '',
        f"Запуск аудита: `{result['run_id']}`. Старый прогноз: `{frozen['run_id']}`."]
    sections = []
    for row in result['candidates']:
        name = 'ATROSAB' if 'atrosab' in row['receiver_id'] else 'H398'
        content = '<p>' + escape(row['reason_ru']) + '</p>'
        content += ''.join('<blockquote>' + escape(e['text']) + '</blockquote>' for e in row['known_pattern_evidence'])
        annotation = next(r for r in audit['candidates'] if r['prediction_id'] == row['prediction_id'])
        content += ''.join('<blockquote>' + escape(e['text']) + '</blockquote>' for o in annotation['outcome_temporal_observations'] for e in o['evidence'])
        sections.append('<details><summary>' + name + ': исходные английские фрагменты</summary>' + content + '</details>')
    review = Path(args.review).resolve(); review.mkdir(parents=True, exist_ok=True)
    data = {'run_id': result['run_id'], 'run_path': str(folder), 'forecast_path': str(forecast_path),
        'tests_path': str(test_path), 'result': result, 'audit': audit, 'model_calls': 0, 'expert_validated': False}
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Время и новизна</title><style>body{font:17px/1.6 system-ui;max-width:1100px;margin:auto;padding:28px;background:#101827;color:#e6edf7}h1,h2{color:#9bd7ff}table{border-collapse:collapse;width:100%}th,td{border:1px solid #40516a;padding:10px}details{background:#1b2a40;margin:18px 0;padding:16px;border:1px solid #536989;border-radius:10px}summary{cursor:pointer;font-weight:bold}blockquote{border-left:4px solid #78baff;padding-left:16px}code{overflow-wrap:anywhere}.table{overflow:auto}</style><main>' + render_lines(lines) + '<h2>Происхождение</h2>' + ''.join(sections) + '</main></html>'
    files = {'report.ru.md': ('\n'.join(lines) + '\n').encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    for name, value in files.items(): write_immutable(review / name, value)
    receipt = {'run_id': result['run_id'], 'tests_sha256': sha256(raw_tests).hexdigest(), 'tests_passed': tests,
        'files': {name: sha256(value).hexdigest() for name, value in files.items()},
        'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'render_helper_sha256': sha256(Path(__file__).with_name('render_template_barrier_audit.py').read_bytes()).hexdigest()}
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'review': str(review), 'tests': tests, 'source_consequences': len(result['source_consequences'])}))


if __name__ == '__main__': main()
