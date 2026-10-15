// Независимая сверка источников, функционального смысла и связанных переменных.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';

const review=resolve(import.meta.dir,'../../eval/whole_map_forecast/functional-target-guard-v1/review-v2');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function valueEnd(s,start){
  let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(!depth)return i+1;}
  assert.fail('Незавершённый объект JSON');
}
function field(bytes,name){const s=bytes.toString(),m=new RegExp('^  "'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;return Buffer.from(s.slice(start,valueEnd(s,start)));}
function arrayItems(bytes){const s=bytes.toString();assert.equal(s.trim()[0],'[');const out=[];let i=1;
  while(i<s.length){while(/\s|,/.test(s[i]))i++;if(s[i]===']')break;const end=valueEnd(s,i);out.push(Buffer.from(s.slice(i,end)));i=end;}return out;}
function seal(folder){const bytes=read(resolve(folder,'predictions.json')),data=JSON.parse(bytes),p=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),p.prediction_sha256);assert.equal(rawJsonFingerprint(field(bytes,'binding')),data.run_id);
  for(const[f,d]of Object.entries(data.binding.implementation))assert.equal(hash(read(resolve(folder,'implementation',f))),d);
  assert.equal(data.model_calls,0);return{bytes,data};}
const receipt=json(resolve(review,'verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_functional_target_guard.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const tests=new Set();let executions=0;
for(const r of receipt.tests){const bytes=read(r.path);assert.equal(hash(bytes),r.sha256);
  const doc=new JSDOM(bytes.toString(),{contentType:'text/xml'}).window.document;let count=0;
  for(const s of doc.querySelectorAll('testsuite')){count+=Number(s.getAttribute('tests'));
    for(const k of ['errors','failures','skipped'])assert.equal(Number(s.getAttribute(k)),0);}
  assert.equal(count,r.tests);executions+=count;
  for(const t of doc.querySelectorAll('testcase'))tests.add(JSON.stringify([t.getAttribute('classname'),t.getAttribute('name')]));}
assert.equal(tests.size,52);assert.equal(tests.size,receipt.tests_unique);
const current=seal(receipt.run_path),orientation=seal(receipt.orientation_path),r=current.data;
assert.equal(r.version,'source-bound-functional-target-guard-2');
assert.equal(rawJsonFingerprint(orientation.bytes),r.binding.orientation_sha256);
const op=json(resolve(receipt.orientation_path,'input-corpus.json')),interval=seal(op.previous),ip=json(resolve(op.previous,'input-corpus.json'));
const typed=seal(ip.baseline),tp=json(resolve(ip.baseline,'input-corpus.json')),source=seal(tp.snapshot),contract=seal(op.applicability);
assert.equal(rawJsonFingerprint(interval.bytes),orientation.data.binding.previous_sha256);
assert.equal(rawJsonFingerprint(typed.bytes),interval.data.binding.baseline_sha256);
assert.equal(rawJsonFingerprint(source.bytes),r.binding.source_sha256);
assert.equal(rawJsonFingerprint(source.bytes),contract.data.binding.input_sha256);
assert.deepEqual(r.binding.map_hashes,source.data.binding.map_hashes);
assert.equal(rawJsonFingerprint(field(contract.bytes,'cases')),r.binding.cases_sha256);
const auditBytes=read(resolve(receipt.run_path,'audit.json')),audit=JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes),r.binding.audit_sha256);assert.equal(audit.source_sha256,r.binding.source_sha256);
assert.deepEqual(audit.map_hashes,r.binding.map_hashes);assert.equal(audit.expert_validated,false);
const maps=new Map(),native=new Map();let canonical=0,statements=0,uses=0;
for(const e of json(resolve(tp.snapshot,'inputs-manifest.json')).sources){const bytes=read(resolve(tp.snapshot,e.map_path));assert.equal(hash(bytes),e.map_file_sha256);
  if(e.coverage_path)assert.equal(hash(read(resolve(tp.snapshot,e.coverage_path))),e.coverage_sha256);
  const m=JSON.parse(bytes);maps.set(m.article_id,m);assert.equal(m.graph.schema_version,6);assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  const ids=new Set(m.graph.nodes.map(n=>n.id)),degrees=new Map([...ids].map(id=>[id,0])),adj=new Map([...ids].map(id=>[id,[]]));
  for(const edge of m.graph.edges){assert.ok(ids.has(edge.source)&&ids.has(edge.target));degrees.set(edge.target,degrees.get(edge.target)+1);adj.get(edge.source).push(edge.target);}
  const queue=[...ids].filter(id=>!degrees.get(id));let visits=0;
  while(queue.length){const id=queue.pop();visits++;for(const t of adj.get(id)){degrees.set(t,degrees.get(t)-1);if(!degrees.get(t))queue.push(t);}}
  assert.equal(visits,ids.size);const text=Array.from(m.source.text),units=new Map(m.source.units.map(u=>[u.id,u]));
  for(const k of m.graph.knowledge){canonical++;native.set(JSON.stringify([m.article_id,k.knowledge_id]),k);
    for(const s of k.semantic_frame.statements){statements++;for(const uid of s.provenance.unit_ids){const u=units.get(uid);assert.ok(u);assert.equal(text.slice(u.start,u.end).join(''),u.text);uses++;}}}}
