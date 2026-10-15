// Проверяем локальный русский отчёт, данные и фильтр без браузерной сети.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';

const file=path.resolve(process.argv[2]),folder=path.dirname(file);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const dom=new JSDOM(fs.readFileSync(file,'utf8')),d=dom.window.document;
const data=read(path.join(folder,'data.json'));
assert.equal(d.documentElement.lang,'ru');
assert.equal(d.querySelectorAll('[src],iframe,link[rel="stylesheet"],[lang="en"]').length,0);
assert.equal(d.querySelectorAll('script').length,1);
assert.match(d.body.textContent,/Преимущество Карты Знаний не доказано/);
assert.match(d.body.textContent,/759 блоков · 1478 утверждений · 0 новых гипотез/);
for(const a of d.querySelectorAll('a[href]')){
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder,a.getAttribute('href'))));
}
assert.equal(data.inventory.length,8);
assert.equal(data.inventory.reduce((n,e)=>n+e.blocks,0),759);
assert.equal(data.inventory.reduce((n,e)=>n+e.statements,0),1478);
assert.equal(data.declared_dataset_families.length,4);
assert.deepEqual(data.support.counts,{'0':58,'1':136});
assert.equal(data.support.rules.length,194);
assert.ok(data.support.rules.every(r=>!r.two_primary_families_declared&&!r.logical_entailment_established));
assert.equal(data.pairs.length,6);
assert.ok(data.pairs.every(p=>!p.new_prediction&&!p.expert_validated&&p.examples.length===2));
assert.deepEqual(Object.keys(data.role_value_types),['str']);
const r=read(path.resolve(folder,'../forecast-runs',data.run_id,'predictions.json'));
const b=read(path.resolve(folder,'../forecast-runs',data.baseline_run_id,'predictions.json'));
assert.deepEqual(r.binding.map_hashes,b.binding.map_hashes);
assert.deepEqual(r.binding.implementation,b.binding.implementation);
assert.equal(r.binding.context_audit_sha256,b.binding.context_audit_sha256);
assert.equal(r.binding.model_audit_sha256,b.binding.model_audit_sha256);
assert.equal(b.binding.origin_audit_sha256,null);assert.ok(r.binding.origin_audit_sha256);
assert.deepEqual(r.predictions,b.predictions);assert.deepEqual(r.coverage,b.coverage);
assert.equal(r.coverage.filter(c=>c.eligible).length,745);
assert.equal(r.numeric_consequences.proofs.length,151);
for(const mode of ['graph','same_rules_without_dependencies','source_neighborhood_without_dependencies','permuted_dependencies'])
  assert.equal(r.predictions[mode].length,0);
// Исполняем только собственный встроенный фильтр; сетевых API в нём нет.
new Function('document',d.querySelector('script').textContent)(d);
const input=d.getElementById('filter'),count=d.getElementById('count');
input.value='проверка';input.dispatchEvent(new dom.window.Event('input'));
const shown=[...d.querySelectorAll('.pair')].filter(p=>!p.hidden);
assert.ok(shown.length>0&&shown.length<6);
assert.equal(count.textContent,`Показано ${shown.length} из 6`);
input.value='несуществующийзапрос';input.dispatchEvent(new dom.window.Event('input'));
assert.equal(count.textContent,'Показано 0 из 6');
d.getElementById('reset').click();assert.equal(count.textContent,'Показано 6 из 6');
const result={passed:true,language:'ru',external_resources:0,filters_verified:true,
  paired_corpus_verified:true,scientific_success:false,visual_inspection:false};
const text=JSON.stringify(result,null,2)+'\n',output=path.join(folder,'html-verification.json');
if(fs.existsSync(output))assert.equal(fs.readFileSync(output,'utf8'),text);else fs.writeFileSync(output,text,{flag:'wx'});
process.stdout.write(JSON.stringify(result)+'\n');
