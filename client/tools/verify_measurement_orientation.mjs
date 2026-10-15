// Определения шкал, неизменность условий и общие ролевые структуры проверяются независимо.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';

const root=resolve(import.meta.dir,'../../eval/whole_map_forecast/measurement-orientation-v1'),review=resolve(root,'review-v2');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function field(bytes,name){
  const s=bytes.toString(),m=new RegExp('^  "'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;if(!depth)return Buffer.from(s.slice(start,i+1));}
  assert.fail('Незавершённый JSON');
}
function seal(folder){const bytes=read(resolve(folder,'predictions.json')),data=JSON.parse(bytes),p=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),p.prediction_sha256);assert.equal(rawJsonFingerprint(field(bytes,'binding')),data.run_id);
  for(const[f,d]of Object.entries(data.binding.implementation))assert.equal(hash(read(resolve(folder,'implementation',f))),d);
  assert.equal(data.model_calls,0);return{bytes,data};}
const receipt=json(resolve(review,'verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_measurement_orientation.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const tests=new Set();let executions=0;
for(const r of receipt.tests){const bytes=read(r.path);assert.equal(hash(bytes),r.sha256);const d=new JSDOM(bytes.toString(),{contentType:'text/xml'}).window.document;
  let count=0;for(const s of d.querySelectorAll('testsuite')){count+=Number(s.getAttribute('tests'));for(const k of ['errors','failures','skipped'])assert.equal(Number(s.getAttribute(k)),0);}
  assert.equal(count,r.tests);executions+=count;for(const t of d.querySelectorAll('testcase'))tests.add(JSON.stringify([t.getAttribute('classname'),t.getAttribute('name')]));}
assert.equal(tests.size,79);assert.equal(tests.size,receipt.tests_unique);assert.equal(executions,105);
const current=seal(receipt.run_path),previous=seal(receipt.previous_path),contract=seal(receipt.applicability_path),data=current.data;
assert.equal(rawJsonFingerprint(previous.bytes),data.binding.previous_sha256);
const pp=json(resolve(receipt.previous_path,'input-corpus.json')),baseline=seal(pp.baseline),bp=json(resolve(pp.baseline,'input-corpus.json'));
const source=seal(bp.snapshot),frozen=source.data;
assert.equal(rawJsonFingerprint(source.bytes),data.binding.source_sha256);assert.equal(rawJsonFingerprint(source.bytes),contract.data.binding.input_sha256);
assert.deepEqual(data.binding.map_hashes,frozen.binding.map_hashes);
assert.equal(rawJsonFingerprint(read(resolve(bp.snapshot,'origin-audit.json'))),data.binding.origin_audit_sha256);
const auditBytes=read(resolve(receipt.run_path,'audit.json')),audit=JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes),data.binding.audit_sha256);assert.equal(audit.source_sha256,data.binding.source_sha256);
const maps=new Map(),native=new Map();let canonical=0,statements=0,uses=0;
for(const e of json(resolve(bp.snapshot,'inputs-manifest.json')).sources){const bytes=read(resolve(bp.snapshot,e.map_path));assert.equal(hash(bytes),e.map_file_sha256);
  if(e.coverage_path)assert.equal(hash(read(resolve(bp.snapshot,e.coverage_path))),e.coverage_sha256);
  const m=JSON.parse(bytes);maps.set(m.article_id,m);assert.equal(m.graph.schema_version,6);assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  const ids=new Set(m.graph.nodes.map(n=>n.id)),degrees=new Map([...ids].map(id=>[id,0])),adjacent=new Map([...ids].map(id=>[id,[]]));
  for(const edge of m.graph.edges){assert.ok(ids.has(edge.source)&&ids.has(edge.target));degrees.set(edge.target,degrees.get(edge.target)+1);adjacent.get(edge.source).push(edge.target);}
  const queue=[...ids].filter(id=>degrees.get(id)===0);let visits=0;while(queue.length){const id=queue.pop();visits++;for(const t of adjacent.get(id)){degrees.set(t,degrees.get(t)-1);if(!degrees.get(t))queue.push(t);}}
  assert.equal(visits,ids.size);const text=Array.from(m.source.text),units=new Map(m.source.units.map(u=>[u.id,u]));
  for(const k of m.graph.knowledge){canonical++;native.set(JSON.stringify([m.article_id,k.knowledge_id]),k);
    for(const s of k.semantic_frame.statements){statements++;for(const uid of s.provenance.unit_ids){const u=units.get(uid);assert.ok(u);assert.equal(text.slice(u.start,u.end).join(''),u.text);uses++;}}}}