assert.equal(maps.size,11);assert.equal(canonical,943);assert.equal(statements,1897);assert.equal(r.input_parts,915);
assert.equal(r.canonical_blocks,canonical);assert.equal(r.semantic_statements,statements);
const domain='human TNFR1 extracellular binding domain';let quoteCount=0;
const certificateById=new Map();
for(const bytes of arrayItems(field(current.bytes,'functional_certificates'))){const c=JSON.parse(bytes);
  assert.equal(rawJsonFingerprint(bytes.toString().replace(/,\s*"id"\s*:\s*"[a-f0-9]{64}"\s*}$/, '}')),c.id);
  certificateById.set(c.id,c);const m=maps.get(c.article_id),entry=audit.entries.find(e=>e.article_id===c.article_id);
  assert.ok(m&&entry);assert.equal(entry.run_id,m.run_id);assert.equal(entry.source_sha256,m.source.sha256);
  assert.deepEqual(c.functional_frame,entry.functional_frame);assert.deepEqual(c.evidence,entry.evidence);assert.deepEqual(c.case_ids,entry.case_ids);
  const text=Array.from(m.source.text),units=new Map(m.source.units.map(u=>[u.id,u]));
  for(const parent of c.full_native_parents)assert.deepEqual(parent,native.get(JSON.stringify([c.article_id,parent.knowledge_id])));
  const byKind=new Map();
  for(const e of c.evidence){const parent=native.get(JSON.stringify([c.article_id,e.knowledge_id])),q=e.quote,u=units.get(q.unit_id);
    assert.ok(parent.semantic_frame.statements.flatMap(s=>s.provenance.unit_ids).includes(q.unit_id));
    assert.ok(u.start<=q.start&&q.end<=u.end&&q.end<=m.source.content_end);
    assert.equal(text.slice(q.start,q.end).join(''),q.text);assert.equal(hash(Buffer.from(q.text)),q.sha256);quoteCount++;
    if(!byKind.has(e.kind))byKind.set(e.kind,[]);byKind.get(e.kind).push(q.text);}
  for(const kind of ['binding','inhibition','model_domain'])assert.ok(byKind.get(kind)?.length);
  assert.equal(c.required_target_domain,domain);assert.equal(entry.model_target_domain,domain);
  const atom=c.functional_frame.statements[0],roles=Object.fromEntries(atom.roles.map(p=>[p.role,p.value]));
  assert.equal(c.functional_frame.kind,'state');assert.equal(c.functional_frame.action_status,null);assert.equal(c.functional_frame.logic,'single');
  assert.equal(c.functional_frame.statements.length,1);assert.equal(atom.negated,false);assert.deepEqual(atom.attributes,[]);
  assert.equal(roles.intervention,c.intervention);assert.equal(atom.scope.study_group,c.article_id);
  assert.deepEqual(atom.scope.conditions,byKind.get('inhibition'));assert.equal(atom.scope.quantifier,null);
  assert.equal(atom.scope.modality,'reported source claim');assert.equal(atom.scope.time,'reported functional context; no clinical time window inferred');
  if(entry.agent_alias==='TROS'){
    assert.equal(atom.predicate,'reported pathway inhibition');assert.equal(roles.target,'human TNFR1');assert.equal(roles.ligand,'tumor necrosis factor alpha');
    assert.equal(roles.systems,'in vitro; ex vivo; in vivo in partially humanized mice');assert.equal(c.functional_origin,'cited_or_prior_report');
    assert.ok(byKind.get('inhibition').some(s=>s.includes('inhibits the TNF/hTNFR1 pathway')));
    assert.ok(byKind.get('model_domain').some(s=>s.includes('expressing hTNFR1 in a mouse TNFR1-knockout background')));
  }else{
    assert.equal(entry.agent_alias,'Atrosimab');assert.equal(atom.predicate,'reported inhibition of stimulated release');
    assert.equal(roles.stimulus,'tumor necrosis factor alpha');assert.equal(roles.outcome,'interleukin 8 release');assert.equal(roles['assay population'],'HT1080 cells');
    assert.equal('target' in roles,false);assert.equal(c.functional_origin,'own_report_with_unread_supplement');
    assert.ok(byKind.get('inhibition').some(s=>s.includes('dose-dependent inhibition of the TNF-induced IL-8 release')));
    assert.ok(byKind.get('model_domain').some(s=>s.includes('extracellular domains of human TNFR1')&&s.includes('intracellular part of mouse TNFR1')));
  }
  const expectedParents=c.evidence.filter(e=>e.kind==='inhibition').map(e=>native.get(JSON.stringify([c.article_id,e.knowledge_id])));
  assert.deepEqual(c.original_functional_source_attributes,expectedParents.map(p=>({knowledge_id:p.knowledge_id,statements:p.semantic_frame.statements})));
  assert.equal(c.structural_target_compatibility_supported,true);assert.equal(c.source_binding_and_inhibition_are_distinct,true);
  for(const k of ['in_vivo_target_engagement_established','brain_delivery_established','tnfr2_functional_preservation_established',
    'pure_antagonism_all_doses_established','clinical_efficacy_inferred','mechanism_from_clinical_efficacy_inferred','expert_validated'])assert.equal(c[k],false);
  assert.equal(c.extra_primary_clinical_replications,0);
}
assert.equal(certificateById.size,2);assert.equal(quoteCount,7);
// Контрмодели: одинаковое связывание совместимо и с отсутствием, и с наличием ингибирования.
const worlds=[{binds:true,inhibits:false},{binds:true,inhibits:true}];assert.ok(worlds.every(w=>w.binds));assert.ok(worlds.some(w=>!w.inhibits));
const p=r.guarded_prototype;assert.equal(p.body.length,3);assert.equal(p.primary_families.length,2);
const guard=p.body[0].statements[0],head=p.head.statements[0],gr=Object.fromEntries(guard.roles.map(x=>[x.role,x.value]));
const hr=Object.fromEntries(head.roles.map(x=>[x.role,x.value]));assert.equal(guard.predicate,'reported inhibitory function and model binding domain compatibility');
assert.deepEqual(gr['required target domain'],{constant:domain});assert.deepEqual(gr.intervention,hr.intervention);assert.deepEqual(gr.population,hr.population);
const original=orientation.data.policies.source_bound_measurement_orientation.graph.guard_barriers.find(g=>g.id===p.original_quantity_bound_prototype_id);
assert.ok(original);assert.deepEqual(p.body.slice(1),original.structure.body);assert.deepEqual(p.head,original.structure.head);
assert.deepEqual(p.source_variants_with_all_constraints,original.variants);assert.deepEqual(p.primary_families,original.primary_families);
const measured=p.body.find(b=>b.statements[0].predicate==='measure clinical course').statements[0];
assert.ok('variable'in hr.outcome);assert.deepEqual(hr.outcome,measured.roles.find(x=>x.role==='outcome').value);
for(const[cid,id]of Object.entries(p.certificates)){const c=certificateById.get(id);assert.ok(c&&c.case_ids.includes(cid));
  const sourceCase=contract.data.cases.find(x=>x.case_id===cid);assert.equal(c.article_id,sourceCase.article_id);
  const roles=Object.fromEntries(sourceCase.method.frame.statements[0].roles.map(x=>[x.role,x.value]));
  assert.equal(c.intervention,roles.intervention);assert.equal(c.population,roles.population);}
