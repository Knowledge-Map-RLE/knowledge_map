// Целочисленные миллионные доли дня независимо проверяют смену начала отсчёта.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';
await import('./verify_treatment_episodes_v2.mjs');
const review=resolve(import.meta.dir,'../../eval/whole_map_forecast/first-administration-clock-v1/review-v2');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function end(s,start){let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(!depth)return i+1;}assert.fail('Незавершённый JSON');}
function field(bytes,name){const s=bytes.toString(),m=new RegExp('^\\s*"'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;return Buffer.from(s.slice(start,end(s,start)));}
function arrayItems(bytes){const s=bytes.toString();assert.equal(s[0],'[');const result=[];let i=1;
  while(i<s.length){while(/\s|,/.test(s[i]))i++;if(s[i]===']')break;const finish=end(s,i);result.push(Buffer.from(s.slice(i,finish)));i=finish;}return result;}
function seal(folder){const bytes=read(resolve(folder,'predictions.json')),data=JSON.parse(bytes),p=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),p.prediction_sha256);assert.equal(rawJsonFingerprint(field(bytes,'binding')),data.run_id);
  for(const[f,d]of Object.entries(data.binding.implementation))assert.equal(hash(read(resolve(folder,'implementation',f))),d);
  return{bytes,data};}
function units(s){assert.match(s,/^-?\d{1,13}(?:\.\d{1,6})?$/);const negative=s.startsWith('-'),[whole,fraction='']=s.replace(/^-/,'').split('.');
  const value=BigInt(whole)*1000000n+BigInt(fraction.padEnd(6,'0'));return negative?-value:value;}
function decimal(n){const negative=n<0n;if(negative)n=-n;const fraction=String(n%1000000n).padStart(6,'0').replace(/0+$/,'');
  return(negative?'-':'')+String(n/1000000n)+(fraction?'.'+fraction:'');}
const receipt=json(resolve(review,'verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_first_administration_clock.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const tests=new Set();for(const t of receipt.tests){const bytes=read(t.path);assert.equal(hash(bytes),t.sha256);
  const doc=new JSDOM(bytes.toString(),{contentType:'text/xml'}).window.document;let count=0;
  for(const s of doc.querySelectorAll('testsuite')){count+=Number(s.getAttribute('tests'));
    for(const k of ['errors','failures','skipped'])assert.equal(Number(s.getAttribute(k)),0);}
  assert.equal(count,t.tests);for(const p of doc.querySelectorAll('testcase'))tests.add(JSON.stringify([p.getAttribute('classname'),p.getAttribute('name')]));}
assert.equal(tests.size,24);assert.equal(receipt.tests_unique,tests.size);
const current=seal(receipt.run_path),previous=seal(receipt.episode_path),r=current.data;
assert.equal(r.version,'source-bound-first-administration-clock-2');assert.equal(rawJsonFingerprint(previous.bytes),r.binding.episode_sha256);
assert.equal(r.canonical_blocks,943);assert.equal(r.semantic_statements,1897);assert.equal(r.input_parts,915);
assert.deepEqual(r.source_calendar_consequences,previous.data.calendar_consequences);
assert.deepEqual(r.source_calendar_conflicts,previous.data.calendar_conflicts);assert.deepEqual(r.source_protocol_conflicts,previous.data.protocol_conflicts);
assert.deepEqual(r.source_guarded_prototype,previous.data.guarded_prototype);
const oldRows=new Map(arrayItems(field(previous.bytes,'episodes')).map(bytes=>[JSON.parse(bytes).case_id,bytes]));
const refs=new Set(),proofs=new Map();let coordinates=0;
for(const bytes of arrayItems(field(current.bytes,'clock_proofs'))){const p=JSON.parse(bytes),old=JSON.parse(oldRows.get(p.case_id));
  assert.equal(rawJsonFingerprint(field(bytes,'complete_source_case')),rawJsonFingerprint(oldRows.get(p.case_id)));
  assert.equal(rawJsonFingerprint(bytes.toString().replace(/,\s*"id"\s*:\s*"[a-f0-9]{64}"\s*}$/, '}')),p.id);
  const e=old.entry.episodes.find(t=>t.id===p.procedure);assert.ok(e);assert.equal(p.purpose,e.purpose);assert.equal(p.phase,old.complete_case.features.phase);
  const ref=p.reference,{id,...refData}=ref;assert.equal(rawJsonFingerprint(JSON.stringify(refData)),id);assert.equal(ref.target_anchor,'first_administration_of_this_episode');
  assert.deepEqual(ref.source_clock_context,{article_id:old.entry.article_id,case_id:p.case_id,procedure:p.procedure,anchor:e.anchor,unit:e.unit});
  assert.equal(ref.unit,'day');assert.ok(!refs.has(id));refs.add(id);proofs.set(p.id,p);
  const sourcePoints=e.schedule.form==='explicit'?e.schedule.points:Array.from({length:Number((BigInt(e.schedule.last)-BigInt(e.schedule.first))/BigInt(e.schedule.step))+1},
    (_,i)=>String(BigInt(e.schedule.first)+BigInt(i)*BigInt(e.schedule.step)));
  assert.equal(ref.first_dose_day,sourcePoints[0]);assert.equal(p.relative_doses.length,sourcePoints.length);
  function check(bound,source,origin){assert.equal(bound.source_origin,origin);assert.equal(bound.point.reference_id,id);assert.equal(bound.point.unit,'day');
    assert.equal(bound.point.value,decimal(units(source)-units(ref.first_dose_day)));
    assert.equal(decimal(units(bound.point.value)+units(ref.first_dose_day)),source);
    assert.equal(bound.coordinate_was_copied_from_its_own_procedure,true);assert.equal(bound.new_effect_duration_inferred,false);coordinates++;}
  p.relative_doses.forEach((point,i)=>check(point,sourcePoints[i],'performed_dose'));
  if(e.observation_end===null)assert.equal(p.relative_endpoint,null);else check(p.relative_endpoint,e.observation_end,'source_method_endpoint');
  if(e.purpose==='clinical_followup'&&old.entry.figure_assessment!==null){assert.equal(p.relative_graphical_points.length,1);
    check(p.relative_graphical_points[0],old.entry.figure_assessment.confirmed_assessment_day,'source_result_plot');}
  else assert.equal(p.relative_graphical_points.length,0);
  assert.deepEqual(p.unchanged_interval_days,sourcePoints.slice(1).map((v,i)=>decimal(units(v)-units(sourcePoints[i]))));
  assert.deepEqual(p.unchanged_interval_days,p.relative_doses.slice(1).map((v,i)=>decimal(units(v.point.value)-units(p.relative_doses[i].point.value))));
  assert.deepEqual(p.source_dose_specifications,old.complete_case.method.frame.statements[0].attributes.filter(a=>['dose','doses'].includes(a.name)));
  if(e.purpose==='clinical_followup'&&old.planned_forecast_window!==null){const w=p.relative_method_window;assert.equal(w.reference_id,id);assert.equal(w.start,'0');
    assert.equal(w.end,p.relative_endpoint.point.value);assert.equal(w.time_quantifier,'some_assessed_time');assert.equal(w.new_effect_duration_inferred,false);}
  else assert.equal(p.relative_method_window,null);
  assert.equal(p.source_numbers_and_clock_retained,true);assert.equal(p.biological_onset_equivalence_inferred,false);
  assert.equal('first_dose_is_not_biological_onset'in p,false);
  assert.equal(p.doses_or_scales_converted,false);assert.equal(p.effect_duration_inferred,false);assert.equal(p.new_empirical_prediction,false);
}
assert.equal(refs.size,4);assert.equal(coordinates,19);assert.equal(r.comparisons.length,3);
for(const c of r.comparisons){const a=proofs.get(c.left),b=proofs.get(c.right);assert.ok(a&&b);assert.equal(a.purpose,b.purpose);
  assert.equal(c.same_reference_type,true);assert.equal(c.same_source_clock_identity,a.reference.id===b.reference.id);
  assert.equal(c.same_phase,a.phase===b.phase);assert.equal(c.same_relative_dosing_schedule,JSON.stringify(a.relative_doses.map(p=>p.point.value))===JSON.stringify(b.relative_doses.map(p=>p.point.value)));
  assert.equal(c.same_dose_specifications,rawJsonFingerprint(JSON.stringify(a.source_dose_specifications))===rawJsonFingerprint(JSON.stringify(b.source_dose_specifications)));
  assert.equal(c.experimental_equivalence,false);assert.equal(c.transfer_of_effect_established,false);}
