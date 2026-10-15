"""Русский отчёт логических следствий на полном корпусе, отдельно от прогнозов."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines


def main():
    p = argparse.ArgumentParser()
    for name in ('run','control','tests','review'): p.add_argument('--'+name,required=True)
    args=p.parse_args(); root=Path(args.run).resolve(); control_root=Path(args.control).resolve()
    r=FilePredictionStore(root.parent).read_seal(root.name)
    c=FilePredictionStore(control_root.parent).read_seal(control_root.name)
    for field in ('sources','families','metadata','map_hashes','implementation','context_audit_sha256','model_audit_sha256','origin_audit_sha256'):
        require(r['binding'][field]==c['binding'][field], 'Logical paired input differs')
    require(r['canonical_blocks']==c['canonical_blocks']==943 and r['predictions']==c['predictions'], 'Corpus or empirical forecast differs')
    logic=r['licensed_categorical_inference']; conclusions=logic['consequences']['without_dependencies']
    require(len(conclusions)==2 and logic['licensed_parent_blocks']==2 and logic['licensed_views']==3
            and c['licensed_categorical_inference']['status']=='not_supplied', 'Definition proof count differs')
    tests=Path(args.tests).read_bytes(); suites=ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures',0))==int(s.attrib.get('errors',0))==0 for s in suites), 'Tests failed')
    count=sum(int(s.attrib['tests']) for s in suites)
    lines=['# Логические выводы на всех 11 картах','',
        '**Два прежних логических следствия воспроизведены на полном корпусе из 943 знаний. '
        'Новых эмпирических прогнозов — 0; преимущество исходных зависимостей пока не установлено.**','',
        'Весь нынешний корпус обработан без выбора вопроса или отдельных статей для генератора. '
        'Проверяются канонические знания и контексты всех 11 карт. Явные формальные лицензии по-прежнему '
        'имеются только у двух определений обзора PMC6416157; расширение числа статей не превращает '
        'остальные утверждения в универсальные посылки. Лицензии сохраняют полные составные родители '
        'и точные исходные фрагменты. Их интерпретация подготовлена Codex и требует экспертной проверки.','',
        '## Полученные выводы','',
        '1. В рамках вводного определения данного обзора амнестическое MCI исключает когнитивное '
        'снижение, нарушающее повседневное функционирование.',
        '2. В рамках того же определения неамнестическое MCI исключает когнитивное снижение, '
        'нарушающее повседневное функционирование.','',
        'Это следствия определения, а не утверждения об отсутствии любой физической инвалидности, '
        'будущем развитии деменции или всех пациентах, диагностированных по другим схемам. '
        'Оба вывода уже получались на прежнем меньшем корпусе; они не объявляются новыми открытиями '
        'этого прогона.','',
        '## Механизм вывода','',
        'Использована форма EAE первой фигуры: ни один M не относится к P; все S относятся к M; '
        'следовательно, ни один S не относится к P. M — случаи MCI в рамках определения, S — '
        'соответствующий подтип, P — когнитивное снижение, нарушающее повседневное функционирование. '
        'Полная проверка моделей не нашла контрмодели; удаление любой посылки уничтожает следование. '
        'Для каждого вывода сохраняется отдельный DAG доказательства.','',
        'Проверяющий модуль охватывает 256 сочетаний форм в четырёх фигурах. Из традиционных 24 '
        'силлогистических форм 15 допустимы без дополнительного существования, ещё 9 требуют '
        'установленной непустоты соответствующих классов. Существование не предполагается. '
        'Этот корпус не использовал все 24 формы: два реальных вывода получены одной формой EAE.','',
        '## Роль структуры','',
        '| Способ поиска посылок | Логических следствий |','| --- | ---: |']
    names={'graph':'Совместные предпосылки исходной карты','without_dependencies':'Сочетания семантических посылок без зависимостей',
           'source_neighborhood':'Соседство в статье','permuted_dependencies':'Перемешанные зависимости'}
    lines += [f"| {names[mode]} | {len(values)} |" for mode,values in logic['consequences'].items()]
    lines += ['', 'K9 остаётся изолированным в исходной карте. Семантический поиск находит посылки '
        'без авторской стрелки между K1 и K9. Новый граф доказательства построен после проверки '
        'вывода и не выдаётся за преимущество прежнего DAG. Источниковые карты не дополнялись '
        'выгодными стрелками задним числом.','',
        '## Прогнозы и вычислительные представления','',
        'Генеративные режимы с зависимостями, без зависимостей и с перемешиванием по-прежнему '
        'не сформировали новых эмпирических гипотез. По 20 результатов известных знаний и '
        'частотной базы — выбранные существующие блоки, а не 20 совпадений. Сохранился 151 '
        'арифметический результат интерпретации уже сообщённых модельных чисел; они не считаются '
        '151 независимым прогнозом.','',
        'Исправлен вывод административного CLI: раньше его краткая сводка показывала только '
        'непосредственно категорические исходные блоки и пропускала отдельный лицензированный '
        'канал. Теперь отсутствие лицензии обозначается отдельно, а два проверенных вывода '
        'отображаются явно. Научный алгоритм этой правкой не изменён.','',
        '## Следующая содержательная работа','',
        'Нужно расширять источниковую типизацию реально выраженных правил и определений, '
        'различая универсальные положения, вероятностные отношения, действия и намерения. '
        'Поиск подходящих посылок и проверка их совместного применения должны быть отдельными '
        'операциями. Для свободных прогнозов продолжается проверка независимого переноса; для '
        'выводов — проверка следования, существенности посылок и границ контекста. Преимущество '
        'каждого канала сравнивается на одинаковых знаниях и бюджете.','',
        '## Воспроизводимость','',
        f'{count} проверок через Poetry прошли: силлогистические формы, условия существования, '
        'контрмодели, отрицания, лицензии полных родителей и генератор всей карты. Две стороны '
        'парного опыта используют одни источники, версии карт, код и контексты; отличаются '
        'только наличием отдельной лицензии определений.','',
        'Сеть и модельные вызовы в CLI запрещены. Источники уже прочитаны: это воспроизведение '
        'логических следствий, а не слепой эмпирический опыт. GOLD, production-карты и сервисы '
        'не менялись; перезапуск не требуется. Экспертная и визуальная проверки не заявляются.','',
        f"Основной запуск: `{r['run_id']}`. Контроль: `{c['run_id']}`.",'']
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Логические выводы всей карты</title><style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1100px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>'+render_lines(lines)+'</main></html>'
    data={'run_id':r['run_id'],'control_run_id':c['run_id'],'sources':11,'canonical_blocks':943,
          'logical_counts':{mode:len(values) for mode,values in logic['consequences'].items()},
          'licensed_parent_blocks':2,'licensed_views':3,'tests':count,'numeric_presentations':151,
          'new_empirical_predictions':0,'graph_advantage_demonstrated':False,'model_calls':0}
    files={'report.ru.md':'\n'.join(lines).encode(),'report.html':html.encode(),'data.json':FilePredictionStore.encode(data)}
    folder=Path(args.review).resolve();folder.mkdir(parents=True,exist_ok=True)
    for name,content in files.items():write_immutable(folder/name,content)
    builders={str(path):sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),Path(__file__).with_name('render_template_barrier_audit.py'))}
    write_immutable(folder/'verification.json',FilePredictionStore.encode({'files':{name:sha256(b).hexdigest() for name,b in files.items()},
        'builders':builders,'tests_sha256':sha256(tests).hexdigest(),'main_snapshot':str(root),'control_snapshot':str(control_root)}))
    print(json.dumps(data))


if __name__=='__main__':main()
