"""Автономный двуязычный обзор полной сетки ограничений без выбора удачного варианта."""
import json
from domain.article_maps import fingerprint
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable

MODES = ('semantic', 'dependency', 'family_frequency_baseline')


def summarize(result):
    channel = result['outcome_channels']['reported_direction_exploratory']
    metrics = {}
    for mode in MODES:
        eligible = [f for f in result['retrospective_folds'] if f['evaluation']['outcome_channels']['reported_direction_exploratory']['targets']]
        values = [f['evaluation']['outcome_channels']['reported_direction_exploratory']['modes'][mode] for f in eligible]
        metrics[mode] = {key: sum(v[key] for v in values) for key in (
            'issued_answers', 'scorable_comparisons', 'unscorable_comparisons', 'agreements', 'different_signs', 'supported_target_comparisons')}
        metrics[mode]['scored_families'] = sorted({f['plan']['family'] for f, v in zip(eligible, values) if v['scorable_comparisons']})
        metrics[mode]['unanswered_target_families'] = sorted({f['plan']['family'] for f, v in zip(eligible, values) if not v['scorable_comparisons']})
        metrics[mode]['no_target_sealed_answers'] = sum(f['evaluation']['outcome_channels']['reported_direction_exploratory']['modes'][mode]['issued_answers']
            for f in result['retrospective_folds'] if not f['evaluation']['outcome_channels']['reported_direction_exploratory']['targets'])
    return {'sources': len(result['binding']['sources']), 'families': len(result['retrospective_folds']),
            'selected_modifier_claims': channel['eligible_modifier_claims'],
            'selected_modifier_families': len(channel['eligible_modifier_families']),
            'unknown_modifier_claims': len(channel['unknown_modifier_claims']),
            'current_semantic_forecasts': len(channel['modes']['semantic']),
            'current_dependency_forecasts': len(channel['modes']['dependency']),
            'strict_statistical_forecasts': len(result['outcome_channels']['statistical_detection_strict']['modes']['semantic']),
            'direction': metrics}


