"""Автономный обзор проверки первичных источников, без генерации и сетевых ресурсов."""
import json
from pathlib import Path

from domain.article_maps import digest, fingerprint, require
from infrastructure.immutable_files import write_immutable
from infrastructure.question_prediction_report import validate_report_bindings

VERSION = "primary-question-review-1"


def save_primary_review(folder, screening, bundles, audit, forecast):
    validate_report_bindings(audit, forecast, None)
    rows = {r["pmcid"]: r for r in screening["rows"]}
    require(len(rows) == len(screening["rows"]), "Duplicate screened primary source")
    references = {(r["article_id"], r["run_id"]) for r in forecast["binding"]["sources"]}
    require(references == {(b["map"]["article_id"], b["map"]["run_id"]) for b in bundles},
            "Prepared source runs differ from forecast")
    require(fingerprint({b["map"]["article_id"]: b["annotation"] for b in bundles})
            == forecast["binding"]["annotations_sha256"], "Prepared annotations differ from forecast")
    sources = []
    for bundle in bundles:
        metadata = bundle["origin"]["source_metadata"]
        pmcid = metadata["pmcid"]
        source = bundle["map"]["source"]
        require(pmcid in rows and source["sha256"] == rows[pmcid]["source_sha256"] == digest(source["text"]),
                "Screened source differs from prepared source")
        require(bundle["origin"]["purpose"] == "training", "Target cannot enter the primary source review")
        for evidence in rows[pmcid]["evidence"]:
            require(source["text"][evidence["start"]:evidence["end"]] == evidence["quote"], "Screening evidence differs")
        sources.append({"pmcid": pmcid, "title": metadata["title"], "source": source["text"],
                        "source_sha256": source["sha256"], "run_id": bundle["map"]["run_id"],
                        "claims": bundle["annotation"]["claims"],
                        "labels": bundle["map"]["translations"]["ru"]["knowledge_labels"]})
    require(set(rows) == {s["pmcid"] for s in sources}, "Primary source review corpus differs")
    require(len(sources) == len(forecast["binding"]["sources"]), "Forecast corpus differs from source review")
    artifact = {"version": VERSION, "screening": screening, "sources": sources,
                "audit": {k: v for k, v in audit.items() if k != "claims"}, "forecast": forecast}
    artifact["review_id"] = fingerprint(artifact)
    payload = json.dumps(artifact, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    markup = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>IL-6 · Проверка первичных источников</title><style>
body{font:16px system-ui;color:#16334a;background:#eef3f8;max-width:1260px;margin:28px auto;padding:0 20px}h1{font-size:28px}button,select{font:inherit;background:white;border:1px solid #91acc1;border-radius:8px;padding:10px 16px;cursor:pointer}button:hover{background:#dceaf6}section{background:white;border:1px solid #cfdae5;border-radius:12px;margin:18px 0;padding:20px}table{border-collapse:collapse;width:100%}th,td{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #dbe4ee}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace;max-height:650px;overflow:auto;background:#f1f6fa;padding:16px}blockquote{border-left:3px solid #3d82b7;padding-left:16px;margin-left:0}small{color:#536c80}summary{cursor:pointer}mark{background:#ffe6a0}#source-meta{overflow-wrap:anywhere}.alert{border-left:5px solid #cf8625}label{display:block;margin:14px 0}</style>
<header><button id="language">English</button><h1 id="title"></h1><p id="question"></p><small id="binding"></small></header>
<section class="alert"><h2 id="status-title"></h2><p id="status"></p><p id="scope"></p></section>
<section><h2 id="screen-title"></h2><table id="screen"></table></section>
<section><h2 id="mode-title"></h2><table id="modes"></table><p id="mode-warning"></p></section>
<section><h2 id="source-title"></h2><label><select id="article"></select></label><p id="source-meta"></p><select id="claim"></select><div id="claim-detail"></div><details><summary id="full-title"></summary><pre id="full-source"></pre></details></section>
<section><h2 id="control-title"></h2><select id="control"></select><pre id="control-detail"></pre></section>
<section><h2 id="next-title"></h2><p id="next"></p></section>
<script type="application/json" id="data">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),E=id=>document.getElementById(id);let lang='ru';
const words={ru:{title:'IL-6: проверка первичных исследований',status:'Готовность к новой независимой цели',scope:'Это ручная частичная формализация по вопросу, а не новые полные карты статей. 5 полных текстов, 4 семьи исследований, 21 выбранное утверждение. Контрольные пары размечены Codex и требуют экспертной проверки. Модельных вызовов, переводчика и эмбеддингов: 0. Старые карты сохранены.',screen:'Пригодность для точного вопроса',article:'Статья',matrix:'Материал исходного анализа',age:'Возраст',reason:'Причины исключения',modes:'Четыре режима',mode:'Режим',count:'Результатов',rules:'Правил',warning:'Пустой прогноз не доказывает невозможность научного предсказания. Необнаруженная статистическая связь не означает отсутствия биологического эффекта. Другой материал, маркер, исход или возраст не подставляется вместо заданного вопроса.',sources:'Утверждения и полный источник',full:'Полный английский текст, включая таблицы и References',controls:'15 контрольных пар',next:'Следующий научный шаг',nextText:'Нужны подходящие полные первичные тексты с плазмой, возрастом ≥60 лет или отдельно опубликованной такой подгруппой, исходным отсутствием деменции и глобальным когнитивным исходом. Необходимо подтвердить минимум две независимые семьи реальных исторических эпизодов. Затем повторить этот же опыт, зафиксировать прогноз и только после прохождения порога читать новую независимую цель.'},en:{title:'IL-6: primary study screening',status:'Readiness for a new independent target',scope:'Manual question-specific partial formalization, not new complete article maps. 5 full texts, 4 study families, 21 selected claims. Controls are Codex annotations requiring expert review. Model, translation and embedding calls: 0. Existing maps are preserved.',screen:'Eligibility for the exact question',article:'Paper',matrix:'Baseline specimen',age:'Age',reason:'Exclusion reasons',modes:'Four modes',mode:'Mode',count:'Results',rules:'Rules',warning:'An empty forecast does not establish that scientific prediction is impossible. A statistically undetected association is not proof of no biological effect. A different specimen, marker, outcome or age group cannot substitute for the question.',sources:'Claims and complete sources',full:'Full English source, including tables and References',controls:'15 control pairs',next:'Next scientific step',nextText:'Obtain suitable primary full texts using plasma, adults aged at least 60 or a separately reported older stratum, absence of baseline dementia and global cognitive change. Verify at least two independent study families of actual historical episodes. Repeat the same experiment, seal the forecast, then read a new independent target only after the readiness gate passes.'}};
const labels={ru:{known_union:'Известные знания',frequency:'Частотная база',semantic:'Семантические шаблоны',dependency:'Шаблоны с зависимостями'},en:{known_union:'Known union',frequency:'Frequency baseline',semantic:'Semantic templates',dependency:'Dependency templates'}};
const counts={sources:D.sources.length,families:D.screening.independent_study_families,claims:D.sources.reduce((n,s)=>n+s.claims.length,0)};
words.ru.scope='Ручная частичная формализация по вопросу, а не новые полные карты. Полных текстов: '+counts.sources+'; семей исследований: '+counts.families+'; выбранных утверждений: '+counts.claims+'. Разметка Codex требует экспертной проверки. Модельных вызовов, переводчика и эмбеддингов: 0. Старые карты сохранены.';
words.en.scope='Manual question-specific partial formalization, not new complete article maps. Full texts: '+counts.sources+'; study families: '+counts.families+'; selected claims: '+counts.claims+'. Codex annotations need expert review. Model, translation and embedding calls: 0. Existing maps are preserved.';
words.ru.controls='Контрольных пар: '+D.audit.control_count;words.en.controls='Control pairs: '+D.audit.control_count;
const reasons={specimen_conflict:'Противоречие о материале',baseline_dementia_exclusion_unknown:'Не подтверждено исходное исключение деменции',baseline_specimen_serum:'Исходно сыворотка',clinical_dementia_exclusion_unknown:'Клиническое исключение деменции не описано',outcome_not_global_cognitive_change:'Другой исход: диагноз или изображение',dementia_status_wrong_phase:'Отсутствие деменции установлено в другой фазе',younger_participants_without_separate_older_estimate:'Есть участники моложе 60 лет; отдельной оценки для пожилых нет'};
const descriptions=new Map(D.screening.rows.flatMap(r=>[[r.specimen,r.specimen_ru||r.specimen],[r.age,r.age_ru||r.age],[r.reasons.join(', '),r.reasons.map(k=>reasons[k]||k).join('; ')]]));
function set(id,s){E(id).textContent=s}function row(table,values,header=false){const tr=document.createElement('tr');for(const v of values){const c=document.createElement(header?'th':'td');c.textContent=table.id==='screen'&&lang==='ru'&&!header?(descriptions.get(v)||v):v;tr.append(c)}table.append(tr)}
function render(){const w=words[lang],oldArticle=E('article').value,oldControl=E('control').value;document.documentElement.lang=lang;set('language',lang==='ru'?'English':'Русский');for(const [id,key] of [['title','title'],['status-title','status'],['scope','scope'],['screen-title','screen'],['mode-title','modes'],['mode-warning','warning'],['source-title','sources'],['full-title','full'],['control-title','controls'],['next-title','next'],['next','nextText']])set(id,w[key]);set('question',D.forecast.question[lang==='ru'?'text_ru':'text_en']);set('binding',D.forecast.run_id);const ready=D.forecast.readiness;set('status',(lang==='ru'?'Подходящих источников: ':'Eligible sources: ')+D.screening.eligible_full_sources+'/'+counts.sources+' · '+ready.status+' · '+(lang==='ru'?'Новая цель не выбрана и не прочитана.':'No new target selected or read.'));E('screen').replaceChildren();row(E('screen'),[w.article,w.matrix,w.age,w.reason],true);for(const r of D.screening.rows)row(E('screen'),[r.pmcid,r.specimen,r.age,r.reasons.join(', ')]);E('modes').replaceChildren();row(E('modes'),[w.mode,w.count,w.rules],true);for(const mode of ['known_union','frequency','semantic','dependency'])row(E('modes'),[labels[lang][mode],D.forecast.modes[mode].length,D.forecast.rules[mode]?.length||0]);E('article').replaceChildren();for(const s of D.sources){const o=document.createElement('option');o.value=s.pmcid;o.textContent=s.pmcid+' · '+s.title;E('article').append(o)}if(oldArticle)E('article').value=oldArticle;E('control').replaceChildren();for(const c of D.audit.controls){const o=document.createElement('option');o.value=c.id;o.textContent=c.id+' · '+(c.passed?'✓':'!')+' · '+c.comparisons.map(x=>x.relation).join(', ');E('control').append(o)}if(oldControl)E('control').value=oldControl;article();control()}
function article(){const s=D.sources.find(s=>s.pmcid===E('article').value);set('source-meta',s.run_id+' · SHA-256 '+s.source_sha256);E('claim').replaceChildren();for(const c of s.claims){const o=document.createElement('option');o.value=c.claim_id;o.textContent=c.knowledge_id+' · '+(lang==='ru'?s.labels[c.knowledge_id]:c.text);E('claim').append(o)}claim()}
function claim(){const s=D.sources.find(s=>s.pmcid===E('article').value),c=s.claims.find(c=>c.claim_id===E('claim').value);E('claim-detail').replaceChildren();const p=document.createElement('p');p.textContent=lang==='ru'?s.labels[c.knowledge_id]:c.text;E('claim-detail').append(p);for(const span of c.spans){const q=document.createElement('blockquote');q.textContent=span.text+' ['+span.start+':'+span.end+' Unicode code points]';E('claim-detail').append(q)}const d=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent=lang==='ru'?'Скрытая семантика и ограничения':'Hidden semantics and constraints';pre.textContent=JSON.stringify({predicate:c.predicate,roles:c.roles,negated:c.negated,modality:c.modality,context:c.context,measurements:c.measurements},null,2);d.append(summary,pre);E('claim-detail').append(d);const points=Array.from(s.source),span=c.spans[0],before=document.createTextNode(points.slice(0,span.start).join('')),mark=document.createElement('mark'),after=document.createTextNode(points.slice(span.end).join(''));mark.textContent=points.slice(span.start,span.end).join('');E('full-source').replaceChildren(before,mark,after)}
function control(){const c=D.audit.controls.find(c=>c.id===E('control').value);set('control-detail',JSON.stringify(c,null,2))}
E('language').onclick=()=>{lang=lang==='ru'?'en':'ru';render()};E('article').onchange=article;E('claim').onchange=claim;E('control').onchange=control;render();
</script></html>'''.replace("__DATA__", payload)
    claim_count = sum(len(s["claims"]) for s in sources)
    markdown = ["# IL-6: проверка первичных источников", "", forecast["question"]["text_ru"], "",
                f"Полных текстов: {len(sources)}; семей исследований: {screening['independent_study_families']}; "
                f"работ, подтверждающих весь набор условий точного вопроса: {screening['eligible_full_sources']}. "
                "Это результат ограниченного скрининга, а не систематический обзор всей литературы.", "",
                "| Статья | Материал | Возраст | Причины исключения |", "|---|---|---|---|"]
    for r in screening["rows"]:
        markdown.append(f"| {r['pmcid']} | {r.get('specimen_ru', r['specimen'])} | {r.get('age_ru', r['age'])} | {', '.join(r['reasons'])} |")
    markdown += ["", f"Сохранено выбранных утверждений: {claim_count}; английская семантика, отдельные русские подписи "
                 "и точные координаты цитат. Полные production-карты не создавались. "
                 "Сохранённые ранее GOLD-карты и эксперименты не изменены.", "",
                 f"Контрольные пары: {audit['controls_passed']}/{audit['control_count']}. Разметка Codex требует экспертной проверки.",
                 f"Неизменяемый прогон: `{forecast['run_id']}`.",
                 "Готовность: `" + forecast["readiness"]["status"] + "`. Новая цель не выбрана и не прочитана.", "",
                 "| Режим | Результатов | Выученных правил |", "|---|---:|---:|"]
    for mode in ("known_union", "frequency", "semantic", "dependency"):
        markdown.append(f"| {mode} | {len(forecast['modes'][mode])} | {len(forecast['rules'].get(mode, []))} |")
    for r in screening["rows"]:
        markdown += ["", "### " + r["pmcid"], ""] + ["- " + c for c in r.get("caveats_ru", r["caveats"])]
    markdown += ["", "Два реальных эпизода цитирования фиксируют более ранний результат и позднейший собственный результат. "
                 "Они не являются доказанными правилами вывода и не создают стрелки автоматически. "
                 "Неизвестный контекст, разные экспозиции и одна родительская когорта ограничивают обучение.", "",
                 "Необнаруженная статистическая связь не является доказательством отсутствия эффекта. "
                 "Пустой прогноз не доказывает невозможность научного предсказания.", "",
                 "Следующий шаг: найти подходящие полные первичные тексты и отдельно опубликованные оценки для пожилых; "
                 "подтвердить независимость и исторические эпизоды. Повторить опыт с тем же вопросом до чтения новой цели.", "",
                 "Внешних и локальных модельных вызовов, переводчика и эмбеддингов: 0. "
                 "Расход внутренних токенов Codex неизвестен. Предиктор не считает цитирования независимыми испытаниями."]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in (("report.html", markup), ("report.ru.md", "\n".join(markdown) + "\n"),
                          ("review.json", json.dumps(artifact, ensure_ascii=False, allow_nan=False))):
        write_immutable(folder / name, content.encode("utf-8"))
    return artifact["review_id"]
