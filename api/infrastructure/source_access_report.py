"""Автономный двуязычный просмотр конфликтующих описаний источника без сетевых ресурсов."""
import json
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable

HTML = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matsushima: аудит источника</title><style>
body{font:16px/1.55 system-ui,sans-serif;background:#f4f6fa;color:#182638;margin:0}main{max-width:1100px;margin:auto;padding:24px}h1{line-height:1.2}.card{background:white;border:1px solid #d6deeb;border-radius:12px;padding:20px;margin:18px 0}button,select{font:inherit;background:#fff;border:1px solid #5b6c85;border-radius:7px;padding:9px 14px;cursor:pointer}button{background:#2555a6;color:white;font-weight:600}.badge{padding:8px 12px;display:inline-block;background:#fff0d8;border-radius:6px}blockquote{border-left:4px solid #c17916;margin:12px 0;padding:12px;background:#fff8ed;white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #dbe1eb}small,.muted{color:#536279}code{overflow-wrap:anywhere}a{color:#174fa7}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}mark{background:#ffe099}button:focus-visible,select:focus-visible{outline:3px solid #83aeed}@media(max-width:650px){main{padding:15px}table{font-size:14px}.card{padding:12px}}
</style><main><button id="language">English</button><h1 id="title"></h1><p id="intro"></p><div class="badge" id="decision"></div>
<section class="card"><h2 id="conflictTitle"></h2><div id="conflict"></div><p id="interpretation"></p></section>
<section class="card"><h2 id="evidenceTitle"></h2><select id="document"></select><div id="evidence"></div><details><summary id="sourceTitle"></summary><pre id="source"></pre></details></section>
<section class="card"><h2 id="accessTitle"></h2><div id="access"></div></section>
<section class="card"><h2 id="nextTitle"></h2><p id="next"></p><p id="limits"></p><p id="exposure"></p></section>
<footer id="footer"></footer></main><script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let lang='ru';
const t=(ru,en)=>lang==='ru'?ru:en,e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function table(headers,rows){return '<table><thead><tr>'+headers.map(v=>'<th>'+e(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function render(){document.documentElement.lang=lang;el('language').textContent=t('English','Русский');el('title').textContent=t('Matsushima: полный текст и конфликт материала','Matsushima: full text and specimen conflict');
el('intro').textContent=t('Проверена следующая историческая статья для вопроса о плазменном IL-6 и последующем изменении MMSE. Это аудит источника; состав обучения не расширен.','The next historical candidate was checked for baseline plasma IL-6 and subsequent MMSE change. This source audit does not expand training.');
el('decision').textContent=t('Новых обучающих источников: 0 · Новый прогноз: не выдан','New training sources: 0 · New forecast: not issued');
el('conflictTitle').textContent=t('Два несовместимых описания','Two conflicting descriptions');el('conflict').innerHTML=table([t('Документ','Document'),t('Материал','Specimen'),t('Полный первичный текст','Full primary text')],D.documents.map(d=>[d['label_'+lang],d.assertions[0].value=== 'plasma'?t('Плазма','Plasma'):t('Сыворотка','Serum'),t('Нет','No')]));
el('interpretation').textContent=t('Английская аннотация сообщает плазму; японское авторское резюме содержит 血清検体 (образцы сыворотки). Не определяем правильный вариант голосованием и не исправляем документы. Материал остаётся неразрешённым до проверки полного Methods.','The English abstract reports plasma; the Japanese author summary uses 血清検体 (serum samples). No majority vote or source correction resolves this conflict. The specimen remains unresolved pending full Methods verification.');
el('evidenceTitle').textContent=t('Точные фрагменты','Exact fragments');el('sourceTitle').textContent=t('Сохранённый вспомогательный документ','Preserved auxiliary document');el('accessTitle').textContent=t('Что удалось получить','Acquisition results');
el('access').innerHTML=table([t('Проверка','Check'),t('Результат','Result')],D.access_checks.map(v=>[v['label_'+lang],v['note_'+lang]]));
el('nextTitle').textContent=t('Что нужно для продолжения','Requirements to proceed');el('next').textContent=t('Получить полный журнальный текст или полный авторский manuscript с Methods и таблицами. Затем проверить материал, определение изменения MMSE, исключение деменции, поправки и временные точки. Эта статья пока не подходит ни для обучения, ни для слепой будущей цели: её аннотация уже прочитана.','Obtain the complete journal paper or complete author manuscript with Methods and tables. Then check specimen, MMSE-change definition, dementia exclusion, adjustments and temporal anchors. The article is currently neither training evidence nor a blind future target: its abstract has already been read.');
el('limits').textContent=t('Для ветки непрерывного годового MMSE остаётся одно подтверждённое семейство TOOTH. Две подходящие статьи ещё не гарантируют правило: нужны две независимые семьи исторических заключений с проверенными более ранними предпосылками. Успех предсказания не установлен.','The continuous annual MMSE branch still has one confirmed family, TOOTH. Two eligible papers alone do not establish a template: two independent historical conclusion families with verified earlier premises are required. Predictive success has not been established.');
el('exposure').textContent=t('Поиск вновь вернул фрагменты публикаций после временной границы. Их идентификаторы сохранены отдельно; они исключены из будущей слепой номинации и не используются в обучении. Полные будущие статьи не загружались.','Search again exposed post-cutoff snippets. Their identifiers were recorded separately, excluded from future blind nomination and not used for training. No future full papers were downloaded.');
el('footer').textContent=t('Разметка и русский перевод вспомогательных подписей: Codex, требуется экспертная проверка. LLM, эмбеддинги и переводчик не вызывались. Прежние карты, GOLD, корпус и результаты сохранены.','Annotation and Russian auxiliary labels: Codex; expert review required. No LLM, embeddings or translator were called. Prior maps, GOLD, corpus and results were preserved.');
const old=el('document').value;el('document').innerHTML=D.documents.map((d,i)=>'<option value="'+i+'">'+e(d['label_'+lang])+'</option>').join('');el('document').value=old||'0';renderEvidence();}
function renderEvidence(){const d=D.documents[Number(el('document').value)],p=d.assertions[0].evidence[0],points=Array.from(d.text);if(points.slice(p.start,p.end).join('')!==p.text)throw Error('Unicode source differs');
el('evidence').innerHTML='<p><a href="'+e(d.url)+'">'+e(d['label_'+lang])+'</a></p><p class="muted">Unicode ['+p.start+', '+p.end+')</p><blockquote>'+e(p.text)+'</blockquote><p>'+e(d['note_'+lang])+'</p><small>SHA-256 <code>'+e(d.sha256)+'</code></small>';
el('source').innerHTML=e(points.slice(0,p.start).join(''))+'<mark>'+e(p.text)+'</mark>'+e(points.slice(p.end).join(''));}
el('document').onchange=renderEvidence;el('language').onclick=()=>{lang=lang==='ru'?'en':'ru';render()};render();
</script></html>'''


def save_source_access_report(folder, data, markdown):
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    write_immutable(folder / 'review.json', FilePredictionStore.encode(data))
    write_immutable(folder / 'report.html', HTML.replace('__DATA__', encoded).encode('utf-8'))
    write_immutable(folder / 'report.ru.md', markdown.encode('utf-8'))
