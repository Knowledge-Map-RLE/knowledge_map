// Проверка автономного русского отчёта и привязки к реальному парному прогону.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
const file=path.resolve(process.argv[2]),folder=path.dirname(file);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const d=new JSDOM(fs.readFileSync(file,'utf8')).window.document,data=read(path.join(folder,'data.json'));
assert.equal(d.documentElement.lang,'ru');
assert.equal(d.querySelectorAll('script,iframe,[src],link[rel="stylesheet"],[lang="en"]').length,0);
assert.match(d.body.textContent,/не совпадения с целевой статьёй/);
assert.match(d.body.textContent,/преимущество Карты Знаний пока не установлено/);
for(const a of d.querySelectorAll('a[href]')){
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder,a.getAttribute('href'))));
}
const r=read(path.resolve(folder,'../forecast-runs',data.run_id,'predictions.json'));
const b=read(path.resolve(folder,'../forecast-runs',data.baseline_run_id,'predictions.json'));
assert.equal(data.canonical_blocks,r.canonical_blocks);assert.equal(data.eligible,r.coverage.filter(c=>c.eligible).length);
assert.deepEqual(r.binding.map_hashes,b.binding.map_hashes);assert.deepEqual(r.binding.implementation,b.binding.implementation);
assert.equal(data.numeric_consequences,r.numeric_consequences.proofs.length);
assert.equal(data.admitted_frames,r.numeric_consequences.proofs.filter(p=>p.operator==='audited_statistical_context').length);
assert.equal(data.new_supported_predictions,r.predictions.graph.length);
assert.equal(data.graph_advantage_demonstrated,false);assert.equal(data.model_calls,0);assert.equal(data.target_reads,0);
const evidence=read(path.join(folder,'evidence-presentation-audit.json'));
assert.equal(evidence.entries.length,data.canonical_blocks);
assert.equal(evidence.entries.filter(e=>e.status==='unclassified').length,data.untagged_blocks);
const verification={passed:true,language:'ru',external_resources:0,paired_code_and_corpus_verified:true,
  canonical_blocks:data.canonical_blocks,admitted_model_frames:data.admitted_frames,visual_inspection:false};
const text=JSON.stringify(verification,null,2)+'\n',out=path.join(folder,'html-verification.json');
if(fs.existsSync(out))assert.equal(fs.readFileSync(out,'utf8'),text);else fs.writeFileSync(out,text,{flag:'wx'});
process.stdout.write(JSON.stringify(verification)+'\n');