assert.deepEqual(r.source_temporal_relations,r.normalized_temporal_relations);assert.equal(r.source_temporal_relations.length,4);
assert.equal(r.relative_reference_equates_experiments,false);assert.equal(r.empirical_generator_run,false);
assert.equal(r.new_empirical_forecasts,0);assert.equal(r.graph_advantage_demonstrated,false);assert.equal(r.scientific_success,false);assert.equal(r.model_calls,0);assert.equal(r.target_read,false);
// Независимые сгенерированные проверки точной арифметики и сохранения порядка.
let pairs=0;const points=['0','0.01','1','3','8','12','16','30','100'];
for(const first of ['0','0.02','3','8','100'])for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
  const a=units(points[i])-units(first),b=units(points[j])-units(first);assert.ok(a<b);assert.equal(b-a,units(points[j])-units(points[i]));pairs++;}
assert.equal(pairs,180);assert.equal(decimal(units('999999999999.999999')-units('999999999999.999998')),'0.000001');
assert.deepEqual(['6','8'].map(onset=>decimal(units(onset)-units('8'))),['-2','0']);
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;assert.equal(doc.documentElement.lang,'ru');assert.equal(doc.querySelectorAll('details').length,5);
assert.equal(doc.querySelectorAll('table').length,1);assert.equal(doc.querySelectorAll('[src],link[href],script').length,0);assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:r.run_id,tests_unique:tests.size,sources:11,canonical_blocks:943,semantic_statements:1897,
  episode_references:4,source_cases:3,reversible_coordinates:coordinates,independent_generated_pair_checks:pairs,
  comparisons:3,unknown_endpoint_preserved:true,temporal_evidence_unchanged:true,source_disagreements_preserved:true,
  empirical_generator_run:false,new_empirical_forecasts:0,graph_advantage_demonstrated:false,model_calls:0,visual_review_claimed:false,
  upstream_receipt_sha256:hash(read(resolve(import.meta.dir,'../../eval/whole_map_forecast/treatment-episodes-v1/review-v2/bun-verification.json'))),
  upstream_verifier_sha256:hash(read(resolve(import.meta.dir,'verify_treatment_episodes_v2.mjs'))),
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const file=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(file))assert.deepEqual(read(file),bytes);else writeFileSync(file,bytes,{flag:'wx'});console.log(JSON.stringify(proof));
