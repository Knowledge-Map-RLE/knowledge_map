"""Автономный отчёт о проверке полного источника и отдельном исходе исследования."""
import json
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore

HTML = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Matsushima: полный текст</title>
<style>body{margin:0;background:#f2f5fa;color:#1c2b42;font:16px/1.55 system-ui}main{max-width:1100px;margin:auto;padding:24px}button,select{font:inherit;padding:10px 14px;border:1px solid #6983a4;border-radius:8px;background:white;color:#16365f;cursor:pointer}button{background:#245a9f;color:white;font-weight:600}nav{display:flex;gap:12px;flex-wrap:wrap}.card{background:white;border:1px solid #d5deea;border-radius:12px;padding:20px;margin:20px 0}.warn{background:#fff5df}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #d5deea;padding:10px;text-align:left;vertical-align:top}blockquote{white-space:pre-wrap;background:#f5f8fc;border-left:4px solid #245a9f;padding:14px;margin-left:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 system-ui}.muted{color:#536882}mark{background:#ffeaa3}summary{cursor:pointer;font-weight:600}a{color:#175299}code{overflow-wrap:anywhere}h1{line-height:1.25}@media(max-width:650px){main{padding:14px}.card{padding:12px}table{font-size:14px}}</style>
<main><nav><button id="language">English</button><a href="../source/article.pdf" id="pdf"></a></nav><h1 id="title"></h1><section class="card warn" id="decision"></section>
<section class="card"><h2 id="factsTitle"></h2><div id="facts"></div></section>
<section class="card"><h2 id="evidenceTitle"></h2><select id="observation"></select><div id="evidence"></div><details><summary id="semanticsTitle"></summary><pre id="semantics"></pre></details><details><summary id="sourceTitle"></summary><pre id="source"></pre></details></section>
<section class="card"><h2 id="gateTitle"></h2><div id="gate"></div></section>
<section class="card"><h2 id="nextTitle"></h2><p id="next"></p><p id="limits"></p></section><footer id="footer"></footer></main>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let lang='ru';
const t=(ru,en)=>lang==='ru'?ru:en,e=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={'matrix-methods':['Материал: Methods','Specimen: Methods'],'matrix-results':['Материал: Results','Specimen: Results'],'mmse-model':['Что прогнозирует модель','Model estimand'],'mmse-result':['IL-6 и MMSE: таблица 5','IL-6 and MMSE: Table 5'],'population':['Выборка и время','Population and timing'],'limitations':['Ограничения','Limitations']};
function table(head,rows){return '<table><thead><tr>'+head.map(v=>'<th>'+e(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+e(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function render(){document.documentElement.lang=lang;el('language').textContent=t('English','Русский');el('pdf').textContent=t('Предоставленный полный PDF','Supplied complete PDF');el('title').textContent=t('Matsushima 2015: проверка полного текста','Matsushima 2015: full-text verification');
el('decision').textContent=t('Полный текст получен и прочитан. Новых источников в обучении: 0. Новый прогноз не выдан. Для сопоставимого годового изменения MMSE остаётся одно подтверждённое семейство TOOTH.','Complete text received and read. New training sources: 0. No new forecast issued. The comparable annual MMSE-change branch retains one confirmed family, TOOTH.');
el('factsTitle').textContent=t('Что установлено по статье','Findings from the complete paper');el('facts').innerHTML=table([t('Проверка','Check'),t('Результат','Finding')],D.observations.map(o=>[labels[o.id][lang==='ru'?0:1],o['text_'+lang]]));
el('evidenceTitle').textContent=t('Доказательные фрагменты и скрытое представление','Evidence fragments and semantic representation');el('semanticsTitle').textContent=t('Семантические поля проверяемого факта','Semantic fields of the audited fact');el('sourceTitle').textContent=t('Полный извлечённый текст с References','Complete extracted text including References');
el('gateTitle').textContent=t('Решение по корпусу','Corpus decision');el('gate').textContent=t('Устранён прежний блокер отсутствия полного текста. Конфликт материала сохранился и обнаружен внутри самой статьи. Независимый блокер: Analysis 3 моделирует последующий уровень MMSE, а не изменение за период. Средние 28,11 и 27,39 не превращают β из таблицы 5 в коэффициент изменения. Даже при разрешении конфликта материала эта модель не подходит выбранному исходу.','The prior missing-full-text blocker is removed. The specimen conflict persists within the paper. A separate blocker remains: Analysis 3 models later MMSE level rather than change over the interval. Group means 28.11 and 27.39 do not turn Table 5 beta into a change coefficient. Resolving specimen alone would still not make this model compatible with the selected outcome.');
el('nextTitle').textContent=t('Следующий шаг','Next step');el('next').textContent=t('Продолжить проверку других исторических источников с явно заданным изменением MMSE и подходящим материалом. Уточнение у авторов может разрешить плазму/сыворотку, но не создаст отсутствующую оценку изменения. Самостоятельно пересчитать её без индивидуальных данных нельзя.','Continue checking other historical sources with explicit MMSE change and eligible specimen. Author clarification may resolve plasma/serum, but it cannot supply an unreported change estimate. It cannot be recalculated without individual data.');
el('limits').textContent=t('Это проверка знаний по конкретному вопросу, не новая полная карта статьи и не экспертная научная валидация. Прогнозируемую цель не выбирали и не читали. Поддержка шаблона требует двух независимых семейств исторических заключений с проверенными ранними предпосылками.','This is a question-specific knowledge audit, not a new complete article map or expert scientific validation. No forecast target was selected or read. Template support requires two independent historical conclusion families with verified earlier premises.');
el('footer').textContent=t('Источник пользователя сохранён с SHA-256. Старые версии и исходный корпус не заменены. Разметка и русские подписи: Codex. Модельных и сетевых вызовов в этой проверке нет.','Supplied source preserved with SHA-256. Previous versions and original corpus were not replaced. Annotation and Russian labels: Codex. No model or network calls in this audit.');
const old=el('observation').value;el('observation').innerHTML=D.observations.map((o,i)=>'<option value="'+i+'">'+e(labels[o.id][lang==='ru'?0:1])+'</option>').join('');el('observation').value=old||'0';renderEvidence();}
function renderEvidence(){const o=D.observations[Number(el('observation').value)],points=Array.from(D.source.text);for(const p of o.evidence){if(points.slice(p.start,p.end).join('')!==p.text)throw Error('Unicode provenance differs')}
el('evidence').innerHTML='<p>'+e(o['text_'+lang])+'</p>'+o.evidence.map(p=>'<p class="muted">Unicode ['+p.start+', '+p.end+')</p><blockquote>'+e(p.text)+'</blockquote>').join('')+'<p class="muted">SHA-256 <code>'+e(D.source.sha256)+'</code></p>';el('semantics').textContent=JSON.stringify(o.semantics,null,2);const p=o.evidence[0];el('source').innerHTML=e(points.slice(0,p.start).join(''))+'<mark>'+e(p.text)+'</mark>'+e(points.slice(p.end).join(''));}
el('observation').onchange=renderEvidence;el('language').onclick=()=>{lang=lang==='ru'?'en':'ru';render()};render();
</script></html>'''


def save_fulltext_question_audit_report(folder, payload):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c')
    write_immutable(folder / 'review.json', FilePredictionStore.encode(payload))
    write_immutable(folder / 'report.html', HTML.replace('__DATA__', encoded).encode('utf-8'))
    markdown = '''# Matsushima 2015: полный первичный текст

Полная журнальная статья (DOI 10.1016/j.jad.2014.10.030, страницы 9–14) предоставлена пользователем. PDF сохранён отдельно, текст всех шести страниц прочитан, Methods и таблицы просмотрены в изображениях. References сохранены и не используются как методы собственного исследования.

Блокер отсутствия полного текста снят. Конфликт плазма/сыворотка остаётся: Methods 2.3 говорит о плазме, Results на странице 11 — о сывороточных концентрациях в собственной выборке. Авторское резюме также сообщает сыворотку. Ни один документ не исправлен и ни один вариант не принят голосованием.

Независимый блокер: Analysis 3 использует балл MMSE при follow-up как зависимую переменную. Формула изменения, годового изменения или траектории, а также поправка на исходный MMSE не описаны. Средние MMSE исходно 28,11 и через три года 27,39 из таблицы 2 не дают коэффициент связи исходного IL-6 с индивидуальным изменением.

В таблице 5 для IL-6 и последующего MMSE: β=0,025, p=0,861. Сохранены исходный знак, целевая переменная и отсутствие сообщённого доверительного интервала. Стандартизация β не утверждается. Авторы не обнаружили статистической значимости; это не доказательство отсутствия биологического эффекта. Слова авторов cognitive decline не заменяют описанную зависимую переменную модели.

Kurogawa Study: возраст ≥65, исходное исключение явного когнитивного дефицита, включая деменцию. 99 исходных образцов крови, 64 при follow-up, 17 мужчин и 47 женщин. Формальный статус MCI не установлен. Не смешиваем число обследованных людей со числом образцов. Учитываем малую выборку, потери при follow-up и отсутствие BMI. Описанные в аннотации поправки на возраст, пол и образование не означают поправку на исходный MMSE.

Статья не добавлена к обучению ни исходного вопроса о снижении глобальной функции, ни ветки годового изменения MMSE. Кумулятивный скрининг содержит предыдущие четыре аналитические записи и новую запись Kurogawa; подтверждено только одно семейство TOOTH. Это отдельный исследовательский аудит с шестью семантическими наблюдениями, а не новая полная карта статьи. Исходные 19 статей, GOLD, карты, прошлые прогнозы и протокол не изменены. Новый прогноз не выдан, будущая цель не выбрана.

Следующий шаг — другие исторические исследования с явно определённым изменением MMSE. Уточнение материала у авторов не создаст отсутствующую оценку изменения; её нельзя получить из опубликованных средних и β без нужных данных. Автоматически расширять вопрос или подменять его последующим уровнем когнитивной функции нельзя.

Разметка Codex требует экспертной проверки. LLM, локальные модели, эмбеддинги и переводчик не вызывались. Работа с предоставленным файлом не использовала сеть. Сервисы не менялись. Токены Codex не измерены.
'''
    write_immutable(folder / 'report.ru.md', markdown.encode('utf-8'))
