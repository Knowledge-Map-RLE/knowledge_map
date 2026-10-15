// Независимая проверка ролей, источников, неизменённых научных полей и честного нулевого прогноза.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/operation-role-bindings-v1');
const read = p => readFileSync(resolve(root, p)), json = p => JSON.parse(read(p));
const hash = v => createHash('sha256').update(v).digest('hex');
const receipt = json('review-v1/verification.json'), data = json('review-v1/data.json');
for(const [p,h] of Object.entries(receipt.files)) assert.equal(hash(read('review-v1/'+p)),h);
for(const [p,h] of Object.entries(receipt.builders)) assert.equal(hash(readFileSync(p)),h);
assert.equal(hash(read('tests-v3.xml')),receipt.tests_sha256); assert.equal(data.tests,149);
function rawField(bytes,name) {
  const text=bytes.toString('utf8'), match=new RegExp('^  "'+name+'":\\s*','m').exec(text); assert.ok(match);
  const start=match.index+match[0].length; let depth=0, quoted=false, escaped=false;
  for(let i=start;i<text.length;i++) {
    const ch=text[i];
    if(quoted){if(escaped)escaped=false;else if(ch==='\\')escaped=true;else if(ch==='"')quoted=false;continue;}
    if(ch==='"'){quoted=true;continue;}if(ch==='{'||ch==='[')depth++;else if(ch==='}'||ch===']')depth--;
    if(depth===0)return Buffer.from(text.slice(start,i+1));
  }assert.fail('Незавершённое поле');
}
function seal(folder) {
  const raw=read(folder+'/predictions.json'), d=JSON.parse(raw);
  assert.equal(rawJsonFingerprint(raw),json(folder+'/seal.json').prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(raw,'binding')),d.run_id);
  for(const [p,h] of Object.entries(d.binding.implementation)) assert.equal(hash(read(folder+'/implementation/'+p)),h);
  for(const flag of ['target_read','scientific_success','graph_advantage_demonstrated'])assert.equal(d[flag],false);
  assert.equal(d.model_calls,0);return d;
}
const mf='runs/'+data.run_id, cf='control-runs/'+data.control_run_id;
const bf='barrier-runs/'+data.barrier_run_id, cbf='control-barrier-runs/'+data.control_barrier_run_id;
const main=seal(mf),control=seal(cf),barrier=seal(bf),oldbarrier=seal(cbf);
assert.equal(barrier.binding.input_sha256,rawJsonFingerprint(read(mf+'/predictions.json')));
assert.equal(oldbarrier.binding.input_sha256,rawJsonFingerprint(read(cf+'/predictions.json')));
assert.deepEqual(barrier.binding.implementation,oldbarrier.binding.implementation);
for(const field of ['references','map_hashes','families','context_audit_sha256','model_audit_sha256',
  'origin_audit_sha256','compound_licenses_sha256','method_clauses_sha256','implementation','version','limits']) {
  assert.deepEqual(main.binding[field],control.binding[field]);
}
const metadata=structuredClone(main.binding.metadata);delete metadata.input_audit_file_sha256['role-bindings'];
assert.deepEqual(metadata,control.binding.metadata);
assert.deepEqual(main.method_clause_projection,control.method_clause_projection);
assert.equal(control.operation_role_bindings,null);
assert.equal(main.licensed_parts,906);assert.equal(control.licensed_parts,894);assert.equal(main.canonical_blocks,943);
const projection=main.operation_role_bindings,audit=json(mf+'/role-bindings.json');
assert.equal(projection.added_views,12);assert.equal(projection.profiles.length,894);assert.equal(audit.entries.length,12);
assert.equal(hash(readFileSync(resolve(import.meta.dir,'../../api/tools/prepare_operation_role_bindings.py'))),audit.author_script_sha256);
assert.equal(audit.model_calls,0);assert.equal(audit.expert_validated,false);
const inputs=json(mf+'/inputs-manifest.json');assert.deepEqual(inputs,json(cf+'/inputs-manifest.json'));
assert.equal(inputs.sources.length,11);const maps=new Map();let knowledge=0;
for(const e of inputs.sources) {
  const raw=read(mf+'/'+e.map_path),m=JSON.parse(raw);
  assert.equal(hash(raw),e.map_file_sha256);assert.equal(hash(read(cf+'/'+e.map_path)),e.map_file_sha256);
  assert.equal(m.run_id,e.reference.run_id);assert.equal(m.article_id,e.reference.article_id);
  assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);assert.equal(m.source.offset_encoding,'unicode_codepoints');
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  const indegree=new Map(m.graph.nodes.map(n=>[n.id,0])),next=new Map(m.graph.nodes.map(n=>[n.id,[]]));
  for(const edge of m.graph.edges){assert.ok(indegree.has(edge.source)&&indegree.has(edge.target));indegree.set(edge.target,indegree.get(edge.target)+1);next.get(edge.source).push(edge.target);}
  const pending=[...indegree].filter(([,v])=>v===0).map(([k])=>k);let count=0;
  while(pending.length){const id=pending.shift();count++;for(const t of next.get(id)){indegree.set(t,indegree.get(t)-1);if(indegree.get(t)===0)pending.push(t);}}
  assert.equal(count,m.graph.nodes.length);maps.set(m.article_id,m);knowledge+=m.graph.knowledge.length;
}
assert.equal(knowledge,943);
const baseline=new Map(control.part_views.map(v=>[JSON.stringify(v.key),v]));let additions=0,evidenceCount=0;
for(const v of main.part_views) {
  const existing=baseline.get(JSON.stringify(v.key));if(existing){assert.deepEqual(v,existing);continue;}
  additions++;
  const p=v.projection_proof.role_binding_proof,e=p.entry,old=baseline.get(JSON.stringify(p.source_part_key));assert.ok(old);
  assert.ok(audit.entries.some(entry=>JSON.stringify(entry)===JSON.stringify(e)));
  assert.equal(p.source_frame_sha256,old.projection_proof.view_frame_sha256);
  for(const flag of ['scope_or_number_changed','experiments_declared_equivalent','participant_groups_merged','new_empirical_result'])assert.equal(p[flag],false);
  assert.equal(p.complete_parent_retained,true);assert.equal(p.source_interpretation_requires_expert_review,true);
  assert.deepEqual(v.projection_proof.complete_native_knowledge,old.projection_proof.complete_native_knowledge);
  const map=maps.get(v.native_key[0]),native=map.graph.knowledge.find(k=>k.knowledge_id===v.native_key[1]);
  assert.deepEqual(native,v.projection_proof.complete_native_knowledge);
  const allowedUnits=new Set();
  for(const related of p.complete_related_knowledge) {
    assert.equal(related.native_key[0],map.article_id);
    assert.deepEqual(related.knowledge,map.graph.knowledge.find(k=>k.knowledge_id===related.native_key[1]));
    for(const s of related.knowledge.semantic_frame.statements)for(const id of s.provenance.unit_ids)allowedUnits.add(id);
  }
  const restored=structuredClone(v.frame),statement=restored.statements[0];
  for(const a of p.aliases){const r=statement.roles.find(r=>r.role===a.role);assert.equal(r.value,a.canonical);r.value=a.original;}
  for(const a of e.add_roles) {
    const role=statement.roles.find(r=>r.role===a.role);assert.ok(role);assert.equal(a.source_asserts_role,true);
    if(a.copy_from) {
      const from=baseline.get(JSON.stringify(a.copy_from.part_key));assert.ok(from);assert.equal(from.run_id,v.run_id);
      assert.equal(from.native_key[0],v.native_key[0]);assert.equal(a.copy_from.frame_sha256,from.projection_proof.view_frame_sha256);
      const sourceRoles=from.frame.statements.flatMap(s=>s.roles).filter(r=>r.role===a.copy_from.role);assert.equal(sourceRoles.length,1);
      assert.deepEqual(role,{...sourceRoles[0],role:a.role});
      if(a.role==='population'){assert.equal(a.source_asserts_subprotocol_group,true);assert.ok(e.binding_group);}
    }else assert.deepEqual(role,{role:a.role,value:a.value,reference_kind:'concept'});
    statement.roles=statement.roles.filter(r=>r.role!==a.role);
  }
  for(const a of e.rename_roles) {
    assert.equal(a.from,'model');assert.equal(a.to,'challenge');assert.equal(a.biological_induced_disease_model,true);
    statement.roles.find(r=>r.role===a.to).role=a.from;
  }
  const expected=structuredClone(old.frame);
  for(const f of [restored,expected])f.statements[0].roles.sort((a,b)=>a.role.localeCompare(b.role));
  assert.deepEqual(restored,expected);
  for(const change of [...e.add_roles,...e.rename_roles]) {
    const quote=change.evidence,u=map.source.units.find(u=>u.id===quote.unit_id);
    assert.ok(allowedUnits.has(quote.unit_id)&&u.start<=quote.start&&quote.end<=u.end&&u.end<=map.source.content_end);
    assert.equal(Array.from(map.source.text).slice(quote.start,quote.end).join(''),quote.text);
    assert.equal(hash(Buffer.from(quote.text)),quote.sha256);evidenceCount++;
  }
}
assert.equal(additions,12);
for(const d of [main,control])for(const mode of Object.keys(d.predictions))assert.equal(d.predictions[mode].length,0);
for(const policy of ['exact','source_labels','without_context'])assert.equal(barrier.modes.graph.policies[policy].multi_family_collision_groups,0);
assert.equal(barrier.modes.graph.policies.relational_structure.multi_family_collision_groups,1);
assert.equal(oldbarrier.modes.graph.policies.relational_structure.multi_family_collision_groups,0);
assert.equal(barrier.modes.source_neighborhood_without_dependencies.policies.relational_structure.multi_family_collision_groups,1);
const collision=barrier.modes.graph.policies.relational_structure.collision_groups[0];assert.equal(collision.primary_families.length,2);
assert.equal(collision.valid_inference,false);assert.equal(collision.scientific_equivalence,false);
const html=read('review-v1/report.html').toString('utf8');assert.ok(html.includes('lang="ru"'));
assert.ok(!/<script|https?:\/\/|<iframe|<link/i.test(html));assert.equal((html.match(/<tr>/g)||[]).length,10);
const proof={run_id:main.run_id,control_run_id:control.run_id,sources:11,knowledge:943,role_views_verified:additions,
  evidence_verified:evidenceCount,original_views_preserved:894,coarse_multi_family_forms:1,valid_rules:0,new_predictions:0,
  graph_advantage_demonstrated:false,model_calls:0,verifier_sha256:hash(readFileSync(import.meta.filename)),
  helper_sha256:hash(readFileSync(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
writeFileSync(resolve(root,'review-v1/bun-verification.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));
