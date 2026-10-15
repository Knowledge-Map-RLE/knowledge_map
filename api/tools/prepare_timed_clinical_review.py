"""Ручная разметка Codex связывает прочитанные графические сравнения с проверенными часами."""
import argparse
from hashlib import sha256,md5
from html import escape
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.first_administration_clock import relative_point
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network


def main():
    p=argparse.ArgumentParser()
    for name in ('clock-run','tros-figure','atros-figure','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();disable_network();root=Path(a.clock_run).resolve()
    clock=FilePredictionStore(root.parent).read_seal(root.name)
    require(clock is not None and clock['version']=='source-bound-first-administration-clock-2','Corrected source clock run required')
    for f,d in clock['binding']['implementation'].items():require(sha256((root/'implementation'/f).read_bytes()).hexdigest()==d,'Clock code differs')
    paths={'tros':Path(a.tros_figure).resolve(),'atros':Path(a.atros_figure).resolve()}
    binaries={k:v.read_bytes()for k,v in paths.items()}
    expected={'tros':'660161c1507b849e00538e894ef8137ae4072d0774d08a1a7bf6a9956efb8c1e',
        'atros':'fc2cdd3ba1d91c0aac2e780b0f30b4793b9aca2465cca64c239cf7797c6ebd82'}
    require(all(sha256(binaries[k]).hexdigest()==v for k,v in expected.items()),'Viewed graphical source differs')
    acquisition=json.loads((paths['tros'].parent/'acquisition.json').read_bytes())
    require(acquisition['pmcid']=='PMC5651799' and acquisition['figure_id']=='Fig4'
        and acquisition['image_sha256']==expected['tros'] and md5(binaries['tros']).hexdigest()==acquisition['image_md5'],
        'TROS graphical source is not bound to its XML')
    configs=[('tros','therapeutic_clinical','25','Fig4','a_right','TROS','PBS',[{'value':'500','unit':'microgram'}],
        'https://cdn.ncbi.nlm.nih.gov/pmc/blobs/2406/5651799/84ee95fdb653/41598_2017_13984_Fig4_HTML.jpg'),
        ('atros','manifest_clinical','18','f7','A','Atrosimab','FcDeltaab',
            [{'value':'30','unit':'mg/kg'},{'value':'60','unit':'mg/kg'}],
        'https://cdn.ncbi.nlm.nih.gov/pmc/blobs/ddea/8294390/8420d5cfc6a2/fimmu-12-705485-g007.jpg')]
    witnesses=[]
    for key,procedure,raw_day,figure,panel,agent,comparator,doses,url in configs:
        choices=[r for r in clock['clock_proofs']if r['procedure']==procedure];require(len(choices)==1,'Exact clinical context required')
        row=choices[0];require(row['purpose']=='clinical_followup' and row['phase']=='manifest_disease','Clinical manifest case required')
        ref=row['reference'];translated=relative_point({'context':ref['source_clock_context'],'day':raw_day},ref)
        require(translated['value']=='17','Source point does not establish the shared coordinate')
        witness={'source_key':key,'case_id':row['case_id'],'procedure':procedure,'primary_family':row['primary_family'],
            'figure_id':figure,'panel':panel,'image_sha256':expected[key],'source_url':url,'source_day':raw_day,
            'relative_time':translated,'source_clock_reference':ref,'intervention_label':agent,'comparator_label':comparator,
            'dose_groups':doses,'reported_relation':'lower_plotted_group_mean_clinical_score',
            'source_features':row['complete_source_case']['complete_case']['features'],
            'full_context':row['complete_source_case'],'read_by':'Codex','expert_validated':False,
            'exact_y_values_extracted':False,'pointwise_significance_inferred':False,
            'clinical_causality_inferred':False,'continuous_effect_inferred':False,
            'source_observation_end_filled_from_plot':False,
            'reading_ru':'Сравнение среднего на клиническом графике в выбранный отмеченный день; не график массы тела и не сравнение с нокаутом.'}
        witness['id']=fingerprint(witness);witnesses.append(witness)
    require(witnesses[0]['source_features']==witnesses[1]['source_features'],'Coarse source phenotype features differ')
    require(len({w['primary_family']for w in witnesses})==2,'Two distinct source dataset families required')
    data={'version':'codex-timed-clinical-source-review-1','clock_run_id':clock['run_id'],'clock_sha256':fingerprint(clock),
        'author':'Codex','expert_validated':False,'model_calls':0,'target_read':False,'witnesses':witnesses,
        'pattern':{'relation':'lower_plotted_group_mean_clinical_score','time_reference_type':'first_administration_of_this_episode',
            'coordinate':'17','unit':'source_day_coordinate','primary_families':sorted({w['primary_family']for w in witnesses}),
            'source_features':witnesses[0]['source_features'],'is_pattern_similarity':True,'full_fact_equivalence':False,
            'is_valid_universal_rule':False,'is_future_forecast':False,'is_automatically_extracted_visual_result':False},
        'new_empirical_forecasts':0,'graph_advantage_demonstrated':False,
        'preparer_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    lines=['# Сопоставимый временной паттерн в двух прошлых опытах','',
        '**Два источниковых сравнения в общей координате 17. Новых будущих прогнозов — 0.**','',
        '| Источник | Клиническая панель | Исходный день | Первое введение | Координата от первого | Прочитанное сравнение |',
        '| --- | --- | --- | --- | --- | --- |',
        '| TROS | Рисунок 4a, справа | 25 после иммунизации | 8 | 17 | Среднее TROS ниже PBS |',
        '| Atrosimab | Рисунок 7A | 18 проявленной EAE | 1 | 17 | Средние 30 и 60 мг/кг ниже контроля |','',
        'Это ручная визуальная разметка Codex по подлинным рисункам, требующая экспертной проверки. '
        'Точные значения среднего и значимость конкретной точки не снимались. '
        'Сравниваются клинические оценки, а не масса тела. Нокаут TNFR1 на рисунке TROS не подменяет PBS-контроль.','',
        '## Что общего','',
        'Оба опыта относятся к проявленной MOG-индуцированной EAE у гуманизированных мышей, '
        'селективному воздействию на человеческий TNFR1, внутрибрюшинному введению и порядковому клиническому оцениванию. '
        'Смена начала отсчёта выявляет общий календарный индекс 17 при разных исходных днях 25 и 18. '
        'Идентификаторы часов разные: совпадение индекса не означает один физический момент или одну популяцию.','',
        'Клинические и временные сравнения взяты из уже прочитанных обучающих источников. '
        'Момент выбран Codex для сопоставления по обучающим рисункам; он не объявляется лучшим '
        'моментом ответа или независимо проверенным биологическим законом. '
        'Две дозы Atrosimab — одно семейство, а не две независимые репликации.','',
        '## Какие различия сохранены','',
        'TROS — 500 мкг, курс 0, 4, 8; Atrosimab — 30 или 60 мг/кг, курс 0, 3, 7, 11. '
        'Сохраняются разные пол, генетические конструкции, возрастные и индукционные условия, контролы и шкалы. '
        'У TROS методы и подписи расходятся по верхней категории шкалы; единый паттерн не исправляет это '
        'и не разрешает нелинейную перекодировку групповых средних. Функциональное взаимодействие '
        'с рецептором не превращается в доказанную блокаду в новом организме.','',
        'Неизвестный численный конец клинического наблюдения Atrosimab остаётся неизвестным. '
        'Для утверждения о выбранной измеренной точке полный конец наблюдения не требуется. '
        'Из наличия этой точки не следует улучшение во всех остальных моментах или сохранение эффекта 17 дней. '
        'Дни являются координатами опубликованных графиков, а не более точным временем внутри суток.','',
        '## Следствие для предсказателя','',
        'Для качественной гипотезы о конкретном оцениваемом моменте достаточно корректно связанного '
        'источникового сравнения в этот момент; требование известного полного конца каждого старого опыта '
        'было бы лишним. При этом время будущей оценки должно быть задано отдельной измерительной '
        'процедурой или явным предложенным планом, а не взято из будущего результата. '
        'Новые контексты не становятся эквивалентными прошлым.','',
        'Пока зафиксирован общий временной шаблон прошлых наблюдений. Он не является исполняемым '
        'универсальным правилом и не предсказывает новый клинический результат автоматически. '
        'Далее нужно сформировать и запечатать проверяемые условные кандидаты на одинаковых знаниях '
        'для режима карты и сильного семантического контроля. '
        'Источник-пара не доказывает преимущество DAG или научную корректность будущей гипотезы.','',
        'GOLD, производственные карты и прежние результаты сохранены. Модельных вызовов нет. '
        'Рисунок TROS получен отдельным сетевым чтением прошлого источника с проверкой MD5 из XML; '
        'сама подготовка этого отчёта выполнялась без сети. Будущие контрольные исходы не читались.']
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Общий временной паттерн двух прошлых опытов</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1100px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}th,td{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}img{max-width:100%;height:auto;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}details{background:white;border:1px solid #cad5df;padding:16px;margin:16px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}</style><main>'
    html+=render_lines(lines)
    for key,label in [('tros','TROS: рисунок 4'),('atros','Atrosimab: рисунок 7')]:html+='<h2>'+label+'</h2><img src="'+key+'.jpg" alt="'+label+' — исходные клинические графики">'
    html+='<details><summary>Точные источники и полный контекст</summary><pre>'+escape(json.dumps(data,ensure_ascii=False,indent=2))+'</pre></details></main></html>'
    files={'audit.json':FilePredictionStore.encode(data),'report.ru.md':('\n'.join(lines)+'\n').encode(),
        'report.html':html.encode(),'tros.jpg':binaries['tros'],'atros.jpg':binaries['atros']}
    receipt={'clock_path':str(root),'clock_sha256':fingerprint(clock),'files':{f:sha256(b).hexdigest()for f,b in files.items()},
        'preparer_sha256':data['preparer_sha256'],'helper_sha256':sha256((Path(__file__).parent/'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    output=Path(a.output).resolve()
    for f,b in files.items():write_immutable(output/f,b)
    write_immutable(output/'verification.json',FilePredictionStore.encode(receipt))
    print(json.dumps({'witness_blocks':2,'dose_specific_comparisons':3,'primary_families':2,'relative_coordinate':'17','new_empirical_forecasts':0}))


if __name__=='__main__':main()
