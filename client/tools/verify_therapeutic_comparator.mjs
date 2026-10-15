// Проверка исправления PBS без подмены генетического контроля и научного успеха.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/therapeutic-comparator-v1');
const read = p => readFileSync(resolve(root,p)), json = p => JSON.parse(read(p));
const hash = x => createHash('sha256').update(x).digest('hex');
const fp = x => rawJsonFingerprint(Buffer.from(JSON.stringify(x)));
function rawField(raw,name) {
  const text=raw.toString('utf8'), match=new RegExp('^  "'+name+'":\\s*','m').exec(text);
  assert.ok(match); const start=match.index+match[0].length; let depth=0,quoted=false,escaped=false;
  for(let i=start;i<text.length;i++) {
    const ch=text[i]; if(quoted){if(escaped)escaped=false;else if(ch==='\\')escaped=true;else if(ch==='"')quoted=false;continue;}
    if(ch==='"'){quoted=true;continue;}if(ch==='{'||ch==='[')depth++;else if(ch==='}'||ch===']')depth--;
    if(depth===0)return Buffer.from(text.slice(start,i+1));
  }assert.fail('Незавершённое поле');
}
function seal(folder) {
  const raw=readFileSync(resolve(folder,'predictions.json')), data=JSON.parse(raw);
  assert.equal(rawJsonFingerprint(raw),JSON.parse(readFileSync(resolve(folder,'seal.json'))).prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(raw,'binding')),data.run_id);
  for(const [name,digest] of Object.entries(data.binding.implementation))assert.equal(hash(readFileSync(resolve(folder,'implementation',name))),digest);
  assert.equal(data.model_calls,0);assert.equal(data.graph_advantage_demonstrated,false);return {folder,raw,data};
}
const receipt=json('review-v1/verification.json'), report=json('review-v1/data.json');
for(const [name,digest] of Object.entries(receipt.files))assert.equal(hash(read('review-v1/'+name)),digest);
for(const [path,digest] of Object.entries(receipt.builders))assert.equal(hash(readFileSync(path)),digest);
assert.equal(hash(read('tests-v2.xml')),receipt.tests_sha256);
const tests=read('tests-v2.xml').toString();assert.match(tests,/tests="196"/);assert.match(tests,/failures="0"/);assert.match(tests,/errors="0"/);
const main=seal(receipt.main_snapshot), control=seal(receipt.control_snapshot);
assert.deepEqual(main.data.binding.implementation,control.data.binding.implementation);
assert.equal(main.data.version,'family-held-out-operation-transfer-3');
function upstream(transfer) {
  const descriptor=JSON.parse(readFileSync(resolve(transfer.folder,'input-corpus.json')));
  const contract=seal(descriptor.snapshot);assert.equal(rawJsonFingerprint(contract.raw),transfer.data.binding.input_sha256);
  const before=JSON.parse(readFileSync(resolve(descriptor.snapshot,'input-corpus.json')));
  const forecast=seal(before.snapshot);assert.equal(rawJsonFingerprint(forecast.raw),contract.data.binding.input_sha256);
  return {contract,forecast};
}
const after=upstream(main),before=upstream(control);
assert.deepEqual(after.forecast.data.binding.implementation,before.forecast.data.binding.implementation);
for(const key of ['references','map_hashes','families','context_audit_sha256','model_audit_sha256','origin_audit_sha256',
  'compound_licenses_sha256','method_clauses_sha256','limits','version'])
  assert.deepEqual(after.forecast.data.binding[key],before.forecast.data.binding[key]);