HTML = r'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IL-6: аудит ограничений контекста</title><style>
body{font:16px/1.55 system-ui;margin:0;background:#f2f5f9;color:#152840}main{max-width:1280px;margin:auto;padding:24px}
h1{font-size:29px;line-height:1.2}button,select{font:inherit;padding:9px 14px;border:1px solid #9aacbf;border-radius:8px;background:white;color:#152840;cursor:pointer}button{background:#1d4e8b;color:white}nav{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.card,details{background:white;padding:16px;border:1px solid #d4dfeb;border-radius:10px;margin:12px 0}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #dbe3ec;padding:10px;text-align:left;vertical-align:top}th{background:#e9eff7}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}blockquote{border-left:3px solid #1d4e8b;margin:12px 0;padding-left:14px}.scroll{overflow:auto}.hint{color:#53657d}.warning{background:#fff2ce}.num{font-size:21px;font-weight:700}.status{font-family:monospace;font-size:13px}a{color:#174e91}</style>
<main><nav><button id="language">English</button><select id="scope"></select><select id="variant"></select></nav>
<h1 id="title"></h1><div id="intro" class="card warning"></div><h2 id="gridTitle"></h2><div class="card scroll" id="grid"></div>
<h2 id="detailTitle"></h2><div class="card" id="metrics"></div><div id="diagnostics"></div>
<h2 id="sourceTitle"></h2><div id="sources"></div><h2 id="foldTitle"></h2><select id="fold"></select><div id="holdout"></div>
<p id="footer" class="hint"></p></main><script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let lang='ru';
const t=(ru,en)=>lang==='ru'?ru:en,e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={broad:['Широкий перенос','Broad transport'],mci:['MCI','MCI'],outcome:['Точное определение исхода','Exact outcome definition'],adjustments:['Точный набор поправок','Exact adjustment set']};
const vn=id=>id.split('+').map(k=>names[k][lang==='ru'?0:1]).join(' + '),mn=m=>({semantic:t('Семантический предиктор','Semantic predictor'),dependency:t('Предиктор с зависимостями','Dependency predictor'),family_frequency_baseline:t('Частотная база','Frequency baseline')}[m]);
const current=()=>D.scopes[el('scope').value].variants[el('variant').value];
function table(headers,rows){return '<table><thead><tr>'+headers.map(v=>'<th>'+e(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function render(){document.documentElement.lang=lang;el('language').textContent=t('English','Русский');const branch=D.scopes[el('scope').value],v=current(),s=v.summary;
el('title').textContent=t('IL-6: сколько поддержки остаётся при уточнении контекста','IL-6: how much support survives context restrictions');
el('intro').textContent=t('Те же 19 статей и 16 независимых семейств. Все восемь сочетаний MCI, исхода и поправок фиксированы перед расчётом. Корпус уже прочитан: это ретроспективная диагностика, не независимая проверка. Неизвестное не приравнивается к отсутствующему. Победитель по результатам не выбирается.','The same 19 papers and 16 independent families. All eight combinations were frozen before computation. The corpus was already inspected: retrospective diagnostics, not independent validation. Unknown is not absent. No winning variant is selected.');
el('gridTitle').textContent=t('Все варианты на одинаковом корпусе','All variants on the same corpus');
el('grid').innerHTML=table([t('Вариант','Variant'),t('Пригодные утверждения / семьи','Eligible claims / families'),t('Неизвестные признаки','Unknown traits'),t('Проверенные прогнозы: предиктор / база','Tested issued forecasts: predictor / baseline'),t('Совпало / сравнено: предиктор','Agreement / comparisons: predictor'),t('Совпало / сравнено: база','Agreement / comparisons: baseline')],Object.entries(branch.variants).map(([k,r])=>{const z=r.summary,a=z.direction.semantic,b=z.direction.family_frequency_baseline;return [vn(k),z.selected_modifier_claims+' / '+z.selected_modifier_families,z.unknown_modifier_claims,a.issued_answers+' / '+b.issued_answers,a.agreements+' / '+a.scorable_comparisons,b.agreements+' / '+b.scorable_comparisons]}));
el('detailTitle').textContent=vn(el('variant').value);el('metrics').innerHTML=table([t('Режим','Mode'),t('Выдано при наличии целевых ответов','Issued with target answers'),t('Сопоставимо','Scorable'),t('Совпало знаков','Same signs'),t('Различается','Different'),t('Несопоставимо','Unscorable'),t('Независимых проверенных семейств','Scored independent families'),t('Запечатано без ответа цели','Sealed without target answer')],Object.entries(s.direction).map(([m,z])=>[mn(m),z.issued_answers,z.scorable_comparisons,z.agreements,z.different_signs,z.unscorable_comparisons,z.scored_families.length,z.no_target_sealed_answers]));
el('diagnostics').innerHTML='<div class="card">'+e(t('Строгих статистических прогнозов: ','Strict statistical forecasts: ')+s.strict_statistical_forecasts)+'. '+e(t('Новые независимые цели не открывались. Совпадение знака не доказывает эффект. Разные оценки одной семьи не являются независимыми испытаниями.','No new independent target was opened. Sign agreement does not prove an effect. Multiple estimates from one family are not independent trials.'))+'</div><details><summary>'+e(t('Текущие гипотезы, предпосылки и независимая поддержка','Current hypotheses, premises and independent support'))+'</summary><pre>'+e(JSON.stringify(v.direction.modes,null,2))+'</pre></details><details><summary>'+e(t('Почему шаблоны отклонены','Why templates were rejected'))+'</summary><pre>'+e(JSON.stringify(v.direction.diagnostics,null,2))+'</pre></details><details><summary>'+e(t('Группы частотной базы: одна семья — один голос внутри контекста','Frequency strata: one family, one vote within context'))+'</summary><pre>'+e(JSON.stringify(v.direction.baseline_strata,null,2))+'</pre></details>';
el('sourceTitle').textContent=t('Исходные оценки и признаки переноса','Original estimates and transport traits');el('sources').innerHTML=v.direction.observations.map(r=>'<details><summary>'+e(r.reference.join(' / ')+' · '+r.original.evidence.family+' · '+r.direction.label)+'</summary><p>'+e(r.original.text)+'</p><pre>'+e(JSON.stringify({direction:r.direction,modifier_context:r.modifier_context},null,2))+'</pre><details><summary>'+e(t('Все признаки и доказательства их извлечения','All traits and extraction evidence'))+'</summary><pre>'+e(JSON.stringify(v.profiles.find(p=>JSON.stringify(p.reference)===JSON.stringify(r.reference)),null,2))+'</pre></details>'+((r.original.evidence.spans||[]).map(p=>'<p class="hint">Unicode ['+p.start+', '+p.end+') · SHA-256 '+e(r.original.evidence.source_sha256)+'</p><blockquote>'+e(p.text)+'</blockquote>').join(''))+'</details>').join('');
el('foldTitle').textContent=t('Удержание целого семейства во времени','Whole-family temporal holdout');const old=el('fold').value;el('fold').innerHTML=v.folds.map((f,i)=>'<option value="'+i+'">'+e(f.plan.family+' · '+f.plan.first_publication)+'</option>').join('');el('fold').value=old&&Number(old)<v.folds.length?old:'0';renderFold();
el('footer').textContent=t('Без модельных вызовов. Старые результаты сохранены. Точный исход включает шкалу, estimand, порог и направление; поправки сравниваются как нормализованные множества. Остальные различия по-прежнему требуют допущений широкого переноса.','No model calls. Earlier results preserved. Exact outcome includes scale, estimand, threshold and orientation; adjustments are compared as normalized sets. Other differences still require broad transport assumptions.');
}
function renderFold(){const v=current(),f=v.folds[Number(el('fold').value)],c=f.evaluation.outcome_channels.reported_direction_exploratory;
el('holdout').innerHTML='<div class="card"><strong>'+e(f.plan.family)+'</strong><p>'+e(t('Обучающих статей / семейств: ','Training papers / families: ')+f.training_source_count+' / '+f.training_family_count)+'</p><p class="status">'+e(f.forecast_run_id)+'</p><p>'+e(t('Прогноз сохранён до оценки удержанной семьи.','Forecast sealed before evaluating the heldout family.'))+'</p></div>'+Object.entries(c.modes).map(([m,z])=>'<details open><summary>'+e(mn(m))+'</summary><pre>'+e(JSON.stringify(z,null,2))+'</pre></details>').join('')+'<details><summary>'+e(t('Все целевые оценки и их неопределённость','All target estimates and uncertainty'))+'</summary><pre>'+e(JSON.stringify(c.targets,null,2))+'</pre></details>';}
function selectors(){const old=el('variant').value;el('variant').innerHTML=Object.keys(D.scopes[el('scope').value].variants).map(k=>'<option value="'+e(k)+'">'+e(vn(k))+'</option>').join('');el('variant').value=old||'broad';render();}
function scopes(){const old=el('scope').value;el('scope').innerHTML='<option value="primary">'+e(t('Основная ветка','Primary scope'))+'</option><option value="sensitivity">'+e(t('Расширенная ветка','Sensitivity scope'))+'</option>';el('scope').value=old||'primary';selectors();}
el('language').onclick=()=>{lang=lang==='ru'?'en':'ru';scopes()};el('scope').onchange=selectors;el('variant').onchange=render;el('fold').onchange=renderFold;scopes();
</script></html>'''


def save_modifier_review(folder, outputs, policy):
    scopes, summary = {}, {}
    for scope, output in outputs.items():
        variants = {}
        for name, result in output['variants'].items():
            variants[name] = {'run_id': result['run_id'], 'forecast_sha256': fingerprint(result),
                              'summary': summarize(result), 'direction': result['outcome_channels']['reported_direction_exploratory'],
                              'folds': result['retrospective_folds'], 'profiles': result['structured_context']['profiles']}
        scopes[scope] = {'controls': output['audit'], 'old_run_id': output['old_run_id'], 'variants': variants}
        summary[scope] = {name: variant['summary'] for name, variant in variants.items()}
    review = {'version': 'context-modifier-review-2', 'policy': policy, 'scopes': scopes, 'summary': summary,
              'expert_validated': False, 'prospective_validation': False, 'model_calls': 0}
    encoded = json.dumps(review, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    write_immutable(folder / 'review.json', FilePredictionStore.encode(review))
    write_immutable(folder / 'report.html', HTML.replace('__DATA__', encoded).encode('utf-8'))
    lines = ['# IL-6: аудит MCI, исхода и поправок', '',
             '19 статей, 16 независимых семейств. Полная сетка из восьми вариантов зафиксирована до расчёта.',
             'Это ретроспективная диагностика уже прочитанного корпуса. Выбор лучшего варианта и вывод о научной корректности запрещены.', '',
             'Точное сопоставление требует известных признаков. Неизвестный MCI не становится отсутствием MCI.', '',
             '| Ветка | Вариант | Пригодные знания / семьи | Прогнозы предиктора / базы | Знаки совпали / сравнены: предиктор | База |',
             '|---|---|---|---|---|---|']
    for scope, variants in summary.items():
        for name, value in variants.items():
            a, b = value['direction']['semantic'], value['direction']['family_frequency_baseline']
            lines.append(f"| {scope} | {name} | {value['selected_modifier_claims']} / {value['selected_modifier_families']} | {a['issued_answers']} / {b['issued_answers']} | {a['agreements']} / {a['scorable_comparisons']} | {b['agreements']} / {b['scorable_comparisons']} |")
    lines.extend(['', 'Число прогнозов учитывает только удержания с целевыми ответами. Запечатанные гипотезы без ответа цели показаны отдельно в HTML.',
                  'Несколько оценок одной семьи не являются независимыми испытаниями. Знак точечной оценки не равен доказанному биологическому эффекту.',
                  'Уточнение контекста может уменьшить поддержку до нуля; это недостаток подходящих данных для шаблона, а не доказательство отсутствия эффекта.',
                  'Следующий опыт должен заранее определить сопоставимый исход и поправки и иметь минимум два независимых исторических заключения.',
                  'Модели не вызывались; новая будущая цель не открывалась; старые карты и результаты сохранены.'])
    write_immutable(folder / 'report.ru.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    return review