assert.equal(maps.size,11);assert.equal(canonical,943);assert.equal(statements,1897);
assert.equal(data.input_coverage.length,canonical);assert.equal(data.input_parts,910);assert.equal(data.oriented_parts,915);
const views=new Map(frozen.part_views.map(v=>[JSON.stringify(v.key),v])),originAudit=json(resolve(bp.snapshot,'origin-audit.json'));
const families=new Map(originAudit.sources.map(s=>[s.article_id,s.dataset_family]));let quotes=0;
assert.equal(data.orientation_views.length,5);assert.equal(data.orientation_proofs.length,3);
const proofById=new Map(data.orientation_proofs.map(p=>[p.id,p]));
for(const p of data.orientation_proofs){const e=p.entry,c=p.source_case;assert.deepEqual(c,contract.data.cases.find(c=>c.case_id===p.case_id));
  assert.equal(p.direction,'lower');assert.equal(e.orientation,'higher_is_worse');assert.equal(e.effect,'improved');assert.equal(e.property_label,'reported EAE clinical burden');
  assert.equal(p.participants_or_context_changed,false);assert.equal(p.numerical_attributes_changed,false);assert.equal(p.complete_fact_equivalence,false);
  assert.equal(p.scale_equivalence_asserted,false);assert.equal(p.effect_size_converted,false);assert.equal(p.new_observation,false);
  const points=e.anchors.map(a=>Number(a.value));assert.ok(points.every(Number.isFinite));assert.deepEqual(points,[...new Set(points)].sort((a,b)=>a-b));
  for(const a of e.anchors){assert.ok(a.source_fragment.startsWith(a.value+','));assert.ok(e.order_evidence.some(q=>q.text.includes(a.source_fragment)));}
  const m=maps.get(c.article_id),text=Array.from(m.source.text),units=new Map(m.source.units.map(u=>[u.id,u]));
  const allowed=new Set(['method','measurement','result'].flatMap(f=>native.get(JSON.stringify(c[f].native_key)).semantic_frame.statements.flatMap(s=>s.provenance.unit_ids)));
  for(const q of [...e.order_evidence,...e.bridge_evidence,...e.scale_caveat_evidence]){const u=units.get(q.unit_id);assert.ok(allowed.has(q.unit_id));
    assert.ok(u.start<=q.start&&q.end<=u.end);assert.equal(text.slice(q.start,q.end).join(''),q.text);assert.equal(hash(Buffer.from(q.text)),q.sha256);quotes++;}
  if(p.case_id.startsWith('tros')){assert.equal(points.at(-1),6);assert.equal(e.scale_caveat_evidence.length,1);}else assert.equal(points.at(-1),5);
}
for(const v of data.orientation_views){const p=v.projection_proof,o=p.measurement_orientation,old=views.get(JSON.stringify(o.source_key));assert.ok(old);
  assert.deepEqual(o.complete_input_frame,old.frame);assert.deepEqual(p.complete_native_knowledge,old.projection_proof.complete_native_knowledge);
  const s=v.frame.statements[0],before=old.frame.statements[0];assert.deepEqual(s.scope,before.scope);assert.deepEqual(s.attributes,before.attributes);assert.equal(s.negated,before.negated);
  assert.deepEqual(s.roles.filter(r=>r.role!=='outcome'),before.roles.filter(r=>r.role!=='outcome'));
  assert.equal(s.roles.find(r=>r.role==='outcome').value,'reported EAE clinical burden');
  assert.equal(s.predicate,o.kind==='result'?'reduced after intervention':before.predicate);
  assert.equal(o.full_fact_equivalence,false);assert.equal(o.scale_equivalence,false);
  for(const id of p.orientation_evidence_ids)assert.ok(proofById.has(id));
  for(const key of p.source_part_keys)assert.ok(views.has(JSON.stringify(key)));
  assert.equal(rawJsonFingerprint(JSON.stringify(v.frame)),p.view_frame_sha256);views.set(JSON.stringify(v.key),v);}
