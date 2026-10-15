// Повторная независимая проверка всего корпуса и новых временных лицензий.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';

// Исходный проверяющий повторно сверяет 11 DAG, все источники и функциональные фреймы.
await import('./verify_functional_target_guard.mjs');
const review=resolve(import.meta.dir,'../../eval/whole_map_forecast/treatment-episodes-v1/review-v1');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function field(bytes,name){const s=bytes.toString(),m=new RegExp('^  "'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(!depth)return Buffer.from(s.slice(start,i+1));}assert.fail('Незавершённый JSON');}
function seal(folder){const bytes=read(resolve(folder,'predictions.json')),data=JSON.parse(bytes),p=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),p.prediction_sha256);assert.equal(rawJsonFingerprint(field(bytes,'binding')),data.run_id);
  for(const[f,d]of Object.entries(data.binding.implementation))assert.equal(hash(read(resolve(folder,'implementation',f))),d);
  assert.equal(data.model_calls,0);return{bytes,data};}
const receipt=json(resolve(review,'verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_treatment_episodes.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const tests=new Set();let executions=0;
for(const r of receipt.tests){const bytes=read(r.path);assert.equal(hash(bytes),r.sha256);
  const doc=new JSDOM(bytes.toString(),{contentType:'text/xml'}).window.document;let count=0;
  for(const s of doc.querySelectorAll('testsuite')){count+=Number(s.getAttribute('tests'));
    for(const k of ['errors','failures','skipped'])assert.equal(Number(s.getAttribute(k)),0);}
  assert.equal(count,r.tests);executions+=count;
  for(const t of doc.querySelectorAll('testcase'))tests.add(JSON.stringify([t.getAttribute('classname'),t.getAttribute('name')]));}
assert.equal(tests.size,91);assert.equal(tests.size,receipt.tests_unique);
const current=seal(receipt.run_path),functional=seal(receipt.functional_path),r=current.data;
assert.equal(r.version,'source-bound-treatment-episodes-1');assert.equal(rawJsonFingerprint(functional.bytes),r.binding.functional_sha256);
const previousReceiptPath=resolve(import.meta.dir,'../../eval/whole_map_forecast/functional-target-guard-v1/review-v2/bun-verification.json');
const previousReceipt=json(previousReceiptPath);assert.equal(previousReceipt.run_id,functional.data.run_id);
const fp=json(resolve(receipt.functional_path,'input-corpus.json')),orientation=seal(fp.orientation),op=json(resolve(fp.orientation,'input-corpus.json'));
const ip=json(resolve(op.previous,'input-corpus.json')),tp=json(resolve(ip.baseline,'input-corpus.json')),source=seal(tp.snapshot),contract=seal(op.applicability);
assert.equal(rawJsonFingerprint(source.bytes),r.binding.source_sha256);assert.deepEqual(r.binding.map_hashes,source.data.binding.map_hashes);
assert.equal(rawJsonFingerprint(field(contract.bytes,'cases')),r.binding.cases_sha256);
const auditBytes=read(resolve(receipt.run_path,'audit.json')),audit=JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes),r.binding.audit_sha256);assert.equal(audit.functional_sha256,r.binding.functional_sha256);
assert.equal(audit.source_sha256,r.binding.source_sha256);assert.deepEqual(audit.map_hashes,r.binding.map_hashes);
const maps=new Map();for(const e of json(resolve(tp.snapshot,'inputs-manifest.json')).sources){const bytes=read(resolve(tp.snapshot,e.map_path));
  assert.equal(hash(bytes),e.map_file_sha256);maps.set(JSON.parse(bytes).article_id,JSON.parse(bytes));}
assert.equal(maps.size,11);assert.equal(r.canonical_blocks,943);assert.equal(r.semantic_statements,1897);assert.equal(r.input_parts,915);
assert.equal(r.episodes.length,3);assert.equal(r.calendar_consequences.length,4);assert.equal(r.calendar_conflicts.length,1);assert.equal(r.protocol_conflicts.length,1);
assert.deepEqual(r.guarded_prototype,functional.data.guarded_prototype);assert.equal(r.guarded_prototype.is_executable_rule,false);
const assetBytes=new Map();for(const[id,e]of Object.entries(r.assets)){assert.equal(e.path.includes('..'),false);
  const bytes=read(resolve(receipt.run_path,e.path));assert.equal(hash(bytes),e.sha256);assetBytes.set(id,bytes);}
