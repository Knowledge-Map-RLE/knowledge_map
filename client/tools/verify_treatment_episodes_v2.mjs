// Усиленная ревизия сохраняет все научные результаты первой, меняя только проверки допуска.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {rawJsonFingerprint} from './raw_json_fingerprint.mjs';
await import('./verify_treatment_episodes.mjs');
const root=resolve(import.meta.dir,'../../eval/whole_map_forecast/treatment-episodes-v1'),review=resolve(root,'review-v2');
const read=p=>readFileSync(p),json=p=>JSON.parse(read(p)),hash=b=>createHash('sha256').update(b).digest('hex');
function field(bytes,name){const s=bytes.toString(),m=new RegExp('^  "'+name+'":\\s*','m').exec(s);assert.ok(m);
  const start=m.index+m[0].length;let depth=0,quoted=false,escaped=false;
  for(let i=start;i<s.length;i++){const c=s[i];if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}if(c==='{'||c==='[')depth++;else if(c==='}'||c===']')depth--;
    if(!depth)return Buffer.from(s.slice(start,i+1));}assert.fail('Незавершённый JSON');}
function seal(folder){const bytes=read(resolve(folder,'predictions.json')),data=JSON.parse(bytes),p=json(resolve(folder,'seal.json'));
  assert.equal(rawJsonFingerprint(bytes),p.prediction_sha256);assert.equal(rawJsonFingerprint(field(bytes,'binding')),data.run_id);
  for(const[f,d]of Object.entries(data.binding.implementation))assert.equal(hash(read(resolve(folder,'implementation',f))),d);
  return{bytes,data};}
const receipt=json(resolve(review,'verification.json')),previousReceipt=json(resolve(root,'review-v1/verification.json'));
for(const[f,d]of Object.entries(receipt.files))assert.equal(hash(read(resolve(review,f))),d);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_treatment_episodes.py'))),receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir,'../../api/tools/render_template_barrier_audit.py'))),receipt.helper_sha256);
const current=seal(receipt.run_path),previous=seal(previousReceipt.run_path),functional=seal(receipt.functional_path);
assert.equal(current.data.version,'source-bound-treatment-episodes-2');
assert.notEqual(current.data.run_id,previous.data.run_id);assert.notEqual(current.data.binding.implementation['domain/treatment_episode_context.py'],previous.data.binding.implementation['domain/treatment_episode_context.py']);
assert.equal(rawJsonFingerprint(functional.bytes),current.data.binding.functional_sha256);
assert.equal(current.data.binding.source_sha256,previous.data.binding.source_sha256);
assert.deepEqual(current.data.binding.map_hashes,previous.data.binding.map_hashes);
assert.equal(current.data.binding.cases_sha256,previous.data.binding.cases_sha256);
const scientific=d=>Object.fromEntries(Object.entries(d).filter(([key])=>!['version','run_id','binding'].includes(key)));
assert.deepEqual(scientific(current.data),scientific(previous.data));
// Все прежние результаты, родители, числа и контексты должны оставаться буквально теми же.
for(const name of ['episodes','calendar_consequences','calendar_conflicts','protocol_conflicts','guarded_prototype','assets'])
  assert.equal(rawJsonFingerprint(field(current.bytes,name)),rawJsonFingerprint(field(previous.bytes,name)));
const auditBytes=read(resolve(receipt.run_path,'audit.json')),audit=JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes),current.data.binding.audit_sha256);
assert.equal(audit.version,current.data.version);assert.equal(audit.model_calls,0);assert.equal(audit.expert_validated,false);
assert.deepEqual(audit.assets,current.data.assets);
assert.equal(audit.entries.find(e=>e.case_id==='tros-manifest').reported_after_last_dose_days,'12');
assert.equal(hash(read(resolve(receipt.run_path,audit.assets.atrosimab_figure7.path))),
  'fc2cdd3ba1d91c0aac2e780b0f30b4793b9aca2465cca64c239cf7797c6ebd82');
assert.equal(hash(read(resolve(receipt.run_path,audit.assets.atrosimab_xml.path))),
  '62f7a485973785e91c57ff8de3e3890c6569c39732313bd54e301ab9cb3aa420');
const tests=new Set(),allTests=new Set();let executions=0;
function checkTests(receipts,selected){for(const r of receipts){const bytes=read(r.path);assert.equal(hash(bytes),r.sha256);
  const doc=new JSDOM(bytes.toString(),{contentType:'text/xml'}).window.document;let count=0;
  for(const s of doc.querySelectorAll('testsuite')){count+=Number(s.getAttribute('tests'));
    for(const k of ['errors','failures','skipped'])assert.equal(Number(s.getAttribute(k)),0);}
  assert.equal(count,r.tests);executions+=count;
  for(const t of doc.querySelectorAll('testcase')){const id=JSON.stringify([t.getAttribute('classname'),t.getAttribute('name')]);allTests.add(id);if(selected)tests.add(id);}}}
checkTests(previousReceipt.tests,false);checkTests(receipt.tests,true);
assert.equal(tests.size,37);assert.equal(tests.size,receipt.tests_unique);assert.equal(allTests.size,93);assert.equal(executions,128);
assert.ok([...tests].some(t=>t.includes('omit_reported_distance')));assert.ok([...tests].some(t=>t.includes('replace_asset_and_hash')));
const doc=new JSDOM(read(resolve(review,'report.html')).toString()).window.document;
assert.equal(doc.documentElement.lang,'ru');assert.equal(doc.querySelectorAll('details').length,4);assert.equal(doc.querySelectorAll('table').length,2);
assert.equal(doc.querySelectorAll('img').length,1);assert.equal(doc.querySelector('img').getAttribute('src'),'figure7.jpg');
assert.equal(doc.querySelectorAll('script,link[href]').length,0);assert.match(doc.body.textContent,/Новых эмпирических прогнозов — 0/);
const proof={run_id:current.data.run_id,prior_run_id:previous.data.run_id,tests_current:tests.size,tests_unique_across_revisions:allTests.size,
  test_executions_across_revisions:executions,sources:11,canonical_blocks:943,semantic_statements:1897,
  unchanged_source_cases:3,calendar_consequences:4,calendar_conflicts:1,protocol_conflicts:1,
  known_calendar_conflict_omission_rejected:true,figure_replacement_with_recomputed_hash_rejected:true,
  scientific_results_preserved:true,new_empirical_forecasts:0,graph_advantage_demonstrated:false,model_calls:0,
  visual_report_review_claimed:false,local_browser_review_blocked_by_policy:true,
  upstream_receipt_sha256:hash(read(resolve(root,'review-v1/bun-verification.json'))),
  upstream_verifier_sha256:hash(read(resolve(import.meta.dir,'verify_treatment_episodes.mjs'))),
  verifier_sha256:hash(read(import.meta.filename)),helper_sha256:hash(read(resolve(import.meta.dir,'raw_json_fingerprint.mjs')))};
const file=resolve(review,'bun-verification.json'),bytes=Buffer.from(JSON.stringify(proof,null,2)+'\n');
if(existsSync(file))assert.deepEqual(read(file),bytes);else writeFileSync(file,bytes,{flag:'wx'});console.log(JSON.stringify(proof));