assert.equal(views.size,915);assert.ok(data.orientation_views.some(v=>v.projection_proof.orientation_evidence_ids.length===2));
// Порядок средних не сохраняется при нелинейной, но строго возрастающей перекодировке.
assert.ok((0+5)/2<(3+3)/2);assert.ok((0+100)/2>(3+3)/2);
function structuralKey(rule){const n=rule.body.length;assert.equal(n,2);const variants=[];
  for(const order of [[0,1],[1,0]]){const names=new Map();const alpha=frame=>{const f=structuredClone(frame);for(const s of f.statements){s.roles.sort((a,b)=>a.role<b.role?-1:a.role>b.role?1:0);
      for(const r of s.roles)if('variable'in r.value){const original=r.value.variable;if(!names.has(original))names.set(original,'$'+names.size);r.value={variable:names.get(original)};}
      s.scope={diagnostic_guard_placeholder:true};s.attributes=[];delete s.attribute_types;}return f;};
    const body=order.map(i=>alpha(rule.body[i])),head=alpha(rule.head),inverse=new Map(order.map((old,i)=>[old,i]));
    const shape={body,head,internal_edges:rule.internal_edges.map(([a,b])=>[inverse.get(a),inverse.get(b)]).sort()};
    variants.push([rawJsonFingerprint(JSON.stringify(shape)),shape]);}return variants.sort((a,b)=>a[0].localeCompare(b[0]))[0];}
const groups=data.policies.source_bound_measurement_orientation.graph.guard_barriers;
assert.equal(groups.length,2);const outcomeBindings=new Set();let sourceExamples=0,unboundBodyWeight=false;
for(const group of groups){const recovered=new Set();assert.equal(group.valid_rule,false);assert.equal(group.prediction_created,false);assert.equal(group.constraints_removed_for_inference,false);
  for(const variant of group.variants){const [id,shape]=structuralKey(variant);assert.equal(id,group.id);assert.deepEqual(shape,group.structure);
    for(const e of variant.examples){const head=views.get(JSON.stringify(e.head));assert.ok(head);assert.equal(head.projection_proof.origin.origin,'primary_result');
      recovered.add(families.get(head.native_key[0]));for(const key of e.body){assert.ok(views.has(JSON.stringify(key)));
        const body=views.get(JSON.stringify(key));if('constant'in group.structure.head.statements[0].roles.find(r=>r.role==='outcome').value
          &&body.frame.statements[0].roles.some(r=>r.role==='outcome'&&r.value==='body weight'))unboundBodyWeight=true;}sourceExamples++;}}
  assert.deepEqual([...recovered].sort(),group.primary_families);assert.equal(recovered.size,2);
  const outcome=group.structure.head.statements[0].roles.find(r=>r.role==='outcome').value;
  if('variable'in outcome){const measured=group.structure.body.find(f=>f.statements[0].predicate==='measure clinical course');
    assert.deepEqual(outcome,measured.statements[0].roles.find(r=>r.role==='outcome').value);outcomeBindings.add('bound');}else outcomeBindings.add('constant');}
assert.deepEqual([...outcomeBindings].sort(),['bound','constant']);
assert.equal(unboundBodyWeight,true);
for(const [policy,modes]of Object.entries(data.policies))for(const [mode,row]of Object.entries(modes)){assert.equal(row.predictions.length,0);assert.equal(row.rules?.length||0,0);
  if(policy==='before_measurement_orientation'&&row.learning)assert.deepEqual(row.learning,previous.data.policies.source_bound_interval_summary[mode].learning);}
assert.equal(data.graph_advantage_demonstrated,false);assert.equal(data.scientific_success,false);assert.equal(data.target_read,false);
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;assert.equal(doc.documentElement.lang,'ru');assert.equal(doc.querySelectorAll('table').length,2);
assert.equal(doc.querySelectorAll('details').length,5);assert.equal(doc.querySelectorAll('[src],link[href],script').length,0);assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:data.run_id,tests_unique:tests.size,test_executions:executions,sources:maps.size,canonical_blocks:canonical,semantic_statements:statements,
  source_provenance_uses:uses,exact_quote_uses:quotes,orientation_views:5,orientation_cases:3,primary_families:2,
  structural_representations:2,source_structural_examples:sourceExamples,baseline_learning_reproduced:true,
  quantity_bound_prototypes:1,unbound_prototypes_rejected_for_transfer:1,
  new_empirical_forecasts:0,graph_advantage_demonstrated:false,model_calls:0,visual_review_claimed:false,
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const file=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');if(existsSync(file))assert.deepEqual(read(file),bytes);else writeFileSync(file,bytes,{flag:'wx'});
console.log(JSON.stringify(proof));
