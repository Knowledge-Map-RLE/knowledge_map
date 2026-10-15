// Независимо сверяет научные поля новых операций с неизменёнными частями и исходными фрагментами.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/method-clauses-v1');
const read = p => readFileSync(resolve(root, p)), json = p => JSON.parse(read(p));
const hash = v => createHash('sha256').update(v).digest('hex');
const receipt = json('review-v1/verification.json'), data = json('review-v1/data.json');
for (const [p,h] of Object.entries(receipt.files)) assert.equal(hash(read('review-v1/'+p)), h);
for (const [p,h] of Object.entries(receipt.builders)) assert.equal(hash(readFileSync(p)), h);
assert.equal(hash(read('tests-v2.xml')), receipt.tests_sha256); assert.equal(data.tests,113);
function rawField(bytes, name) {
  const text=bytes.toString('utf8'), match=new RegExp('^  "'+name+'":\\s*','m').exec(text); assert.ok(match);
  const start=match.index+match[0].length; let depth=0, quoted=false, escaped=false;
  for(let i=start;i<text.length;i++) {
    const ch=text[i];
    if(quoted){if(escaped)escaped=false;else if(ch==='\\')escaped=true;else if(ch==='"')quoted=false;continue;}
    if(ch==='"'){quoted=true;continue;}if(ch==='{'||ch==='[')depth++;else if(ch==='}'||ch===']')depth--;
    if(depth===0)return Buffer.from(text.slice(start,i+1));
  } assert.fail('Незавершённое поле JSON');
}
function seal(folder) {
  const raw=read(folder+'/predictions.json'), d=JSON.parse(raw);
  assert.equal(rawJsonFingerprint(raw),json(folder+'/seal.json').prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(raw,'binding')),d.run_id);
  for(const [p,h] of Object.entries(d.binding.implementation))assert.equal(hash(read(folder+'/implementation/'+p)),h);
  for(const name of ['model_calls','target_read','scientific_success','graph_advantage_demonstrated']) assert.equal(d[name],name==='model_calls'?0:false);
  return d;
}
const mf='runs/'+data.run_id, cf='control-runs/'+data.control_run_id, bf='barrier-runs/'+data.barrier_run_id;
const main=seal(mf), control=seal(cf), barrier=seal(bf);
assert.equal(barrier.binding.input_sha256,rawJsonFingerprint(read(mf+'/predictions.json')));
for(const field of ['references','map_hashes','families','context_audit_sha256','model_audit_sha256','origin_audit_sha256','compound_licenses_sha256','implementation','version','limits']) assert.deepEqual(main.binding[field],control.binding[field]);
const metadata=structuredClone(main.binding.metadata);delete metadata.input_audit_file_sha256['method-clauses'];assert.deepEqual(metadata,control.binding.metadata);
assert.equal(control.method_clause_projection,null); assert.equal(main.licensed_parts,894); assert.equal(control.licensed_parts,854);
assert.equal(main.canonical_blocks,943);assert.equal(main.method_clause_projection.added_views,40);
assert.equal(main.method_clause_projection.primary_methods,111);assert.equal(main.method_clause_projection.generic_primary_methods,33);
assert.equal(main.method_clause_projection.counts.retain_native,2);
const audit=json(mf+'/method-clauses.json');assert.equal(audit.entries.length,33);
assert.equal(hash(readFileSync(resolve(import.meta.dir,'../../api/tools/prepare_method_clause_audit.py'))),audit.author_script_sha256);
const inputs=json(mf+'/inputs-manifest.json');assert.deepEqual(inputs,json(cf+'/inputs-manifest.json'));
assert.equal(inputs.sources.length,11);const maps=new Map();let knowledge=0;
for(const e of inputs.sources) {
  const raw=read(mf+'/'+e.map_path), m=JSON.parse(raw);
  assert.equal(hash(raw),e.map_file_sha256);assert.equal(hash(read(cf+'/'+e.map_path)),e.map_file_sha256);
  assert.equal(m.run_id,e.reference.run_id);assert.equal(m.article_id,e.reference.article_id);
  assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  const indegree=new Map(m.graph.nodes.map(n=>[n.id,0])),next=new Map(m.graph.nodes.map(n=>[n.id,[]]));
  for(const edge of m.graph.edges){assert.ok(indegree.has(edge.source)&&indegree.has(edge.target));indegree.set(edge.target,indegree.get(edge.target)+1);next.get(edge.source).push(edge.target);}
  const pending=[...indegree].filter(([,v])=>v===0).map(([k])=>k);let count=0;
  while(pending.length){const id=pending.shift();count++;for(const t of next.get(id)){indegree.set(t,indegree.get(t)-1);if(indegree.get(t)===0)pending.push(t);}}
  assert.equal(count,m.graph.nodes.length);maps.set(m.article_id,m);knowledge+=m.graph.knowledge.length;
}
assert.equal(knowledge,943);
const baseline=new Map(control.part_views.map(v=>[JSON.stringify(v.key),v]));let clauses=0;
for(const v of main.part_views) {
  const old=baseline.get(JSON.stringify(v.key)); if(old){assert.deepEqual(v,old);continue;}
  clauses++;
  const p=v.projection_proof.method_clause_proof, original=baseline.get(JSON.stringify(p.source_part_key));assert.ok(original);
  const restored=structuredClone(v.frame);restored.statements[0].predicate=p.original_predicate;assert.deepEqual(restored,original.frame);
  assert.equal(p.participant_or_constraint_removed,false);assert.equal(p.constraints_inherited_from_complete_parent_not_reassigned,true);
  assert.equal(p.operation_is_complete_parent_equivalent,false);assert.equal(p.new_empirical_result,false);
  assert.equal(v.projection_proof.origin.origin,'primary_method');assert.equal(v.frame.action_status,'performed');
  assert.ok(v.projection_proof.foundation.includes('not an identity'));
  const map=maps.get(v.native_key[0]), k=map.graph.knowledge.find(k=>k.knowledge_id===v.native_key[1]);
  assert.deepEqual(v.projection_proof.complete_native_knowledge,k);
  const e=p.operation.evidence, u=map.source.units.find(u=>u.id===e.unit_id);
  assert.ok(original.projection_proof.selected_provenance.unit_ids.includes(e.unit_id));
  assert.ok(u.start<=e.start&&e.end<=u.end&&u.end<=map.source.content_end);
  assert.equal(Array.from(map.source.text).slice(e.start,e.end).join(''),e.text);assert.equal(hash(Buffer.from(e.text)),e.sha256);
}
assert.equal(clauses,40);
for(const d of [main,control])for(const p of Object.values(d.predictions))assert.equal(p.length,0);
const collisions=barrier.modes.graph.policies.predicate_topology.collision_groups;
assert.equal(collisions.length,1);assert.equal(collisions[0].scientific_equivalence,false);
assert.equal(collisions[0].primary_families.length,2);
for(const key of ['exact','source_labels','without_context','relational_structure']) assert.equal(barrier.modes.graph.policies[key].multi_family_collision_groups,0);
const html=read('review-v1/report.html').toString('utf8');assert.ok(html.includes('lang="ru"'));
assert.ok(!/<script|https?:\/\/|<iframe|<link/i.test(html));assert.equal((html.match(/<tr>/g)||[]).length,4);
const proof={run_id:main.run_id,control_run_id:control.run_id,barrier_run_id:barrier.run_id,sources:11,knowledge:943,
  method_clauses_verified:clauses,coarse_multi_family_forms:1,valid_rules:0,new_predictions:0,graph_advantage_demonstrated:false,
  model_calls:0,verifier_sha256:hash(readFileSync(import.meta.filename)),helper_sha256:hash(readFileSync(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
writeFileSync(resolve(root,'review-v1/bun-verification.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));
