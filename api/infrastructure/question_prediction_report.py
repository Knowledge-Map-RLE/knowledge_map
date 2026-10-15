"""Автономный двуязычный обзор диагностики семантики и прогноза по вопросу."""
from __future__ import annotations
import html
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable

VERSION = "4"
MODE_LABELS = {"semantic": "Семантические шаблоны", "dependency": "Шаблоны с зависимостями",
               "known_union": "Известные знания", "frequency": "Частотная база"}


def validate_report_bindings(audit, sealed, evaluation):
    binding = sealed["binding"]
    require(fingerprint(binding) == sealed["run_id"] and binding["question"] == sealed["question"],
            "Forecast report binding differs")
    require(fingerprint(audit["binding"]) == audit["audit_id"], "Audit report binding differs")
    require(audit["binding"]["analysis_binding"] == binding["analysis_binding"], "Report analysis versions differ")
    require(len(binding["sources"]) == len(binding["maps"]), "Forecast map bindings differ")
    audited = {(m["article_id"], m["run_id"]): m for m in audit["maps"]}
    for ref, snapshot in zip(binding["sources"], binding["maps"]):
        source = audited.get((ref["article_id"], ref["run_id"]))
        require(source is not None and all(source[key] == snapshot[key] for key in ("graph_sha256", "source_sha256")),
                "Audited source differs from the forecast source")
        require(audit["binding"]["registry"].get(ref["article_id"]) == binding["registry"][ref["article_id"]],
                "Audited source metadata differs")
    if evaluation is not None:
        require(evaluation["binding"]["run_id"] == sealed["run_id"]
                and evaluation["binding"]["prediction_sha256"] == fingerprint(sealed)
                and evaluation["evaluation_id"] == fingerprint(evaluation["binding"]),
                "Evaluation report belongs to a different forecast")


