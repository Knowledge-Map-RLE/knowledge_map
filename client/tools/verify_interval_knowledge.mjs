// Источники, интервальная арифметика и условное покрытие проверяются независимо.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root=resolve(import.meta.dir,'../../eval/whole_map_forecast/interval-summary-operators-v1');
const read=p=>readFileSync(p), json=p=>JSON.parse(read(p)), hash=b=>createHash('sha256').update(b).digest('hex');
function field(bytes,name) {
  const text=bytes.toString(), match=new RegExp('^  "'+name+'":\\s*','m').exec(text); assert.ok(match);
  const start=match.index+match[0].length; let depth=0,quote=false,escape=false;
  for(let i=start;i<text.length;i++) {
    const c=text[i]; if(quote) { if(escape) escape=false; else if(c==='\\') escape=true; else if(c==='"') quote=false; continue; }
    if(c==='"') {quote=true;continue;} if(c==='{'||c==='[') depth++; else if(c==='}'||c===']') depth--;
    if(!depth) return Buffer.from(text.slice(start,i+1));
  }
  assert.fail('Незавершённый JSON');
}
function seal(folder) {
  const bytes=read(resolve(folder,'predictions.json')), value=JSON.parse(bytes), receipt=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),receipt.prediction_sha256); assert.equal(rawJsonFingerprint(field(bytes,'binding')),value.run_id);
  for(const [f,digest] of Object.entries(value.binding.implementation)) assert.equal(hash(read(resolve(folder,'implementation',f))),digest);
  assert.equal(value.model_calls,0); return {bytes,value};
}
const review=resolve(root,'review-v1'), receipt=json(resolve(review,'verification.json'));
for(const [f,d] of Object.entries(receipt.files)) assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(receipt.tests_path)),receipt.tests_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_interval_knowledge.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const tests=new JSDOM(read(receipt.tests_path).toString(),{contentType:'text/xml'}).window.document;
let passed=0; for(const s of tests.querySelectorAll('testsuite')) {
  passed+=Number(s.getAttribute('tests')); for(const k of ['errors','failures','skipped']) assert.equal(Number(s.getAttribute(k)),0);
}
assert.equal(passed,83); assert.equal(passed,receipt.tests_passed);
const current=seal(receipt.run_path), baseline=seal(receipt.baseline_path), data=current.value;
const pointer=json(resolve(receipt.baseline_path,'input-corpus.json')), source=seal(pointer.snapshot), frozen=source.value;
assert.equal(rawJsonFingerprint(baseline.bytes),data.binding.baseline_sha256);
assert.equal(rawJsonFingerprint(source.bytes),data.binding.source_sha256);
assert.deepEqual(data.binding.map_hashes,frozen.binding.map_hashes);
const auditBytes=read(resolve(receipt.run_path,'audit.json')), audit=JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes),data.binding.audit_sha256);
assert.equal(rawJsonFingerprint(source.bytes),audit.input_sha256);
assert.equal(rawJsonFingerprint(read(resolve(pointer.snapshot,'origin-audit.json'))),data.binding.origin_audit_sha256);
assert.equal(hash(read(resolve(pointer.snapshot,'origin-audit.json'))),frozen.binding.metadata.input_audit_file_sha256['origin-audit']);
const index=json(resolve(pointer.snapshot,'inputs-manifest.json')), maps=new Map(), native=new Map();
let canonical=0, statements=0, uses=0, fields=0, parents=0;
const norm=s=>s.normalize('NFKC').toLowerCase().replaceAll('_',' ').trim().replace(/\s+/g,' ');
for(const e of index.sources) {
  const bytes=read(resolve(pointer.snapshot,e.map_path)); assert.equal(hash(bytes),e.map_file_sha256);
  const m=JSON.parse(bytes); maps.set(m.article_id,m); assert.equal(m.graph.schema_version,6);
  assert.equal(hash(Buffer.from(m.source.text)),m.source.sha256);
  assert.notEqual(m.source.sha256,'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  if(e.coverage_path) assert.equal(hash(read(resolve(pointer.snapshot,e.coverage_path))),e.coverage_sha256);
  const ids=new Set(m.graph.nodes.map(n=>n.id)), degrees=new Map([...ids].map(i=>[i,0])), adjacent=new Map([...ids].map(i=>[i,[]]));
  assert.equal(ids.size,m.graph.nodes.length);
  for(const edge of m.graph.edges) {
    assert.ok(ids.has(edge.source)&&ids.has(edge.target)); degrees.set(edge.target,degrees.get(edge.target)+1); adjacent.get(edge.source).push(edge.target);
  }
  const queue=[...ids].filter(i=>degrees.get(i)===0); let visits=0;
  while(queue.length) {const i=queue.pop();visits++;for(const t of adjacent.get(i)) {degrees.set(t,degrees.get(t)-1);if(!degrees.get(t))queue.push(t);}}
  assert.equal(visits,ids.size);
  const units=new Map(m.source.units.map(u=>[u.id,u])), text=Array.from(m.source.text);
  for(const k of m.graph.knowledge) {
    canonical++;native.set(JSON.stringify([m.article_id,k.knowledge_id]),k);let hasInterval=false;
    for(const s of k.semantic_frame.statements) {
      statements++;
      for(const uid of s.provenance.unit_ids) {const u=units.get(uid);assert.ok(u);assert.equal(text.slice(u.start,u.end).join(''),u.text);uses++;}
      for(const a of s.qualifiers.attributes) {
        const name=norm(a.name);
        if(name.split(' ').includes('ci')||name.includes('ci95')||name.includes('confidence')) {fields++;hasInterval=true;}
      }
    }
    if(hasInterval)parents++;
  }
}
assert.equal(maps.size,11);assert.equal(canonical,943);assert.equal(statements,1897);
assert.equal(data.coverage.length,canonical);assert.equal(fields,receipt.interval_fields);assert.equal(parents,receipt.interval_parents);
assert.equal(data.interval_consequences.length,2);assert.equal(data.projected_views.length,2);
// Десятичные разности вычисляются через BigInt, без двоичной арифметики Number.
function decimal(raw,scale) {
  assert.match(raw,/^-?\d+(?:\.\d+)?$/);const negative=raw.startsWith('-');const [i,f='']=raw.replace(/^-/, '').split('.');
  return BigInt(i+f.padEnd(scale,'0'))*(negative?-1n:1n);
}
function display(value,scale) {
  const sign=value<0n?'-':'';let digits=(value<0n?-value:value).toString().padStart(scale+1,'0');
  if(!scale)return sign+digits;let result=digits.slice(0,-scale)+'.'+digits.slice(-scale);
  result=result.replace(/0+$/,'').replace(/\.$/,'');return sign+result;
}
let quotes=0;
for(const p of data.interval_consequences) {
  const key=JSON.stringify(p.native_key), k=native.get(key), m=maps.get(p.native_key[0]);assert.deepEqual(p.complete_native_knowledge,k);
  const s=k.semantic_frame.statements.find(s=>s.statement_id===p.statement_id);assert.ok(s);
  const attrs=new Map(s.qualifiers.attributes.map(a=>[norm(a.name),a]));
  const e=audit.entries.find(e=>JSON.stringify(e.native_key)===key&&e.statement_id===p.statement_id);assert.ok(e);
  for(let i=0;i<2;i++) {
    const declaration=e.intervals[i],interval=p.intervals[i],lo=attrs.get(declaration.lower_field),hi=attrs.get(declaration.upper_field);
    assert.equal(String(lo.value),interval.bounds[0]);assert.equal(String(hi.value),interval.bounds[1]);assert.equal(lo.unit,interval.unit);assert.equal(hi.unit,interval.unit);
  }
  const points=p.intervals.flatMap(i=>i.bounds),scale=Math.max(...points.map(x=>(x.split('.')[1]||'').length));
  const [a,b,c,d]=points.map(x=>decimal(x,scale));const lower=a-d,upper=b-c;
  assert.deepEqual(p.geometry.difference,[display(lower,scale),display(upper,scale)]);
  assert.equal(p.geometry.overlap,(a>c?a:c)<=(b<d?b:d));assert.equal(p.geometry.zero_in_difference,lower<=0n&&0n<=upper);
  assert.deepEqual(p.geometry.overlap_bounds,p.geometry.overlap?[display(a>c?a:c,scale),display(b<d?b:d,scale)]:null);
  assert.equal(p.geometry.effect_absence_inferred,false);assert.equal(p.geometry.statistical_detection_inferred,false);
  assert.equal(attrs.get('ci level').value,95);
  const level=BigInt(String(attrs.get('ci level').value));assert.equal(p.coverage.conditional_joint_coverage_percent_at_least,(2n*level-100n).toString());
  for(const flag of ['assumed_independence','parameter_probability_asserted','actual_coverage_verified','reported_rounded_bounds_coverage_verified']) assert.equal(p.coverage[flag],false);
  assert.equal(p.future_prediction,false);assert.equal(p.scientific_confirmation,false);assert.equal(p.input_bounds_precision,'printed_rounded');
  assert.equal(p.reported_detection,e.reported_detection);assert.equal(p.reported_detection_inferred_by_operator,false);
  const units=new Map(m.source.units.map(u=>[u.id,u])),text=Array.from(m.source.text);
  for(const q of p.evidence) {
    const u=units.get(q.unit_id);assert.ok(s.provenance.unit_ids.includes(q.unit_id));
    assert.ok(u.start<=q.start&&q.end<=u.end);assert.equal(text.slice(q.start,q.end).join(''),q.text);assert.equal(hash(Buffer.from(q.text)),q.sha256);quotes++;
  }
}
// Перебор всех распределений двух событий на сетке 1/20 подтверждает границу и её достижимость.
let minimum=21,distributions=0;
for(let both=0;both<=20;both++)for(let first=0;first<=20-both;first++)for(let second=0;second<=20-both-first;second++) {
  const pa=both+first,pb=both+second;assert.ok(both>=Math.max(0,pa+pb-20));distributions++;
  if(pa>=19&&pb>=19)minimum=Math.min(minimum,both);
}
assert.equal(minimum,18);
const views=new Map(frozen.part_views.map(v=>[JSON.stringify(v.key),v]));assert.equal(views.size,910);
for(const v of data.projected_views) {
  const old=views.get(JSON.stringify(v.key)),p=v.projection_proof,license=p.interval_summary_proof;assert.ok(old);
  assert.equal(v.native_key[1],'K30');assert.deepEqual(license.complete_input_frame,old.frame);
  const original=old.frame.statements[0],now=v.frame.statements[0];
  for(const field of ['roles','scope','predicate','negated'])assert.deepEqual(now[field],original[field]);
  assert.equal(license.removed_summary_fields.length,5);
  assert.deepEqual(now.attributes,original.attributes.filter(a=>!license.removed_summary_fields.includes(a.name)));
  assert.deepEqual(p.complete_native_knowledge,old.projection_proof.complete_native_knowledge);
  assert.equal(rawJsonFingerprint(JSON.stringify(v.frame)),p.view_frame_sha256);
  assert.equal(license.scope_changed,false);assert.equal(license.participants_changed,false);assert.equal(license.future_confidence_predicted,false);
}
for(const [policy,modes] of Object.entries(data.policies))for(const [mode,row] of Object.entries(modes)) {
  assert.equal(row.predictions.length,0);assert.equal(row.rules?.length||0,0);
  if(policy==='before_interval_summary'&&row.learning)assert.deepEqual(row.learning,baseline.value.policies.typed_concept_participants[mode].learning);
}
assert.equal(data.policies.before_interval_summary.graph.learning.rejected.unmodelled_numeric_conclusion,244);
assert.equal(data.policies.source_bound_interval_summary.graph.learning.rejected.unmodelled_numeric_conclusion,236);
assert.equal(data.baseline_learning_reproduced,true);assert.equal(data.scientific_success,false);assert.equal(data.graph_advantage_demonstrated,false);
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;
assert.equal(doc.documentElement.lang,'ru');assert.equal(doc.querySelectorAll('table').length,2);assert.equal(doc.querySelectorAll('details').length,2);
assert.equal(doc.querySelectorAll('[src],link[href],script').length,0);assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:data.run_id,tests_passed:passed,sources:maps.size,canonical_blocks:canonical,semantic_statements:statements,
  source_provenance_uses:uses,interval_fields:fields,interval_parents:parents,exact_quote_uses:quotes,
  interval_consequences:2,projected_parts:2,joint_event_distributions:distributions,
  verified_actual_confidence_intervals:0,new_empirical_forecasts:0,graph_advantage_demonstrated:false,model_calls:0,visual_review_claimed:false,
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const destination=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(destination))assert.deepEqual(read(destination),bytes);else writeFileSync(destination,bytes,{flag:'wx'});
console.log(JSON.stringify(proof));
