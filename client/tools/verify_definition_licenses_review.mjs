// Проверка русского автономного отчёта и сохранённых доказательств.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';

const file=path.resolve(process.argv[2]),folder=path.dirname(file);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const d=new JSDOM(fs.readFileSync(file,'utf8')).window.document;
const data=read(path.join(folder,'data.json')),v=data.verification;
assert.equal(d.documentElement.lang,'ru');
assert.equal(d.querySelectorAll('[src],iframe,link[rel="stylesheet"],[lang="en"],script').length,0);
assert.equal(d.querySelectorAll('.conclusion').length,2);
assert.equal(d.querySelectorAll('tbody tr').length,4);
assert.match(d.body.textContent,/Преимущество графа не доказано/);
assert.match(d.body.textContent,/0 новых эмпирических прогнозов/);
for(const a of d.querySelectorAll('a[href]')){
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder,a.getAttribute('href'))));
}
assert.equal(v.canonical_blocks,759);assert.equal(v.statements,1478);
assert.equal(v.licensed_parent_blocks,2);assert.equal(v.licensed_views,3);
assert.equal(v.python_tests_passed,222);assert.equal(v.model_calls,0);
assert.equal(v.new_empirical_predictions,0);assert.equal(v.target_reads,0);
assert.deepEqual(v.logical_counts,{graph:0,without_dependencies:2,source_neighborhood:0,permuted_dependencies:0});
const runs=path.resolve(folder,'../forecast-runs');
const current=read(path.join(runs,v.run_id,'predictions.json'));
const base=read(path.join(runs,v.base_run_id,'predictions.json'));
assert.deepEqual(current.licensed_categorical_inference,data.licensed_categorical_inference);
assert.deepEqual(current.binding.implementation,base.binding.implementation);
assert.deepEqual(current.binding.map_hashes,base.binding.map_hashes);
assert.deepEqual(current.predictions,base.predictions);
assert.equal(current.licensed_categorical_inference.coverage.length,762);
assert.equal(current.numeric_consequences.proofs.length,151);
for(const item of data.conclusions){
  assert.equal(item.candidate.proof.entailed,true);
  assert.equal(item.candidate.proof.countermodels,0);
  assert.equal(item.candidate.novel_empirical_prediction,false);
  assert.equal(item.candidate.premises.length,2);
  assert.equal(item.candidate.proof_graph.nodes.length,4);
  for(const p of item.candidate.premises)assert.ok(p.statement_id && p.view_id && p.license_proof_sha256);
  assert.ok(d.body.textContent.includes(item.text_ru));
}
const verification={passed:true,language:'ru',external_resources:0,proofs_present:2,
  paired_input_verified:true,scientific_success:false,visual_inspection:false};
const output=path.join(folder,'html-verification.json'),text=JSON.stringify(verification,null,2)+'\n';
if(fs.existsSync(output))assert.equal(fs.readFileSync(output,'utf8'),text);
else fs.writeFileSync(output,text,{flag:'wx'});
process.stdout.write(JSON.stringify(verification)+'\n');