def build_report(audit, sealed, evaluation=None):
    validate_report_bindings(audit, sealed, evaluation)
    modes = sealed["modes"]
    text = ["# Прогноз по заданному вопросу", "", sealed["question"]["text_ru"], "",
        f"Срез доступных публикаций: {sealed['question']['cutoff']}; горизонт: {sealed['question']['horizon_end']}.",
        f"Неизменяемый прогноз: `{sealed['run_id']}`.", "",
        f"Контроль семантики: {audit['controls_passed']}/{audit['control_count']} контрольных пар; "
        f"{audit['native_claim_count']} исходных и {audit['analytic_claim_count']} аналитических утверждений.",
        "Контрольные атомы дополняют анализ и не изменяют утверждённые карты. Разметка Codex требует экспертной проверки.", "",
        f"Корпус прогноза: {len(sealed['binding']['sources'])} статей, {sealed['claim_count']} аналитических утверждений. "
        "Диагностический корпус не расширяет обучающий набор.", "",
        "| Режим | Результатов | Правил |", "|---|---:|---:|"]
    partial = [o for o in sealed["binding"].get("source_origin", [])
               if o.get("research_origin", {}).get("full_article_formalization") is False]
    if partial:
        text = text[:-2] + ["Ручное исследовательское представление содержит только выбранные утверждения по вопросу. "
                       "Полные тексты сохранены; полная формализация статей и production-карты не создавались. "
                       "Исходная семантика этого представления также подготовлена Codex, поэтому её покрытие "
                       "не является проверкой автоматического извлечения.", ""] + text[-2:]
    for mode in modes:
        text.append(f"| {MODE_LABELS[mode]} | {len(modes[mode])} | {len(sealed['rules'].get(mode, []))} |")
    text += ["", "Поддержка шаблонов считается по независимым семьям исследований. "
        "Повторная публикация и цитирование не увеличивают её. Отсутствие результата не является отрицательным испытанием.",
        "Баллы служат ранжированию; они не являются откалиброванной вероятностью.", ""]
    if sealed.get("readiness"):
        ready = sealed["readiness"]
        text += ["Готовность к независимой цели: `" + ready["status"] + "`.",
                 "Независимых семей с собственным результатом по точному вопросу: " + str(len(ready["independent_families"])) + ".",
                 "Непройденные проверки: " + (", ".join(ready["failed_checks"]) or "нет") + ".", ""]
    if audit.get("diagnostic_version"):
        text += [f"Исходные карты полностью представляют {audit['native_control_endpoints_represented']} из "
                 f"{audit['native_control_endpoint_count']} концов контрольных пар. Дополнительные ручные атомы считаются отдельно.",
                 "Причины непригодности утверждений пересекаются; их количества нельзя складывать как число блоков.", ""]
    if not modes["semantic"] and not modes["dependency"]:
        text += ["Новый прогноз пуст: в явно заданном корпусе нет поддержанных минимум двумя независимыми "
            "семьями исторических эпизодов «более ранние предпосылки → позднейший собственный результат». "
            "Это ограничение корпуса и текущей семантики, а не доказательство невозможности прогнозирования.", ""]
    if evaluation:
        text += [f"Отдельная оценка: `{evaluation['evaluation_id']}`; релевантных утверждений цели: {evaluation['relevant_target_claims']}.",
                 "Цель не участвовала в обучении. Пустой прогноз не подтверждает научную работоспособность системы.", ""]
        for origin in evaluation["binding"].get("target_origin", []):
            details = origin.get("evaluation_origin", {})
            text += ["Статья оценщика: " + details.get("source_metadata", {}).get("title", origin["article_id"]),
                "Проверяются выбранные утверждения из основного текста, а не полная формализация новой статьи. "
                "Таблицы, представленные только изображениями, численно не транскрибированы. "
                "Это ретроспективная инженерная диагностика; подбор статьи включал просмотр поисковых фрагментов.", ""]
        text += ["Коэффициенты с неизвестной размерностью, разные измерительные шкалы и статистически не обнаруженная связь "
                 "не превращаются в подтверждённый общий биологический эффект или его опровержение.", ""]
    else:
        text += ["Оценщик цели ещё не запускался; файл прогноза уже запечатан.", ""]
    text += ["Внешних и локальных модельных вызовов, переводчика и эмбеддингов: 0. Расход внутренних токенов Codex неизвестен.",
             "Старые GOLD-файлы, графы и результаты экспериментов сохранены.", "",
             "Следующий научный шаг определяется проверками готовности: уточнить неподтверждённые контексты, "
             "добавить подходящие первичные исследования и зафиксировать исторические эпизоды. "
             "Положительный синтетический тест проверяет алгоритм; он не заменяет результат на реальных статьях."]
    payload = {"report_version": VERSION, "audit": {k: v for k, v in audit.items() if k != "claims"}, "claims": audit["claims"],
               "forecast": sealed, "evaluation": evaluation}
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    markup = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Прогноз по вопросу · Карта знаний</title><style>
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#152c43;background:#eef3f8}body{max-width:1180px;margin:32px auto;padding:0 20px}h1{font-size:30px}button,select{font:inherit;padding:10px 16px;border:1px solid #aac0d4;border-radius:8px;background:white;color:#153d66;cursor:pointer}button:hover{background:#dcebf8}.cards{display:flex;gap:12px;flex-wrap:wrap}.card,section{background:white;border:1px solid #d3deea;border-radius:12px;padding:20px;margin:16px 0}.card{flex:1;min-width:170px}.number{font-size:30px;font-weight:700}small{color:#536b80}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #e2e9f1}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f6fa;padding:14px;border-radius:8px;font-size:13px}blockquote{border-left:3px solid #3979b5;padding-left:12px;margin:12px 0}code{overflow-wrap:anywhere}label{display:block;margin:16px 0}details{margin:12px 0}a{color:#1461a7}</style>
<header><button id="lang">English</button><h1 id="title"></h1><p id="question"></p><small id="binding"></small></header>
<div class="cards" id="cards"></div><p class="card" id="origin-disclosure" hidden></p><section><h2 id="modes-title"></h2><table id="modes"></table><p id="warning"></p></section>
<section><h2 id="readiness-title"></h2><p id="readiness"></p><pre id="eligibility"></pre></section>
<section><h2 id="predictions-title"></h2><select id="prediction-mode"></select><div id="predictions"></div></section>
<section><h2 id="controls-title"></h2><label><select id="control"></select></label><div id="detail"></div></section>
<section><h2 id="target-title"></h2><div id="target"></div></section>
<section><h2 id="diagnostics-title"></h2><pre id="diagnostics"></pre></section>
<script type="application/json" id="data">__DATA__</script><script>
const D=JSON.parse(document.querySelector('#data').textContent);let language='ru';const el=id=>document.getElementById(id);
const words={ru:{title:'Прогноз по заданному вопросу',modes:'Четыре режима',controls:'Контрольные пары и исходные фрагменты',diagnostics:'Причины отказа и границы вывода',mode:'Режим',count:'Результатов',rules:'Правил',native:'Исходных утверждений',passed:'Контрольных пар',hypotheses:'Новых гипотез',warning:'Разметка Codex требует экспертной проверки. Балл ранжирования не является вероятностью. Отсутствие утверждения не опровергает гипотезу. Пустой прогноз не подтверждает научную работоспособность.'},en:{title:'Question-constrained forecast',modes:'Four modes',controls:'Control pairs and source evidence',diagnostics:'Rejections and limitations',mode:'Mode',count:'Results',rules:'Rules',native:'Original statements',passed:'Control pairs',hypotheses:'New hypotheses',warning:'Codex annotations need expert review. Ranking scores are not probabilities. Absence of a statement is not a refutation. An empty forecast does not validate scientific predictability.'}};
function text(node,value){node.textContent=value}function cell(row,value,tag='td'){const n=document.createElement(tag);text(n,value);row.append(n)}
const reportWords={ru:{sources:'источников прогноза',corpus:'Утверждений источников',diagnostic:'Исходных в диагностике',predictions:'Прогноз и его основания',empty:'Результатов в этом режиме нет.',episodes:'Допустимых исторических эпизодов',labels:{semantic:'Семантические шаблоны',dependency:'Шаблоны с зависимостями',known_union:'Известные знания',frequency:'Частотная база'}},en:{sources:'forecast sources',corpus:'Source statements',diagnostic:'Original diagnostic statements',predictions:'Forecast and its evidence',empty:'No results in this mode.',episodes:'Eligible historical episodes',labels:{semantic:'Semantic templates',dependency:'Templates with dependencies',known_union:'Known knowledge',frequency:'Frequency baseline'}}};
function render(){
 const w=words[language],r=reportWords[language],controlValue=el('control').value,modeValue=el('prediction-mode').value||'dependency';
 el('lang').textContent=language==='ru'?'English':'Русский';document.documentElement.lang=language;
 const partial=(D.forecast.binding.source_origin||[]).some(o=>o.research_origin?.full_article_formalization===false);
 el('origin-disclosure').hidden=!partial;
 text(el('origin-disclosure'),language==='ru'?'Ручное представление содержит только выбранные утверждения по вопросу. Полные тексты сохранены; полная формализация и production-карты не создавались. Покрытие подготовленных Codex атомов не проверяет автоматическое извлечение.':'This manual representation contains selected question-relevant claims only. Complete sources are preserved; full article formalization and production maps were not created. Coverage of Codex-prepared atoms does not test automatic extraction.');
 text(el('title'),w.title);text(el('question'),D.forecast.question[language==='ru'?'text_ru':'text_en']);
 text(el('binding'),D.forecast.run_id+' · '+D.forecast.question.cutoff+' → '+D.forecast.question.horizon_end+' · '+D.forecast.binding.sources.length+' '+r.sources);
 for(const [id,key] of [['modes-title','modes'],['controls-title','controls'],['diagnostics-title','diagnostics'],['warning','warning']])text(el(id),w[key]);
 el('cards').replaceChildren();
 for(const [label,value] of [[r.corpus,D.forecast.claim_count],[r.diagnostic,D.audit.native_claim_count],[w.passed,D.audit.controls_passed+'/'+D.audit.control_count],[w.hypotheses,D.forecast.modes.dependency.length]]){
  const n=document.createElement('div');n.className='card';const num=document.createElement('div');num.className='number';text(num,value);n.append(num,document.createTextNode(label));el('cards').append(n);
 }
 el('modes').replaceChildren();let row=document.createElement('tr');[w.mode,w.count,w.rules].forEach(v=>cell(row,v,'th'));el('modes').append(row);
 for(const [mode,items] of Object.entries(D.forecast.modes)){row=document.createElement('tr');[r.labels[mode],items.length,(D.forecast.rules[mode]||[]).length].forEach(v=>cell(row,v));el('modes').append(row)}
 text(el('predictions-title'),r.predictions);el('prediction-mode').replaceChildren();
 for(const mode of Object.keys(D.forecast.modes)){const o=document.createElement('option');o.value=mode;text(o,r.labels[mode]);el('prediction-mode').append(o)}
 el('prediction-mode').value=modeValue;el('control').replaceChildren();
 D.audit.controls.forEach((c,i)=>{const o=document.createElement('option');o.value=i;text(o,c.id+' · '+(c.passed?'✓':'!')+' · '+c.expected_relations.join(', '));el('control').append(o)});
 if(controlValue)el('control').value=controlValue;
 text(el('readiness-title'),language==='ru'?'Готовность корпуса к независимой цели':'Corpus readiness for an independent target');
 const ready=D.forecast.readiness;
 text(el('readiness'),ready?(ready.target_reading_allowed?(language==='ru'?'Порог готовности пройден.':'Readiness gate passed.'):(language==='ru'?'Цель читать рано: ':'Do not read the target yet: ')+ready.failed_checks.join(', ')):(language==='ru'?'Порог готовности не рассчитывался для этой версии.':'Readiness was not calculated for this version.'));
 text(el('eligibility'),JSON.stringify({readiness:ready,source_eligibility:D.forecast.eligibility?{total:D.forecast.eligibility.total,eligible:D.forecast.eligibility.eligible,blocked:D.forecast.eligibility.blocked,reason_counts:D.forecast.eligibility.reason_counts}:null,native_control_endpoints_represented:D.audit.native_control_endpoints_represented,native_control_endpoint_count:D.audit.native_control_endpoint_count},null,2));
 text(el('diagnostics'),JSON.stringify({forecast:D.forecast.diagnostics,evaluation:D.evaluation},null,2));detail();predictions();
}
function predictions(){
 const r=reportWords[language],mode=el('prediction-mode').value,items=D.forecast.modes[mode]||[];el('predictions').replaceChildren();
 if(!items.length){const p=document.createElement('p');text(p,r.empty+' '+r.episodes+': '+(D.forecast.diagnostics[mode]?.episodes??D.forecast.episodes.length));el('predictions').append(p)}
 items.forEach((item,i)=>{const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');text(s,r.labels[mode]+' · '+(i+1));text(p,JSON.stringify(item,null,2));d.append(s,p);el('predictions').append(d)});
}
function detail(){const c=D.audit.controls[+el('control').value];el('detail').replaceChildren();if(!c)return;const p=document.createElement('p');text(p,c.note_ru);el('detail').append(p);for(const pair of c.comparisons){const det=document.createElement('details');const sum=document.createElement('summary');text(sum,pair.left+' ↔ '+pair.right+' · '+pair.relation);det.append(sum);for(const id of [pair.left,pair.right]){const claim=Object.values(D.claims).flat().find(c=>c.claim_id===id);if(!claim)continue;const title=document.createElement('p');text(title,claim.evidence.article_id+' · '+claim.knowledge_id+' · '+claim.text);det.append(title);for(const s of claim.evidence.spans){const q=document.createElement('blockquote');text(q,s.text+' ['+s.start+':'+s.end+']');det.append(q)}const pre=document.createElement('pre');text(pre,JSON.stringify(claim.proposition,null,2));det.append(pre)}el('detail').append(det)}if(c.native_details){const det=document.createElement('details'),s=document.createElement('summary'),pre=document.createElement('pre');text(s,language==='ru'?'Расхождения исходной семантики по полям':'Native semantic field discrepancies');text(pre,JSON.stringify(c.native_details,null,2));det.append(s,pre);el('detail').append(det)}}
function target(){text(el('target-title'),language==='ru'?'Выбранные знания отдельного оценщика':'Selected evidence in the separate evaluator');el('target').replaceChildren();const note=document.createElement('p');text(note,language==='ru'?'Ретроспективная диагностика, не слепая научная проверка. Представлены выбранные фрагменты; значения таблиц-изображений не транскрибированы.':'Retrospective engineering diagnostic, not a blinded scientific validation. Selected prose claims only; image-only tables were not transcribed.');el('target').append(note);for(const c of D.evaluation?.target_claims||[]){const d=document.createElement('details');const s=document.createElement('summary');text(s,c.knowledge_id+' · '+(language==='ru'&&c.text_ru?c.text_ru:c.text));d.append(s);const pre=document.createElement('pre');text(pre,JSON.stringify(c.proposition,null,2));d.append(pre);for(const f of c.evidence.spans){const q=document.createElement('blockquote');text(q,f.text+' ['+f.start+':'+f.end+']');d.append(q)}el('target').append(d)}}
el('lang').onclick=()=>{language=language==='ru'?'en':'ru';render();target()};el('control').onchange=detail;el('prediction-mode').onchange=predictions;render();target();
</script></html>'''.replace("__DATA__", data)
    return "\n".join(text) + "\n", markup


def save_report(folder, audit, sealed, evaluation=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    markdown, markup = build_report(audit, sealed, evaluation)
    for name, content in (("report.ru.md", markdown), ("report.html", markup)):
        path = folder / name
        encoded = content.encode("utf-8")
        write_immutable(path, encoded)