assert.equal(Object.keys(p.certificates).length,3);assert.equal(p.guard_was_added_by_compiler,true);
for(const k of ['is_executable_rule','is_future_prediction','clinical_conclusion_deductively_entailed','author_asserted_this_three_part_group'])assert.equal(p[k],false);
assert.equal(guard.scope.full_guard_context_binding_pending,true);
const protoBytes=field(current.bytes,'guarded_prototype');assert.equal(rawJsonFingerprint(protoBytes.toString().replace(/,\s*"id"\s*:\s*"[a-f0-9]{64}"\s*}$/, '}')),p.id);
assert.equal(r.new_empirical_forecasts,0);assert.equal(r.scientific_success,false);assert.equal(r.graph_advantage_demonstrated,false);assert.equal(r.target_read,false);
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;assert.equal(doc.documentElement.lang,'ru');
assert.equal(doc.querySelectorAll('details').length,3);assert.equal(doc.querySelectorAll('table').length,1);assert.equal(doc.querySelectorAll('[src],link[href],script').length,0);
assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:r.run_id,tests_unique:tests.size,test_executions:executions,sources:maps.size,canonical_blocks:canonical,semantic_statements:statements,
  source_provenance_uses:uses,exact_functional_quote_uses:quoteCount,functional_certificates:2,guarded_cases:3,prototype_premises:3,
  primary_clinical_families:2,quantity_bound_prototypes:1,in_vivo_mechanism_inferred:false,new_empirical_forecasts:0,
  graph_advantage_demonstrated:false,model_calls:0,visual_review_claimed:false,
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const file=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(file))assert.deepEqual(read(file),bytes);else writeFileSync(file,bytes,{flag:'wx'});console.log(JSON.stringify(proof));
