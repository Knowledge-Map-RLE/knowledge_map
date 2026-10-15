// Независимая проверка лицензий и единственного отличия основного прогона от контроля.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root=resolve(import.meta.dir,'../../eval/whole_map_forecast/protocol-parameter-transfer-v1');
const read=p=>readFileSync(resolve(root,p)), json=p=>JSON.parse(read(p));
const hash=v=>createHash('sha256').update(v).digest('hex');
const data=json('review-v1/data.json'), receipt=json('review-v1/verification.json');
for(const [p,h] of Object.entries(receipt.inputs)) assert.equal(hash(read(p)),h);
for(const [p,h] of Object.entries(receipt.files)) assert.equal(hash(read('review-v1/'+p)),h);
assert.equal(hash(read('build_review.py')),receipt.builder_sha256);
function rawField(bytes,name){
  const text=bytes.toString('utf8'),m=new RegExp('^  "'+name+'":\\s*','m').exec(text); assert.ok(m);
  const begin=m.index+m[0].length; let depth=0,quoted=false,escaped=false;
  for(let i=begin;i<text.length;i++){const c=text[i];
    if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;} if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(depth===0)return Buffer.from(text.slice(begin,i+1));
  } assert.fail('Незавершённый JSON');
}
function seal(folder){
  const raw=read(folder+'/predictions.json'),d=JSON.parse(raw);
  assert.equal(rawJsonFingerprint(raw),json(folder+'/seal.json').prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(raw,'binding')),d.run_id);
  for(const [p,h] of Object.entries(d.binding.implementation)) assert.equal(hash(read(folder+'/implementation/'+p)),h);
  assert.equal(d.model_calls,0);assert.equal(d.target_read,false);assert.equal(d.scientific_success,false);
  assert.equal(d.graph_advantage_demonstrated,false);assert.equal(json(folder+'/reads.json').network_disabled,true);
  return d;
}
const folder='runs/'+data.run_id,controlFolder='control-runs/'+data.control_run_id;
const result=seal(folder),control=seal(controlFolder);
for(const key of ['references','map_hashes','families','context_audit_sha256','model_audit_sha256','origin_audit_sha256','compound_licenses_sha256','implementation']) assert.deepEqual(result.binding[key],control.binding[key]);
const a={...result.binding.metadata},b={...control.binding.metadata};
assert.equal(a.protocol_parameters_enabled,true);assert.equal(b.protocol_parameters_enabled,false);
delete a.protocol_parameters_enabled;delete b.protocol_parameters_enabled;assert.deepEqual(a,b);
assert.deepEqual(result.part_views,control.part_views);assert.equal(result.canonical_blocks,943);assert.equal(result.licensed_parts,854);
const inputs=json(folder+'/inputs-manifest.json'), maps=new Map();
assert.deepEqual(inputs,json(controlFolder+'/inputs-manifest.json'));assert.equal(inputs.sources.length,11);
for(const entry of inputs.sources){
  const raw=read(folder+'/'+entry.map_path),m=JSON.parse(raw);
  assert.equal(hash(raw),entry.map_file_sha256);assert.equal(m.run_id,entry.reference.run_id);
  assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  maps.set(m.article_id,m);
  const pending=new Map(m.graph.nodes.map(n=>[n.id,0])),next=new Map(m.graph.nodes.map(n=>[n.id,[]]));
  for(const e of m.graph.edges){assert.ok(pending.has(e.source)&&pending.has(e.target));pending.set(e.target,pending.get(e.target)+1);next.get(e.source).push(e.target);}
  const queue=[...pending].filter(([,n])=>n===0).map(([id])=>id);let count=0;
  while(queue.length){const id=queue.shift();count++;for(const t of next.get(id)){pending.set(t,pending.get(t)-1);if(pending.get(t)===0)queue.push(t);}}
  assert.equal(count,m.graph.nodes.length);
}
function decimals(raw){
  return raw.split(';').map(value=>{assert.match(value.trim(),/^(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?$/);
    const [base,exp='0']=value.trim().toLowerCase().split('e'),[integer,fraction='']=base.split('.');
    let n=BigInt((integer||'0')+fraction),d=10n**BigInt(fraction.length),e=Number(exp);
    if(e>0)n*=10n**BigInt(e);else d*=10n**BigInt(-e);assert.ok(n>0n);return {n,d};
  });
}
function sameValue(a,b){const x=decimals(a),y=decimals(b);assert.equal(x.length,y.length);for(let i=0;i<x.length;i++)assert.equal(x[i].n*y[i].d,y[i].n*x[i].d);}
const parts=new Map(result.part_views.map(v=>[JSON.stringify(v.key),v]));let parameters=0,sourceReferences=0;
for(const c of data.cases){
  const rule=result.learning_by_mode.graph.learning.unsupported_rules.find(r=>r.id===c.rule_id);assert.deepEqual(rule,c.rule);
  const example=rule.examples.find(e=>e.protocol_parameter_proof?.id===c.license.id);assert.ok(example);
  const h=parts.get(JSON.stringify(example.head));assert.deepEqual(h.native_key,c.head_native_key);
  assert.equal(h.projection_proof.origin.origin,'primary_result');assert.ok(h.projection_proof.qualitative_result_proof_id);
  assert.deepEqual(h.projection_proof.complete_native_knowledge,c.parent);
  assert.equal(c.support.length,1);assert.equal(c.support[0].primary_families.length,1);
  const {id,...proof}=c.license;assert.equal(rawJsonFingerprint(Buffer.from(JSON.stringify(proof))),id);
  assert.equal(proof.scope_erased,false);assert.equal(proof.measured_response_created,false);assert.equal(proof.numeric_result_prediction,false);
  assert.equal(proof.all_head_protocol_context_fields_matched,true);
  for(const copy of proof.copies){
    const p=parts.get(JSON.stringify(copy.premise_key));assert.ok(example.body.some(k=>JSON.stringify(k)===JSON.stringify(p.key)));
    assert.equal(p.projection_proof.origin.origin,'primary_method');assert.equal(p.frame.kind,'action');assert.equal(p.frame.action_status,'performed');
    assert.equal(p.native_key[0],h.native_key[0]);assert.equal(p.run_id,h.run_id);
    const ps=p.frame.statements[copy.premise_statement],hs=h.frame.statements[copy.head_statement];
    assert.deepEqual(ps.scope,hs.scope);assert.equal(ps.negated,false);assert.equal(hs.negated,false);
    assert.deepEqual(ps.attributes[copy.premise_attribute],copy.premise_parameter);
    assert.deepEqual(hs.attributes[copy.head_attribute],copy.head_parameter);
    assert.equal(copy.premise_parameter.unit,copy.head_parameter.unit);sameValue(copy.premise_parameter.value,copy.head_parameter.value);
    assert.equal(copy.specification.arity,decimals(copy.head_parameter.value).length);
    for(const role of ['intervention','population','comparator']) assert.deepEqual(ps.roles.find(r=>r.role===role),hs.roles.find(r=>r.role===role));
    if(copy.specification.kind==='manifest_schedule'){
      assert.match(p.projection_proof.complete_native_knowledge.display_text,/\bof manifest EAE\b/i);
      assert.equal(copy.head_parameter.name,'days of manifest disease');assert.equal(copy.head_parameter.unit,'day');
    }else{assert.equal(copy.specification.kind,'dose');assert.equal(copy.head_parameter.unit,'mg/kg');}
    for(const v of [p,h]){
      const m=maps.get(v.native_key[0]),text=[...m.source.text];
      for(const span of v.projection_proof.complete_native_knowledge.provenance.source_spans){
        assert.ok(m.source.units.some(u=>u.start===span.start&&u.end===span.end&&u.text===text.slice(span.start,span.end).join('')));sourceReferences++;
      }
    }parameters++;
  }
}
assert.equal(parameters,4);assert.equal(data.cases.length,2);
assert.equal(result.learning_by_mode.graph.learning.rejected.unmodelled_numeric_conclusion,156);
assert.equal(control.learning_by_mode.graph.learning.rejected.unmodelled_numeric_conclusion,158);
for(const mode of Object.keys(result.predictions)){assert.equal(result.predictions[mode].length,0);assert.equal(control.predictions[mode].length,0);}
const html=read('review-v1/report.html').toString('utf8');assert.match(html,/<html lang="ru">/);
assert.match(html,/Новых научных прогнозов — 0/);assert.doesNotMatch(html,/<script[^>]*\bsrc\s*=/i);
const output={same_corpus_and_code:true,maps:11,knowledge:943,parameter_bindings_verified:parameters,
  primary_source_families_for_new_templates:1,new_predictions:0,source_references_checked:sourceReferences,
  graph_advantage_demonstrated:false,scientific_validation:false,model_calls:0,
  verifier_sha256:hash(readFileSync(import.meta.path)),helper_sha256:hash(readFileSync(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const path=resolve(root,'review-v1/bun-verification.json'),bytes=Buffer.from(JSON.stringify(output,null,2)+'\n');
try{writeFileSync(path,bytes,{flag:'wx'});}catch(error){if(error.code!=='EEXIST')throw error;assert.deepEqual(readFileSync(path),bytes);}
console.log(JSON.stringify(output));