assert.deepEqual([...assetBytes.keys()].sort(),['atrosimab_figure7','atrosimab_xml']);
const xmlBytes=assetBytes.get('atrosimab_xml');assert.equal(hash(xmlBytes),'62f7a485973785e91c57ff8de3e3890c6569c39732313bd54e301ab9cb3aa420');
const xml=new JSDOM(xmlBytes.toString(),{contentType:'text/xml'}).window.document;
assert.equal(xml.querySelector('article-id[pub-id-type="pmcid"]').textContent,'PMC8294390');
const figure=xml.querySelector('fig[id="f7"]');assert.ok(figure);
assert.ok([...figure.querySelectorAll('graphic')].some(g=>g.getAttribute('xlink:href')==='fimmu-12-705485-g007.jpg'));
assert.equal(r.assets.atrosimab_figure7.source_url,'https://cdn.ncbi.nlm.nih.gov/pmc/blobs/ddea/8294390/8420d5cfc6a2/fimmu-12-705485-g007.jpg');
assert.equal(hash(assetBytes.get('atrosimab_figure7')),'fc2cdd3ba1d91c0aac2e780b0f30b4793b9aca2465cca64c239cf7797c6ebd82');
function jpegSize(bytes){assert.equal(bytes.readUInt16BE(0),0xffd8);let i=2;
  while(i<bytes.length){assert.equal(bytes[i++],0xff);while(bytes[i]===0xff)i++;const marker=bytes[i++];
    assert.notEqual(marker,0xda);const len=bytes.readUInt16BE(i);
    if([0xc0,0xc1,0xc2].includes(marker))return{height:bytes.readUInt16BE(i+3),width:bytes.readUInt16BE(i+5)};i+=len;}
  assert.fail('Нет размера изображения');}
assert.deepEqual(jpegSize(assetBytes.get('atrosimab_figure7')),{width:716,height:552});
function schedule(t){const s=t.schedule;if(s.form==='explicit')return s.points;
  assert.equal(s.form,'periodic');const first=BigInt(s.first),last=BigInt(s.last),step=BigInt(s.step);
  assert.ok(step>0n&&last>=first);assert.equal((last-first)%step,0n);const values=[];
  for(let v=first;v<=last;v+=step)values.push(String(v));return values;}
let quotes=0;const byCase=new Map();
for(const row of r.episodes){const e=row.entry,m=maps.get(e.article_id),c=contract.data.cases.find(c=>c.case_id===e.case_id);
  assert.ok(m&&c);assert.equal(row.case_id,e.case_id);assert.equal(e.run_id,m.run_id);assert.equal(e.source_sha256,m.source.sha256);
  assert.deepEqual(row.complete_case,c);assert.deepEqual(e,audit.entries.find(a=>a.case_id===e.case_id));
  assert.deepEqual(e.participants,Object.fromEntries(c.method.frame.statements[0].roles.map(p=>[p.role,p.value])));
  const native=new Map(m.graph.knowledge.map(k=>[k.knowledge_id,k]));
  assert.deepEqual(row.additional_complete_native_parents,e.additional_parent_ids.map(k=>native.get(k)));
  const allowed=new Set([...c.complete_basis.map(p=>p.knowledge),...row.additional_complete_native_parents]
    .flatMap(k=>k.semantic_frame.statements.flatMap(s=>s.provenance.unit_ids)));
  const units=new Map(m.source.units.map(u=>[u.id,u])),text=Array.from(m.source.text);
  for(const q of e.evidence){const u=units.get(q.unit_id);assert.ok(u&&allowed.has(q.unit_id));assert.ok(u.start<=q.start&&q.end<=u.end&&q.end<=m.source.content_end);
    assert.equal(text.slice(q.start,q.end).join(''),q.text);assert.equal(hash(Buffer.from(q.text)),q.sha256);quotes++;}
  const clinical=e.episodes.filter(t=>t.purpose==='clinical_followup');assert.equal(clinical.length,1);
  for(const t of e.episodes){assert.equal(t.unit,'day');assert.equal(t.source_asserted_effect_duration,null);
    const values=schedule(t);assert.equal(new Set(values).size,values.length);assert.ok(values.every((p,i)=>!i||BigInt(p)>BigInt(values[i-1])));
    if(t.observation_end!==null)assert.ok(BigInt(t.observation_end)>=BigInt(values.at(-1)));}
  assert.equal(row.functional_certificate_id,functional.data.guarded_prototype.certificates[e.case_id]);
  assert.equal(row.effect_duration_inferred,false);assert.equal(row.doses_and_full_parents_retained,true);byCase.set(e.case_id,row);
}
assert.equal(quotes,10);assert.equal(byCase.size,3);
const prophylactic=byCase.get('tros-prophylactic'),manifest=byCase.get('tros-manifest'),atros=byCase.get('atrosimab-manifest');
assert.equal(prophylactic.entry.dose_frequency_conflict,true);assert.ok(prophylactic.entry.additional_parent_ids.includes('K65'));
assert.deepEqual(schedule(prophylactic.entry.episodes[0]),['3','5','7','9','11','13']);
assert.equal(prophylactic.entry.episodes[0].observation_end,'16');
assert.deepEqual(manifest.entry.episodes.map(t=>schedule(t)),[['8','12','16'],['8','12']]);
assert.deepEqual(manifest.entry.episodes.map(t=>t.observation_end),['30','16']);
assert.equal(atros.entry.episodes[0].anchor,'manifest_disease_day');assert.deepEqual(schedule(atros.entry.episodes[0]),['1','4','8','12']);
assert.equal(atros.entry.episodes[0].observation_end,null);assert.equal(atros.planned_forecast_window,null);assert.equal(atros.unknown_clinical_observation_end,true);
assert.equal(atros.biological_clock_replaces_report_year_only_in_analysis,true);
const assessed=atros.entry.figure_assessment;assert.equal(assessed.panel,'A');assert.equal(assessed.axis_label,'days of EAE');
assert.equal(assessed.confirmed_assessment_day,'18');assert.equal(assessed.axis_upper_tick,'20');
assert.equal(assessed.last_assessment_established,false);assert.equal(assessed.pointwise_significance_inferred,false);assert.equal(assessed.expert_validated,false);
assert.equal(assessed.author,'Codex');assert.equal(assessed.direction,'lower_reported_group_mean');
for(const row of [prophylactic,manifest]){const w=row.planned_forecast_window;assert.equal(w.anchor,'post_immunization');
  assert.equal(w.time_quantifier,'some_assessed_time');assert.equal(w.future_duration_copied_from_result,false);assert.equal(w.all_times_effect_inferred,false);
  assert.equal(w.end,row.entry.episodes[0].observation_end);assert.equal(w.start,schedule(row.entry.episodes[0])[0]);}
