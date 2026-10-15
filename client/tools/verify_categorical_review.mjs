// Проверка автономного русского отчёта, фильтров и фактического полного прогона.
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
for(const a of d.querySelectorAll('a[href]')){
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder,a.getAttribute('href'))));
}
assert.match(d.body.textContent,/Преимущество графа не доказано/);
assert.match(d.body.textContent,/759 блоков · 1478 утверждений · 0 новых прогнозов/);
assert.equal(data.syllogisms.rows.length,256);
assert.equal(data.syllogisms.unconditional,15);assert.equal(data.syllogisms.conditional_only,9);
assert.equal(data.categorical_coverage.coverage.length,759);
assert.equal(data.categorical_coverage.admitted_blocks,0);
assert.equal(data.verification.python_tests_passed,206);
assert.equal(data.verification.new_empirical_predictions,0);
assert.equal(data.verification.graph_advantage_demonstrated,false);
const r=read(path.resolve(folder,'../forecast-runs',data.verification.run_id,'predictions.json'));
assert.deepEqual(r.categorical_inference,data.categorical_coverage);
assert.equal(r.coverage.filter(c=>c.eligible).length,745);
assert.equal(r.numeric_consequences.proofs.length,151);
for(const rows of Object.values(r.categorical_inference.consequences))assert.equal(rows.length,0);
// Исполняем собственный фиксированный фильтр, не подгружая внешних ресурсов.
new Function('document',d.querySelector('script').textContent)(d);
const mode=d.getElementById('mode'),search=d.getElementById('search'),count=d.getElementById('count');
for(const [value,n] of [['unconditional',15],['conditional',9],['invalid',232],['all',256]]){
  mode.value=value;mode.dispatchEvent(new dom.window.Event('change'));
  assert.equal(count.textContent,`Показано ${n} из 256`);
}
search.value='AAA';search.dispatchEvent(new dom.window.Event('input'));
assert.equal(count.textContent,'Показано 4 из 256');
mode.value='unconditional';mode.dispatchEvent(new dom.window.Event('change'));
assert.equal(count.textContent,'Показано 1 из 256');
d.getElementById('reset').click();assert.equal(count.textContent,'Показано 256 из 256');
const result={passed:true,language:'ru',external_resources:0,filters_verified:true,
  full_corpus_verified:true,scientific_success:false,visual_inspection:false};
const text=JSON.stringify(result,null,2)+'\n',output=path.join(folder,'html-verification.json');
if(fs.existsSync(output))assert.equal(fs.readFileSync(output,'utf8'),text);else fs.writeFileSync(output,text,{flag:'wx'});
process.stdout.write(JSON.stringify(result)+'\n');
