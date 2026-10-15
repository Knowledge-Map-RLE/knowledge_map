// Проверяются происхождение и координаты; визуальный смысл пикселей не выдаётся за машинно доказанный.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';
const review=resolve(import.meta.dir,'../../eval/whole_map_forecast/timed-clinical-source-review-v1/review-v1');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function field(bytes,name){const s=bytes.toString(),m=new RegExp('^\\s*"'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(!depth)return Buffer.from(s.slice(start,i+1));}assert.fail('Незавершённый JSON');}
const receipt=json(resolve(review,'verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/prepare_timed_clinical_review.py'))),receipt.preparer_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const clockBytes=read(resolve(receipt.clock_path,'predictions.json')),clock=JSON.parse(clockBytes),clockSeal=json(resolve(receipt.clock_path,'seal.json'));
assert.equal(rawJsonFingerprint(clockBytes),clockSeal.prediction_sha256);assert.equal(rawJsonFingerprint(clockBytes),receipt.clock_sha256);
assert.equal(rawJsonFingerprint(field(clockBytes,'binding')),clock.run_id);
for(const[f,d]of Object.entries(clock.binding.implementation))assert.equal(hash(read(resolve(receipt.clock_path,'implementation',f))),d);
const priorPath=resolve(import.meta.dir,'../../eval/whole_map_forecast/first-administration-clock-v1/review-v2/bun-verification.json');
const prior=json(priorPath);assert.equal(prior.run_id,clock.run_id);
assert.equal(prior.verifier_sha256,hash(read(resolve(import.meta.dir,'verify_first_administration_clock.mjs'))));
assert.equal(prior.reversible_coordinates,19);assert.equal(prior.unknown_endpoint_preserved,true);
const data=json(resolve(review,'audit.json'));assert.equal(data.clock_run_id,clock.run_id);assert.equal(data.clock_sha256,receipt.clock_sha256);
assert.equal(data.preparer_sha256,receipt.preparer_sha256);assert.equal(data.author,'Codex');assert.equal(data.expert_validated,false);
assert.equal(data.witnesses.length,2);const families=new Set();let comparisons=0;
for(const w of data.witnesses){const p=clock.clock_proofs.find(p=>p.procedure===w.procedure);assert.ok(p);
  assert.deepEqual(w.full_context,p.complete_source_case);assert.deepEqual(w.source_clock_reference,p.reference);
  assert.equal(w.relative_time.reference_id,p.reference.id);assert.equal(w.relative_time.value,String(BigInt(w.source_day)-BigInt(p.reference.first_dose_day)));
  assert.equal(w.relative_time.value,'17');assert.equal(w.source_features.phase,'manifest_disease');assert.equal(w.source_features.species,'mouse');
  assert.deepEqual(w.source_features,p.complete_source_case.complete_case.features);
  assert.equal(hash(read(resolve(review,w.source_key+'.jpg'))),w.image_sha256);
  assert.equal(w.reported_relation,'lower_plotted_group_mean_clinical_score');assert.equal(w.read_by,'Codex');assert.equal(w.expert_validated,false);
  for(const key of ['exact_y_values_extracted','pointwise_significance_inferred','clinical_causality_inferred','continuous_effect_inferred','source_observation_end_filled_from_plot'])assert.equal(w[key],false);
  families.add(w.primary_family);comparisons+=w.dose_groups.length;
  if(w.source_key==='tros'){assert.equal(w.source_day,'25');assert.equal(w.figure_id,'Fig4');assert.equal(w.panel,'a_right');assert.equal(w.comparator_label,'PBS');
    assert.deepEqual(w.dose_groups,[{value:'500',unit:'microgram'}]);assert.equal(w.image_sha256,'660161c1507b849e00538e894ef8137ae4072d0774d08a1a7bf6a9956efb8c1e');}
  else{assert.equal(w.source_key,'atros');assert.equal(w.source_day,'18');assert.equal(w.panel,'A');assert.equal(w.comparator_label,'FcDeltaab');
    assert.deepEqual(w.dose_groups,[{value:'30',unit:'mg/kg'},{value:'60',unit:'mg/kg'}]);assert.equal(w.full_context.unknown_clinical_observation_end,true);
    assert.equal(w.image_sha256,'fc2cdd3ba1d91c0aac2e780b0f30b4793b9aca2465cca64c239cf7797c6ebd82');}
}
assert.equal(families.size,2);assert.equal(comparisons,3);assert.deepEqual(data.pattern.primary_families,[...families].sort());
assert.equal(data.pattern.coordinate,'17');assert.equal(data.pattern.unit,'source_day_coordinate');assert.equal(data.pattern.is_pattern_similarity,true);
for(const k of ['full_fact_equivalence','is_valid_universal_rule','is_future_forecast','is_automatically_extracted_visual_result'])assert.equal(data.pattern[k],false);
assert.equal(data.new_empirical_forecasts,0);assert.equal(data.graph_advantage_demonstrated,false);assert.equal(data.model_calls,0);assert.equal(data.target_read,false);
const captureRoot=resolve(import.meta.dir,'../../eval/whole_map_forecast/tros-figure4-audit-v1/source');
const capture=json(resolve(captureRoot,'acquisition.json'));assert.equal(capture.figure_id,'Fig4');assert.equal(capture.pmcid,'PMC5651799');
assert.equal(hash(read(resolve(captureRoot,'image.jpg'))),capture.image_sha256);
assert.equal(createHash('md5').update(read(resolve(captureRoot,'image.jpg'))).digest('hex'),capture.image_md5);
assert.equal(hash(read(resolve(captureRoot,'article.xml'))),capture.raw_xml_sha256);
assert.equal(capture.raw_xml_sha256,'43290ba600f55a76a1536e70ef912b5f6ba475898f9e64b7ad87a00f5a2f8aef');
assert.equal(hash(read(resolve(captureRoot,'source-packet.json'))),capture.source_packet_sha256);
assert.equal(capture.adapter_sha256,hash(read(resolve(import.meta.dir,'../../api/infrastructure/published_figure_capture.py'))));
const xml=new JSDOM(read(resolve(captureRoot,'article.xml')).toString(),{contentType:'text/xml'}).window.document;
const graphic=xml.querySelector('fig[id="Fig4"] graphic');assert.ok(graphic);assert.equal(graphic.getAttribute('xlink:href'),capture.image_name);
const pi=[...graphic.childNodes].filter(n=>n.nodeType===7).map(n=>[n.target,n.data]);
assert.ok(pi.some(([k,v])=>k==='image-md5'&&v===capture.image_md5));
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;assert.equal(doc.documentElement.lang,'ru');
assert.equal(doc.querySelectorAll('img').length,2);assert.deepEqual([...doc.querySelectorAll('img')].map(n=>n.getAttribute('src')),['tros.jpg','atros.jpg']);
assert.equal(doc.querySelectorAll('script,link[href]').length,0);assert.equal(doc.querySelectorAll('details').length,1);
assert.match(doc.body.textContent,/Новых будущих прогнозов — 0/);
const proof={clock_run_id:clock.run_id,witness_blocks:2,dose_specific_comparisons:3,primary_families:2,relative_coordinate:'17',
  provenance_and_arithmetic_verified:true,visual_mean_relation_automatically_verified:false,expert_validated:false,
  future_forecasts:0,graph_advantage_demonstrated:false,model_calls:0,visual_report_review_claimed:false,
  upstream_receipt_sha256:hash(read(priorPath)),verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const path=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(path))assert.deepEqual(read(path),bytes);else writeFileSync(path,bytes,{flag:'wx'});console.log(JSON.stringify(proof));