for(const c of r.calendar_consequences){const row=byCase.get(c.case_id),t=row.entry.episodes.find(t=>t.id===c.procedure);
  const point=c.source_kind==='confirmed_plot_point'?row.entry.figure_assessment.confirmed_assessment_day:t.observation_end;
  assert.equal(c.difference_days,String(BigInt(point)-BigInt(schedule(t).at(-1))));
  assert.deepEqual(c.clock_context,{article_id:row.entry.article_id,case_id:c.case_id,procedure:t.id,anchor:t.anchor,unit:'day'});
  assert.equal(c.effect_duration_inferred,false);assert.equal(c.is_new_empirical_prediction,false);}
assert.deepEqual(r.calendar_consequences.map(c=>c.difference_days).sort(),['14','3','4','6']);
assert.equal(r.calendar_conflicts[0].reported_days,'12');assert.equal(r.calendar_conflicts[0].computed_days,'14');assert.equal(r.calendar_conflicts[0].source_was_corrected,false);
assert.equal(r.protocol_conflicts[0].figure_regimen.interval_days,'2');assert.equal(r.protocol_conflicts[0].methods_wording.interval_days,'3');
assert.equal(r.protocol_conflicts[0].source_was_corrected,false);assert.equal(r.eligible_window_families,0);
assert.equal(r.new_empirical_forecasts,0);assert.equal(r.scientific_success,false);assert.equal(r.graph_advantage_demonstrated,false);assert.equal(r.target_read,false);
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;assert.equal(doc.documentElement.lang,'ru');
assert.equal(doc.querySelectorAll('details').length,4);assert.equal(doc.querySelectorAll('table').length,2);
assert.equal(doc.querySelectorAll('img').length,1);assert.equal(doc.querySelector('img').getAttribute('src'),'figure7.jpg');
assert.equal(doc.querySelectorAll('script,link[href]').length,0);assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:r.run_id,tests_unique:tests.size,test_executions:executions,sources:11,canonical_blocks:943,semantic_statements:1897,
  upstream_source_provenance_uses:previousReceipt.source_provenance_uses,exact_episode_quotes:quotes,source_cases:3,
  clinical_episodes:3,tissue_episodes:1,calendar_consequences:4,calendar_conflicts:1,protocol_conflicts:1,
  confirmed_graphical_day:'18',axis_end_used_as_observation:false,pointwise_significance_inferred:false,
  method_windows_with_two_unconflicted_primary_families:false,new_empirical_forecasts:0,graph_advantage_demonstrated:false,
  model_calls:0,expert_validated:false,visual_report_review_claimed:false,
  upstream_receipt_sha256:hash(read(previousReceiptPath)),upstream_verifier_sha256:hash(read(resolve(import.meta.dir,'verify_functional_target_guard.mjs'))),
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const file=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(file))assert.deepEqual(read(file),bytes);else writeFileSync(file,bytes,{flag:'wx'});console.log(JSON.stringify(proof));
