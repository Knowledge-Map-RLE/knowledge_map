"""Неизменяемый двуязычный отчёт о двух разных прогнозируемых исходах."""
import json
from pathlib import Path
from domain.article_maps import fingerprint
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore


def write_review(folder,branches):
    encoded=json.dumps(branches,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    write_immutable(folder/'report.html',HTML.replace('__DATA__',encoded).encode('utf-8'))
    write_immutable(folder/'review.json',FilePredictionStore.encode(branches))
    markdown='# IL-6: знак оценки и статистическая значимость\n\n'
    for scope,d in branches.items():
        s=d['summary'];markdown+=f'## {scope}\n\nЗапуск `{d["run_id"]}`.\n\n'
        markdown+=f'Те же {s["papers"]} статей и {s["families"]} семейств; опубликованных результатов {s["known_findings"]}.\n\n'
        markdown+='| Режим исследовательского прогноза знака | Текущие гипотезы | Исторические прогнозы | Сравнения со знаками | Совпало | Отличается |\n|---|---:|---:|---:|---:|---:|\n'
        for mode,r in s['direction'].items():markdown+=f'| {mode} | {r["current_hypotheses"]} | {r["historical_issued"]} | {r["comparisons"]} | {r["agreements"]} | {r["different_signs"]} |\n'
        markdown+=f'\nСтрогих статистических прогнозов: {s["statistical_semantic_forecasts"]}. Допуск к будущей цели: {d["readiness"]["target_reading_allowed"]}.\n\n'
    markdown+='Совпадение знака оценки не подтверждает истинный биологический эффект. Доверительные интервалы и отсутствие статистической обнаружимости сохранены отдельно. Несколько оценок одной статьи не являются независимыми испытаниями. Аналогии между шкалами, возрастами, экспозициями, поправками и MCI — явно заявленные, пока не подтверждённые допущения. Частотная база не считается новым выводом. Эпизоды обучения берутся только из прежнего реестра; цитирование не создаёт dependency-связь.\n\n'
    markdown+='Корпус ретроспективно уже прочитан. Будущая цель не открыта; внешние/локальные модели, переводчики и эмбеддинги не вызывались. GOLD и прежние результаты сохранены. Научная разметка Codex требует экспертной проверки.\n'
    write_immutable(folder/'report.ru.md',markdown.encode('utf-8'))


def save_dual_review(folder,forecast,audit):
    channels=forecast['outcome_channels'];direction=channels['reported_direction_exploratory'];folds=forecast['retrospective_folds']
    summary={'papers':len(forecast['binding']['sources']),'families':len(folds),'known_findings':len(forecast['modes']['known_union']),
             'statistical_semantic_forecasts':len(channels['statistical_detection_strict']['modes']['semantic']),'direction':{}}
    for mode,current in direction['modes'].items():
        evaluations=[f['evaluation']['outcome_channels']['reported_direction_exploratory']['modes'][mode] for f in folds]
        summary['direction'][mode]={'current_hypotheses':len(current),'historical_issued':sum(e['issued_answers'] for e in evaluations if e['target_families']),
            'sealed_without_target_answer':sum(e['issued_answers'] for e in evaluations if not e['target_families']),
            'families_with_issued_hypotheses':sum(e['issued_answers']>0 and bool(e['target_families']) for e in evaluations),
            'comparisons':sum(e['scorable_comparisons'] for e in evaluations),'agreements':sum(e['agreements'] for e in evaluations),
            'different_signs':sum(e['different_signs'] for e in evaluations),'supported_target_comparisons':sum(e['supported_target_comparisons'] for e in evaluations)}
    profile_index={tuple(p['reference']):p['normalized'] for p in forecast['structured_context']['profiles']}
    payload={'version':'dual-outcome-review-2','run_id':forecast['run_id'],'forecast_sha256':fingerprint(forecast),
             'scope':forecast['binding']['analysis_scope'],'summary':summary,'direction':direction,
             'profiles':[{'reference':list(k),'normalized':v} for k,v in sorted(profile_index.items())],
             'folds':folds,'readiness':forecast['readiness'],'binding':forecast['binding'],
             'controls':{'passed':audit['controls_passed'],'total':audit['control_count']},
             'model_calls':0,'future_target_read':False,'expert_validated':False}
    write_review(folder,{payload['scope']:payload})
    return payload


def combine_reviews(root):
    branches={}
    for scope in ('primary','sensitivity'):
        receipt=json.loads((root/scope/'receipt-v2.json').read_text('utf-8'))
        d=json.loads((Path(receipt['report_folder'])/'review.json').read_text('utf-8'));branches[scope]=d[scope]
    write_review(root/'review-v2',branches)


HTML=r'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IL-6: два исхода прогноза</title>
<style>body{font:16px/1.5 system-ui;margin:0;background:#f3f5f9;color:#19253c}main{max-width:1250px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:15px}h1{font-size:27px;margin:0}h2{font-size:21px}section{padding:20px;border:1px solid #dbe1ed;border-radius:12px;margin:20px 0;background:white}button,select{font:inherit;border:1px solid #8192b1;border-radius:8px;padding:9px 14px;background:white;cursor:pointer}button{background:#245ac2;color:white}.warning{padding:15px;border-left:5px solid #db991e;background:#fff8e4}.muted{color:#596a81}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #dae1ed;vertical-align:top}th{background:#eef2f9}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace}details{margin:12px 0;padding:12px;border:1px solid #dce2eb;border-radius:8px}summary{cursor:pointer;font-weight:600}blockquote{white-space:pre-wrap;border-left:3px solid #9aaccc;margin:12px 0;padding:10px}.row{display:flex;flex-wrap:wrap;gap:12px}.metric{padding:15px;background:#eef3ff;border-radius:8px}.metric b{display:block;font-size:26px}</style>
<main><header><h1 id="title"></h1><button id="language">English</button></header><p id="meta" class="muted"></p><select id="branch"></select><p id="warning" class="warning"></p>
<section><h2 id="summaryTitle"></h2><div id="metrics" class="row"></div><p id="meaning"></p><div id="scores" class="scroll"></div></section>
<section><h2 id="claimsTitle"></h2><div id="claims"></div></section><section><h2 id="predictionsTitle"></h2><div id="predictions"></div></section>
<section><h2 id="holdoutTitle"></h2><select id="fold"></select><div id="holdout"></div></section><section><h2 id="policyTitle"></h2><p id="policyNote"></p><pre id="policy"></pre><details><summary id="gateTitle"></summary><pre id="gate"></pre></details></section>
<section><h2 id="nextTitle"></h2><p id="next"></p><p id="checks" class="muted"></p></section></main>
<script id="data" type="application/json">__DATA__</script><script>
'use strict';const ALL=JSON.parse(document.getElementById('data').textContent);let D=ALL[Object.keys(ALL)[0]],L=0;
const t=(ru,en)=>L?en:ru,el=id=>document.getElementById(id),set=(id,s)=>el(id).textContent=s,j=v=>JSON.stringify(v,null,2);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ref=r=>r[0].split('-')[1].toUpperCase()+' / '+r[1];
const label=x=>({positive_association:t('Больше снижения при большем IL-6','More decline with higher IL-6'),inverse_association:t('Меньше снижения при большем IL-6','Less decline with higher IL-6'),zero_point_estimate:t('Нулевая точечная оценка','Zero point estimate'),not_statistically_detected:t('Статистически не обнаружено','Not statistically detected')})[x]||x;
const mode=x=>({semantic:t('Символьный перенос','Symbolic transfer'),dependency:t('Перенос с зависимостями','Dependency transfer'),family_frequency_baseline:t('Частотная база по семействам','Family frequency baseline')})[x]||x;
el('branch').innerHTML=Object.keys(ALL).map(k=>'<option value="'+k+'">'+(k==='primary'?'Основной анализ / Primary':'Чувствительность / Sensitivity')+'</option>').join('');
function render(){document.documentElement.lang=L?'en':'ru';set('language',L?'Русский':'English');set('title',t('IL-6: знак оценки и значимость','IL-6: estimate sign and significance'));
set('meta',D.summary.papers+' '+t('статей','papers')+' · '+D.summary.families+' '+t('семейств','families')+' · '+D.run_id);
set('warning',t('Это ретроспективный опыт на уже прочитанном корпусе. Совпадение знака оценки не подтверждает истинный эффект. Будущая цель не прочитана; научная разметка требует экспертной проверки.','Retrospective study on a previously read corpus. Estimate-sign agreement does not establish the true effect. Future target unread; scientific annotations require expert review.'));
set('summaryTitle',t('Результаты двух каналов','Two outcome channels'));el('metrics').innerHTML='<div class="metric"><b>'+D.summary.known_findings+'</b>'+t('Опубликованных результатов','Published findings')+'</div><div class="metric"><b>'+D.summary.statistical_semantic_forecasts+'</b>'+t('Строгих статистических прогнозов','Strict statistical forecasts')+'</div>';
set('meaning',t('Текущие гипотезы используют весь корпус; исторические прогнозы построены только по более ранним семействам. Несколько сравнений с одной удержанной статьёй не являются независимыми опытами.','Current hypotheses use the whole corpus; historical forecasts use earlier families only. Multiple comparisons against one held-out paper are not independent experiments.'));
el('scores').innerHTML='<table><thead><tr>'+[t('Режим знака','Sign mode'),t('Текущие','Current'),t('Исторические','Historical'),t('Сравнения','Comparisons'),t('Совпало','Agree'),t('Отличается','Differ'),t('Статистическая поддержка знака цели','Statistical support for target sign')].map(s=>'<th>'+s+'</th>').join('')+'</tr></thead><tbody>'+Object.entries(D.summary.direction).map(([k,r])=>'<tr><td>'+mode(k)+'</td>'+['current_hypotheses','historical_issued','comparisons','agreements','different_signs','supported_target_comparisons'].map(key=>'<td>'+r[key]+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
set('claimsTitle',t('Знак и обнаружимость исходных результатов','Source estimate signs and statistical detection'));
el('claims').innerHTML=D.direction.observations.map(r=>'<details><summary>'+esc(ref(r.reference))+' · '+esc(label(r.direction.label))+' · '+esc(r.original.modality)+'</summary><p>'+esc(r.original.text)+'</p><pre>'+esc(j({direction:r.direction,transport_scope:r.transport_scope,measurements:r.original.measurements}))+'</pre><details><summary>'+t('Семантические признаки контекста','Semantic context features')+'</summary><pre>'+esc(j(D.profiles.find(p=>j(p.reference)===j(r.reference)).normalized))+'</pre></details>'+r.original.evidence.spans.map(s=>'<p class="muted">Unicode ['+s.start+', '+s.end+') · SHA-256 '+esc(r.original.evidence.source_sha256)+'</p><blockquote>'+esc(s.text)+'</blockquote>').join('')+'</details>').join('');
set('predictionsTitle',t('Текущие гипотезы и источники поддержки','Current hypotheses and supporting sources'));
el('predictions').innerHTML=Object.entries(D.direction.modes).map(([k,rs])=>'<h3>'+mode(k)+'</h3>'+(rs.length?rs.map(r=>'<details><summary>'+esc(label(r.finding))+' · '+t('поддержка: ','support: ')+r.support+'</summary><pre>'+esc(j(r))+'</pre></details>').join(''):'<p>'+t('Прогноз пуст.','No forecast.')+'</p>')).join('');
set('holdoutTitle',t('Удержание целого семейства: прогноз до оценки','Whole-family holdout: seal before evaluation'));
const selected=el('fold').value;el('fold').innerHTML=D.folds.map((f,i)=>'<option value="'+i+'">'+esc(f.plan.family)+' · '+f.plan.first_publication+'</option>').join('');
if(selected&&Number(selected)<D.folds.length)el('fold').value=selected;else{const i=D.folds.findIndex(f=>f.evaluation.outcome_channels.reported_direction_exploratory.modes.semantic.issued_answers>0);el('fold').value=String(i<0?0:i)}showFold();
set('policyTitle',t('Явные допущения переноса','Explicit transport assumptions'));set('policyNote',D.direction.transport_policy[L?'scope_en':'scope_ru']);set('policy',j(D.direction.transport_policy));
set('gateTitle',t('Допуск к независимой будущей цели','Independent future-target readiness'));set('gate',j(D.readiness));
set('nextTitle',t('Что проверять дальше','What to test next'));set('next',t('Проверить, какие модификаторы объясняют расхождение знаков: MCI, определение исхода и поправки. Правила уточнять на тех же статьях. При нескольких оценках одного семейства сохранять неопределённость; не выбирать удобную оценку. Прогноз биологического направления требует отдельной проверки неопределённости и нового независимого материала после фиксации правил.','Test which modifiers explain sign differences: MCI, outcome definition and adjustments. Refine rules on the same papers. Retain uncertainty when a family reports multiple estimates; do not cherry-pick an estimate. Biological-direction prediction needs separate uncertainty validation and new independent data after the rules are fixed.'));
set('checks',t('Контроли: ','Controls: ')+D.controls.passed+'/'+D.controls.total+'. '+t('Модельных вызовов нет. Старые карты и результаты сохранены.','No model calls. Old maps and results retained.'));}
function showFold(){const f=D.folds[Number(el('fold').value)];el('holdout').innerHTML='<p>'+t('Обучающих семейств: ','Training families: ')+f.training_family_count+' · '+t('Запечатанный прогноз: ','Sealed forecast: ')+f.forecast_run_id+'</p>'+Object.entries(f.evaluation.outcome_channels.reported_direction_exploratory.modes).map(([k,r])=>'<h3>'+mode(k)+'</h3><p>'+t('Прогнозов / сравнений: ','Forecasts / comparisons: ')+r.issued_answers+' / '+r.scorable_comparisons+'</p>'+r.results.map(s=>'<details><summary>'+esc(ref(s.target))+' · '+esc(s.status)+'</summary><pre>'+esc(j(s))+'</pre></details>').join('')).join('')+'<details><summary>'+t('Удержанные исходные утверждения','Held-out source claims')+'</summary>'+f.evaluation.outcome_channels.reported_direction_exploratory.targets.map(r=>'<p>'+esc(r.original.text)+'</p><pre>'+esc(j(r.original.measurements))+'</pre>').join('')+'</details>';}
el('language').onclick=()=>{L=1-L;render()};el('branch').onchange=()=>{D=ALL[el('branch').value];el('fold').value='';render()};el('fold').onchange=showFold;render();
</script></html>'''
