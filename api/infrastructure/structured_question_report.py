"""Автономный двуязычный просмотр признаков, отказов переноса и фиксации прогноза."""
import json
from copy import deepcopy
from collections import Counter
from domain.article_maps import fingerprint
from domain.structured_question_context import FEATURES,structured_matrix,compare_features
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable

LABELS={
 'age':['Возраст','Age'],'dementia_entry':['Исключение деменции','Dementia entry'],
 'mci':['Исходный MCI','Baseline MCI'],'baseline_score':['Исходный когнитивный отбор','Baseline cognitive selection'],
 'exposure':['Экспозиция IL-6','IL-6 exposure'],'outcome':['Определение исхода','Outcome estimand'],
 'followup':['Наблюдение','Follow-up'],'adjustments':['Поправки','Adjustments'],'model':['Модель','Model'],
 'alpha':['Порог значимости','Significance threshold'],'sample_size':['Размер выборки','Sample size']}


def save_structured_review(folder,current,previous,audit):
    profiles=deepcopy(current['structured_context']['profiles']);pairs=structured_matrix(profiles)
    source_family={r['original']['evidence']['article_id']:r['original']['evidence']['family'] for r in current['observations']}
    for p in pairs:p['independent_families']=source_family[p['left'][0]]!=source_family[p['right'][0]]
    for p in profiles:p['unknown_features']=compare_features(p['normalized'],p['normalized'])['unknown']
    # Отчёт не должен менять уже зафиксированную структуру прогноза.
    payload={'version':'structured-question-review-2','run_id':current['run_id'],'scope':current['binding']['analysis_scope'],
             'previous_run_id':previous['run_id'],'source_count':len(current['binding']['sources']),
             'family_count':len(current['retrospective_folds']),'claim_count':current['claim_count'],
             'profiles':profiles,'pairs':pairs,'labels':LABELS,'modes':current['modes'],'observations':current['observations'],
             'prior_counts':{m:len(v) for m,v in previous['modes'].items()},'rules':current['rules'],
             'diagnostics':current['diagnostics'],'folds':current['retrospective_folds'],
             'readiness':current['readiness'],'controls':{'passed':audit['controls_passed'],'total':audit['control_count']},
             'normalization':{'same_profile_pairs':sum(p['transfer_authorized'] for p in pairs),
                              'same_profile_independent_pairs':sum(p['transfer_authorized'] and p['independent_families'] for p in pairs)},
             'model_calls':0,'future_target_read':False,'expert_validated':False,
             'scientific_status':'retrospective_engineering_diagnostic',
             'strict_transport_policy':'all explicit applicability features must agree; unknown blocks transfer; sample size and alpha retained',
             'forecast_sha256':fingerprint(current)}
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    html=HTML.replace('__DATA__',encoded)
    write_immutable(folder/'review.json',FilePredictionStore.encode(payload))
    write_immutable(folder/'report.html',html.encode('utf-8'))
    known=len(current['modes']['known_union']);sem=len(current['modes']['semantic']);dep=len(current['modes']['dependency'])
    fully=sum(not p['unknown_features'] for p in profiles)
    counts=Counter(k for p in profiles for k in p['unknown_features'])
    md=(f'# IL-6: структурированный контекст\n\nЗапуск `{current["run_id"]}`, ветка `{payload["scope"]}`. '
        f'Те же {payload["source_count"]} статей, {payload["family_count"]} независимых семейств.\n\n'
        f'Известные результаты: {known}; семантические прогнозы: {sem}; прогнозы с зависимостями: {dep}. '
        'Известные результаты — опубликованные наблюдения, а не успешные прогнозы.\n\n'
        f'Структурировано {len(profiles)} результатов по 11 признакам; полностью известны {fully}. '
        f'Пары с одинаковым полным профилем: {payload["normalization"]["same_profile_pairs"]}; '
        f'из разных семейств: {payload["normalization"]["same_profile_independent_pairs"]}.\n\n'
        f'Неизвестные признаки: {dict(counts)}. Различия или неизвестность не являются опровержением научной связи. '
        'Равенство контекста также не доказывает тождество знаний.\n\n'
        'Консервативная политика переноса требует совпадения всех признаков, включая N и α. '
        'Это явно зафиксированное ограничение алгоритма, а не требование идентичных условий для любой научной гипотезы. '
        'Следующий шаг — определить и независимо проверить правила допустимого переноса между близкими контекстами, '
        'разделив прогноз направления эффекта и прогноз статистической значимости. Увеличивать корпус до этой проверки не требуется.\n\n'
        f'Контроли: {audit["controls_passed"]}/{audit["control_count"]}. '
        f'Чтение будущей цели разрешено: {current["readiness"]["target_reading_allowed"]}. '
        'Внешних/локальных модельных вызовов нет. GOLD, исходные карты и прежние результаты сохранены. '
        'Разметка Codex требует экспертной проверки.\n')
    write_immutable(folder/'report.ru.md',md.encode('utf-8'))
    return payload


