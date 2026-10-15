"""Автономное двуязычное представление аудита исторических первичных источников."""
import json
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore


HTML = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IL-6: исторические источники</title>
<style>body{margin:0;background:#f2f5fa;color:#203047;font:16px/1.6 system-ui}main{max-width:1150px;margin:auto;padding:24px}button,select{font:inherit;padding:10px 14px;border:1px solid #7085a0;border-radius:8px;background:white;color:#15385f;cursor:pointer}button{background:#245b9c;color:white;font-weight:600}.card{background:white;border:1px solid #d4deea;border-radius:12px;padding:20px;margin:20px 0}.warn{background:#fff5df}nav{display:flex;gap:14px;flex-wrap:wrap}a{color:#185693}table{width:100%;border-collapse:collapse}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dae2ec}pre,blockquote{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}blockquote{margin-left:0;padding:14px;border-left:4px solid #245b9c;background:#f5f8fc}mark{background:#ffe79b}summary{cursor:pointer;font-weight:600}h1{line-height:1.25}.muted{color:#53677f}code{overflow-wrap:anywhere}@media(max-width:650px){main{padding:12px}.card{padding:12px}table{font-size:14px}}</style>
<main><nav><button id="language">English</button><a href="../../matsushima-fulltext-v1/review-v1/report.html" id="previous"></a></nav><h1 id="title"></h1><section class="card warn" id="decision"></section>
<section class="card"><h2 id="summaryTitle"></h2><div id="summary"></div></section><section class="card"><h2 id="evidenceTitle"></h2><select id="observation"></select><p id="explanation"></p><a id="pdf"></a><div id="evidence"></div><details><summary id="semanticsTitle"></summary><pre id="semantics"></pre></details><details><summary id="sourceTitle"></summary><pre id="source"></pre></details></section>
<section class="card"><h2 id="gateTitle"></h2><div id="gate"></div><p id="limits"></p></section><section class="card"><h2 id="nextTitle"></h2><p id="next"></p></section><footer id="footer"></footer></main>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let lang='ru';
const t=(ru,en)=>lang==='ru'?ru:en,e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function table(head,rows){return '<table><thead><tr>'+head.map(v=>'<th>'+e(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function render(){document.documentElement.lang=lang;el('language').textContent=t('English','Русский');el('previous').textContent=t('Предыдущий аудит Matsushima','Previous Matsushima audit');el('title').textContent=D['title_'+lang];el('decision').textContent=D['decision_'+lang];el('summaryTitle').textContent=t('Результаты проверки источников','Source verification results');el('summary').innerHTML=table([t('Источник / анализ','Source / analysis'),t('Что установлено','Finding'),t('Допуск','Admission')],D.summaries.map(s=>[s.label,s['text_'+lang],s['status_'+lang]]));
el('evidenceTitle').textContent=t('Наблюдения и первичный текст','Observations and primary text');el('semanticsTitle').textContent=t('Скрытые семантические поля','Semantic fields');el('sourceTitle').textContent=t('Полный текст источника с выделенным фрагментом','Complete source text with highlighted fragment');el('gateTitle').textContent=t('Состояние эксперимента','Experiment status');el('gate').textContent=D['gate_'+lang];el('limits').textContent=D['limits_'+lang];el('nextTitle').textContent=t('Следующий шаг','Next step');el('next').textContent=D['next_'+lang];el('footer').textContent=D['footer_'+lang];
const selected=el('observation').value;el('observation').innerHTML=D.observations.map((o,i)=>'<option value="'+i+'">'+e(o['label_'+lang])+'</option>').join('');el('observation').value=selected||'0';renderEvidence();}
function renderEvidence(){const o=D.observations[Number(el('observation').value)],s=D.sources[o.source_sha256],points=Array.from(s.text);el('explanation').textContent=o['text_'+lang];el('pdf').textContent=t('Открыть сохранённый первичный PDF','Open saved primary PDF');el('pdf').href=s.pdf_local;el('semantics').textContent=JSON.stringify(o.semantics,null,2);
for(const p of o.evidence){if(points.slice(p.start,p.end).join('')!==p.text)throw Error('Unicode provenance differs')}
el('evidence').innerHTML=o.evidence.map(p=>'<p class="muted">Unicode ['+p.start+', '+p.end+')</p><blockquote>'+e(p.text)+'</blockquote>').join('')+'<p class="muted">SHA-256 <code>'+e(s.sha256)+'</code></p>';const p=o.evidence[0];el('source').innerHTML=e(points.slice(0,p.start).join(''))+'<mark>'+e(p.text)+'</mark>'+e(points.slice(p.end).join(''));}
el('language').onclick=()=>{lang=lang==='ru'?'en':'ru';render()};el('observation').onchange=renderEvidence;render();
</script></html>'''


def save_historical_question_audit_report(folder, payload, markdown):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    write_immutable(folder / 'review.json', FilePredictionStore.encode(payload))
    write_immutable(folder / 'report.html', HTML.replace('__DATA__', encoded).encode('utf-8'))
    write_immutable(folder / 'report.ru.md', markdown.encode('utf-8'))