assert.equal(before.forecast.data.part_views.length,906);assert.equal(after.forecast.data.part_views.length,910);
const oldViews=new Map(before.forecast.data.part_views.map(v=>[JSON.stringify(v.key),v]));
const newViews=new Map(after.forecast.data.part_views.map(v=>[JSON.stringify(v.key),v]));
let unchanged=0;
for(const [key,view] of oldViews)if(!view.projection_proof.role_binding_proof){assert.deepEqual(newViews.get(key),view);unchanged++;}
assert.equal(unchanged,894);
const oldProofs=before.forecast.data.operation_role_bindings.proofs,newProofs=after.forecast.data.operation_role_bindings.proofs;
assert.equal(oldProofs.length,12);assert.equal(newProofs.length,16);
for(const old of oldProofs) {
  const match=newProofs.find(p=>JSON.stringify(p.entry)===JSON.stringify(old.entry));assert.ok(match);
  const oldView=[...oldViews.values()].find(v=>v.projection_proof.role_binding_proof?.id===old.id);
  const newView=[...newViews.values()].find(v=>v.projection_proof.role_binding_proof?.id===match.id);
  assert.deepEqual(oldView.frame,newView.frame);assert.deepEqual(oldView.native_key,newView.native_key);
}
const manifest=JSON.parse(readFileSync(resolve(after.forecast.folder,'inputs-manifest.json'))),maps=new Map();let knowledge=0;
for(const entry of manifest.sources) {
  const bytes=readFileSync(resolve(after.forecast.folder,entry.map_path));assert.equal(hash(bytes),entry.map_file_sha256);
  const map=JSON.parse(bytes);maps.set(map.article_id,map);knowledge+=map.graph.knowledge.length;
  assert.equal(hash(map.source.text),map.source.sha256);assert.equal(map.source.offset_encoding,'unicode_codepoints');
  assert.notEqual(map.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  const ids=new Set(map.graph.nodes.map(n=>n.id)),indegree=new Map([...ids].map(k=>[k,0])),adj=new Map([...ids].map(k=>[k,[]]));
  for(const e of map.graph.edges){assert.ok(ids.has(e.source)&&ids.has(e.target));adj.get(e.source).push(e.target);indegree.set(e.target,indegree.get(e.target)+1);}
  const queue=[...ids].filter(k=>indegree.get(k)===0);let visited=0;
  while(queue.length){const id=queue.pop();visited++;for(const next of adj.get(id)){indegree.set(next,indegree.get(next)-1);if(!indegree.get(next))queue.push(next);}}
  assert.equal(visited,ids.size);
}
assert.equal(maps.size,11);assert.equal(knowledge,943);
const repair=newProofs.filter(p=>p.entry.variant==='explicit_therapeutic_pbs_comparator');assert.equal(repair.length,4);
const outcomes=new Set();let quotes=0;
for(const proof of repair) {
  const old=oldViews.get(JSON.stringify(proof.source_part_key)),view=[...newViews.values()].find(v=>v.projection_proof.role_binding_proof?.id===proof.id);
  assert.ok(old&&view);assert.equal(old.native_key[0],'research-pmc5651799-d577fb3b53bb16a1');
  assert.equal(fp(old.frame),proof.entry.frame_sha256);assert.equal(fp(view.frame),view.projection_proof.view_frame_sha256);
  assert.equal(proof.scope_or_number_changed,false);assert.equal(proof.new_empirical_result,false);
  const reverse=structuredClone(view.frame);reverse.statements[0].roles=reverse.statements[0].roles.filter(r=>r.role!=='comparator');
  for(const alias of proof.aliases){const role=reverse.statements[0].roles.find(r=>r.role===alias.role);role.value=alias.original;}
  reverse.statements[0].roles.sort((a,b)=>a.role.localeCompare(b.role));
  const expected=structuredClone(old.frame);expected.statements[0].roles.sort((a,b)=>a.role.localeCompare(b.role));
  assert.deepEqual(reverse,expected);
  const added=view.frame.statements[0].roles.find(r=>r.role==='comparator');assert.equal(added.value,'pbs vehicle control');
  assert.notEqual(old.frame.statements[0].predicate,'difference not statistically detected');
  const outcome=old.frame.statements[0].roles.find(r=>r.role==='outcome');if(outcome)outcomes.add(outcome.value);
  const e=proof.entry.add_roles[0].evidence,map=maps.get(old.native_key[0]),unit=map.source.units.find(u=>u.id===e.unit_id);
  assert.ok(unit.start<=e.start&&e.end<=unit.end&&unit.end<=map.source.content_end);
  assert.equal(Array.from(map.source.text).slice(e.start,e.end).join(''),e.text);assert.equal(hash(e.text),e.sha256);
  assert.match(e.text,/PBS/);assert.equal(proof.entry.add_roles[0].source_asserts_role,true);quotes++;
  for(const related of proof.complete_related_knowledge)assert.deepEqual(related.knowledge,map.graph.knowledge.find(k=>k.knowledge_id===related.native_key[1]));
}
assert.deepEqual([...outcomes].sort(),['body-weight loss','eae clinical progression','mean maximum disease score'].sort());
for(const view of before.forecast.data.part_views.filter(v=>v.native_key[1]==='K49'&&!v.projection_proof.role_binding_proof))
  assert.deepEqual(newViews.get(JSON.stringify(view.key)),view);
for(const transfer of [main,control]) {
  assert.equal(transfer.data.question,null);assert.equal(transfer.data.held_out_results_used_for_learning,false);
  assert.equal(transfer.data.retrospective_annotation_and_validation_used_results,true);
  const c=upstream(transfer).contract.data.cases;
  for(const folds of Object.values(transfer.data.modes))for(const fold of folds){
    assert.equal(fold.predictions.length,0);assert.equal(fold.rules.length,0);
    for(const id of fold.training_case_ids)assert.notEqual(c.find(v=>v.case_id===id).primary_family,fold.held_out_family);
  }
}
function evaluation(run,id) {
  const bytes=readFileSync(resolve(run.folder,'evaluations',id+'.json'));assert.equal(rawJsonFingerprint(bytes),id);
  const e=JSON.parse(bytes);assert.equal(e.forecast_sha256,rawJsonFingerprint(run.raw));
  assert.equal(e.resubstitution_diagnostic.is_independent_validation,false);assert.equal(e.new_scientific_knowledge_confirmed,false);return e;
}
const evaluated=evaluation(main,report.evaluation_id),oldEvaluated=evaluation(control,report.control_evaluation_id);
assert.equal(oldEvaluated.resubstitution_diagnostic.candidates.length,0);
const candidates=evaluated.resubstitution_diagnostic.candidates;assert.equal(candidates.length,2);
assert.deepEqual(candidates.map(c=>c.receiver_id).sort(),['atrosimab-manifest','tros-manifest']);
for(const candidate of candidates) {
  assert.equal(candidate.deductive_entailment,false);assert.equal(candidate.support_families.length,2);
  const comparator=candidate.receiver.body[0].frame.statements[0].roles.find(r=>r.role==='comparator').value;
  assert.equal(candidate.head.participants.comparator,comparator);
  assert.equal(candidate.head.qualitative_direction,'lower_clinical_burden');
}
assert.ok(Object.values(after.forecast.data.predictions).every(p=>p.length===0));
const html=read('review-v1/report.html').toString();assert.match(html,/<html lang="ru">/);
assert.ok(!/<script|https?:\/\/|(?:src|href)=/i.test(html));assert.match(html,/не два предсказания/);
const result={run_id:main.data.run_id,sources_verified:11,canonical_blocks_verified:943,original_views_preserved:894,
  previous_role_frames_preserved:12,new_source_bound_roles_verified:4,quotes_verified:quotes,
  resubstitution_candidates:2,independent_hypotheses:0,graph_advantage_demonstrated:false,
  verifier_sha256:hash(readFileSync(import.meta.path)),helper_sha256:hash(readFileSync(resolve(dirname(import.meta.path),'raw_json_fingerprint.mjs')))};
writeFileSync(resolve(root,'review-v1/bun-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