HTML=r'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IL-6 — структурированный контекст</title><style>
body{font:16px/1.5 system-ui;background:#f3f5f9;color:#172339;margin:0}main{max-width:1300px;margin:auto;padding:24px}
header{display:flex;justify-content:space-between;gap:20px}button,select{font:inherit;border:1px solid #8091b0;border-radius:8px;padding:8px 15px;background:white;cursor:pointer}button{background:#245ac2;color:white}
h1{margin:0;font-size:28px}h2{font-size:21px}section,details.card{background:white;padding:20px;margin:18px 0;border:1px solid #d8dfeb;border-radius:12px}
.metrics{display:flex;flex-wrap:wrap;gap:12px}.metric{background:#eef3ff;padding:16px;border-radius:9px;min-width:130px}.metric b{font-size:26px;display:block}
.muted{color:#52637b}.warning{border-left:5px solid #d89619;background:#fff8e5;padding:15px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #dde3ee;vertical-align:top}th{background:#eef2f8}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace}summary{cursor:pointer;font-weight:600}.unknown{color:#926108}code{overflow-wrap:anywhere}blockquote{border-left:3px solid #a2b2cb;padding:8px 15px;margin:10px 0;white-space:pre-wrap;font-size:14px}.row{display:flex;gap:10px;flex-wrap:wrap}
</style><main><header><h1 id="title"></h1><button id="language">English</button></header><p id="meta" class="muted"></p>
<p id="notice" class="warning"></p><section><h2 id="resultsTitle"></h2><div id="metrics" class="metrics"></div><p id="meaning"></p></section>
<section><h2 id="traitsTitle"></h2><p id="traitsNote"></p><div id="profiles"></div></section>
<section><h2 id="pairsTitle"></h2><p id="pairsNote"></p><label class="row"><span id="filterLabel"></span><select id="pairFilter"><option value="independent"></option><option value="all"></option></select></label><div id="pairs"></div></section>
<section><h2 id="foldsTitle"></h2><div id="folds"></div></section><section><h2 id="nextTitle"></h2><p id="next"></p><details><summary id="gateTitle"></summary><pre id="gate"></pre></details></section>
<section><h2 id="provenanceTitle"></h2><p id="provenance"></p><details><summary id="technicalTitle"></summary><pre id="technical"></pre></details></section>
</main><script id="data" type="application/json">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('data').textContent);let L=0;
const t=(ru,en)=>L?en:ru,e=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const set=(id,text)=>document.getElementById(id).textContent=text,j=v=>JSON.stringify(v,null,2),ref=v=>v[0].split('-')[1].toUpperCase()+' / '+v[1];
function proof(f){return '<details><summary>'+t('Исходные фрагменты','Source fragments')+' ('+f.evidence.length+')</summary>'+f.evidence.map(s=>'<p class="muted">'+e(s.source_id)+' · Unicode ['+s.start+', '+s.end+') · SHA-256 '+e(s.sha256)+'</p><blockquote>'+e(s.text)+'</blockquote>').join('')+'</details>'}
function render(){document.documentElement.lang=L?'en':'ru';set('language',L?'Русский':'English');set('title',t('IL-6: структурированный контекст','IL-6: structured context'));
set('meta',D.source_count+' '+t('статей','papers')+' · '+D.family_count+' '+t('независимых семейств','independent families')+' · '+D.scope+' · '+D.run_id);
set('notice',t('Ретроспективная инженерная диагностика. Будущая цель не прочитана; модельных вызовов нет. Разметка Codex требует экспертной проверки.','Retrospective engineering diagnostic. Future target unread; no model calls. Codex annotations require expert review.'));
set('resultsTitle',t('Опубликованные результаты и новые прогнозы','Published findings and new forecasts'));
const names={known_union:t('Известные знания','Known findings'),frequency:t('Частотная база','Frequency baseline'),semantic:t('Семантический прогноз','Semantic forecast'),dependency:t('Прогноз с зависимостями','Dependency forecast')};
document.getElementById('metrics').innerHTML=Object.entries(D.modes).map(([k,v])=>'<div class="metric"><b>'+v.length+'</b>'+e(names[k])+'<small><br>'+t('Ранее: ','Previously: ')+D.prior_counts[k]+'</small></div>').join('');
set('meaning',t('Числа известных знаний и частотной базы показывают опубликованные ответы на вопрос, а не совпадения с будущей статьёй. Новые прогнозы считаются отдельно.','Known and frequency counts describe published answers, not matches with a future paper. New forecasts are counted separately.'));
set('traitsTitle',t('11 признаков каждого результата','11 features of each finding'));set('traitsNote',t('Синонимы и точные единицы нормализованы. Неизвестные признаки не заполнены предположениями. N, α, метод и конкретный исход сохранены.','Synonyms and exact units normalized. Unknown features are not imputed. N, alpha, model and exact outcome retained.'));
document.getElementById('profiles').innerHTML=D.profiles.map(p=>{const o=D.observations.find(o=>j(o.reference)===j(p.reference));return '<details class="card"><summary>'+e(ref(p.reference))+' · '+t('неизвестны: ','unknown: ')+e(p.unknown_features.map(n=>D.labels[n][L]).join(', '))+'</summary><p>'+e(o.original.text)+'</p><pre>'+e(j({finding:o.projected.modality,original_measurements:o.original.measurements}))+'</pre><table><thead><tr><th>'+t('Признак','Feature')+'</th><th>'+t('Значение и происхождение','Value and provenance')+'</th></tr></thead><tbody>'+Object.entries(p.record.features).map(([k,f])=>'<tr><td>'+e(D.labels[k][L])+'</td><td><span class="'+(f.status==='not_reported'?'unknown':'')+'">'+e(f.status)+'</span><pre>'+e(j(f.value))+'</pre><p>'+e(f[L?'note_en':'note_ru'])+'</p>'+proof(f)+'</td></tr>').join('')+'</tbody></table></details>'}).join('');
set('pairsTitle',t('Проверка переноса между контекстами','Context transfer checks'));set('pairsNote',t('Разные или неизвестные условия ограничивают этот алгоритм переноса; они не опровергают связь IL-6 и когнитивного снижения. Совпадение полного профиля не доказывает равенство фактов. Все 11 признаков, включая N и α, сейчас сопоставляются строго.','Different or unknown conditions restrict this transfer algorithm; they do not refute the IL-6 association. An identical full profile does not establish fact equivalence. All 11 features, including N and alpha, are currently matched strictly.'));
set('filterLabel',t('Пары:','Pairs:'));const opts=document.getElementById('pairFilter').options;opts[0].text=t('Разные семейства','Independent families');opts[1].text=t('Все, включая одно семейство','All, including same family');renderPairs();
set('foldsTitle',t('Удержание целого семейства с учётом времени','Temporal whole-family holdouts'));
document.getElementById('folds').innerHTML='<div class="scroll"><table><thead><tr><th>'+t('Удержанное семейство','Held-out family')+'</th><th>'+t('Ранние обучающие семейства','Earlier training families')+'</th><th>'+t('Прогнозы / оцениваемые','Issued / scorable')+'</th></tr></thead><tbody>'+D.folds.map(f=>'<tr><td>'+e(f.plan.family)+'</td><td>'+f.training_family_count+'</td><td>'+f.evaluation.modes.semantic.issued_answers+' / '+f.evaluation.modes.semantic.scorable_answers+'</td></tr>').join('')+'</tbody></table></div>';
set('nextTitle',t('Следующий шаг','Next step'));set('next',t('Сначала определить и проверить допустимый перенос между близкими контекстами. Отдельно прогнозировать направление эффекта и статистическую значимость: последняя зависит от N, α и модели. Проверку выполнить на том же корпусе с удержанием целого семейства; будущую цель пока не открывать.','Define and validate transfer between related contexts first. Predict effect direction separately from statistical significance, which depends on N, alpha and model. Test on the same corpus with whole-family holdouts; keep the future target sealed.'));
set('gateTitle',t('Критерии допуска к будущей цели','Future-target readiness checks'));set('gate',j(D.readiness));
set('provenanceTitle',t('Проверки и происхождение','Checks and provenance'));set('provenance',t('Контроли семантики: ','Semantic controls: ')+D.controls.passed+'/'+D.controls.total+'. '+t('Старые источники, карты и результаты сохранены. Health ABC: только уточнение возраста из явно связанного описания набора участников; это не 20-я обучающая статья.','Old sources, maps and results retained. Health ABC: age from explicitly linked recruitment methods only; this is not a 20th training paper.'));
set('technicalTitle',t('Техническая диагностика','Technical diagnostics'));set('technical',j({normalization:D.normalization,diagnostics:D.diagnostics,forecast_sha256:D.forecast_sha256}));}
function renderPairs(){const pairs=D.pairs.filter(p=>document.getElementById('pairFilter').value==='all'||p.independent_families);document.getElementById('pairs').innerHTML=pairs.map(p=>'<details class="card"><summary>'+e(ref(p.left))+' ↔ '+e(ref(p.right))+' · '+e(p.status)+'</summary><p>'+t('Неизвестны: ','Unknown: ')+e(p.unknown.map(n=>D.labels[n][L]).join(', '))+'</p><table><thead><tr><th>'+t('Различающийся признак','Different feature')+'</th><th>'+e(ref(p.left))+'</th><th>'+e(ref(p.right))+'</th></tr></thead><tbody>'+p.differences.map(d=>'<tr><td>'+e(D.labels[d.feature][L])+'</td><td><pre>'+e(j(d.left.value))+'</pre></td><td><pre>'+e(j(d.right.value))+'</pre></td></tr>').join('')+'</tbody></table></details>').join('');}
document.getElementById('language').onclick=()=>{L=1-L;render()};document.getElementById('pairFilter').onchange=renderPairs;render();
</script></html>'''
