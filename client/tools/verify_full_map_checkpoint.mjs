// Автономная DOM-проверка отчёта и полной исследовательской карты без сетевых ресурсов.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
const file=path.resolve(process.argv[2]),folder=path.dirname(file);
const data=JSON.parse(fs.readFileSync(path.join(folder,'data.json'),'utf8'));
const report=new JSDOM(fs.readFileSync(file,'utf8')).window.document;
assert.equal(report.documentElement.lang,'ru');
assert.equal(report.querySelectorAll('script,iframe,[src],link[rel="stylesheet"],[lang="en"]').length,0);
assert.match(report.body.textContent,/не совпадения с целевой статьёй/);
assert.match(report.body.textContent,/преимущество Карты Знаний пока не установлено/);
for(const a of report.querySelectorAll('a[href]')){
  assert.ok(!/^(https?:|\/\/)/.test(a.getAttribute('href')));
  assert.ok(fs.existsSync(path.resolve(folder,a.getAttribute('href'))));
}
const result=JSON.parse(fs.readFileSync(path.resolve(folder,'../forecast-runs',data.run_id,'predictions.json'),'utf8'));
assert.equal(data.canonical_blocks,result.canonical_blocks);
assert.equal(data.eligible,result.coverage.filter(r=>r.eligible).length);
assert.equal(data.new_supported_predictions,result.predictions.graph.length);
assert.equal(data.graph_advantage_demonstrated,result.graph_advantage_demonstrated);
assert.equal(data.model_calls,0);assert.equal(data.target_reads,0);
assert.equal(data.source_table_cells_verified,true);
const html=fs.readFileSync(path.resolve(folder,'../runs',data.map_run_id,'map.html'),'utf8');
const dom=new JSDOM(html,{pretendToBeVisual:true,beforeParse(w){
  w.fetch=()=>{throw new Error('Network forbidden');};
  Object.defineProperty(w.HTMLElement.prototype,'clientWidth',{get:()=>1000});
  Object.defineProperty(w.HTMLElement.prototype,'clientHeight',{get:()=>700});
}});
const d=dom.window.document;
assert.equal(d.querySelectorAll('[src],link[rel="stylesheet"]').length,0);
for(const s of d.querySelectorAll('script:not([type])'))new Function('window','document',s.textContent)(dom.window,d);
const map=JSON.parse(d.querySelector('#data').textContent);
assert.equal(map.graph.knowledge.length,data.active_map.blocks);
assert.equal(d.querySelectorAll('.card').length,map.graph.nodes.length);
assert.equal(d.querySelectorAll('.edge').length,map.graph.edges.length);
const k=map.graph.knowledge.find(k=>k.knowledge_id===map.graph.nodes[0].knowledge_id);
assert.ok(d.querySelector('.card').textContent.includes(k.display_text));
d.querySelector('.card').click();assert.ok(d.querySelector('#details blockquote'));
const language=d.querySelector('#language');language.value='ru';language.dispatchEvent(new dom.window.Event('change'));
assert.ok(d.querySelector('.card').textContent.includes(map.translations.ru.labels[map.graph.nodes[0].id]));
d.querySelector('.hit').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
assert.match(d.querySelector('#details').textContent,/Совместные входы/);
assert.ok(d.querySelector('#details blockquote'));
const scene=d.querySelector('#scene'),old=scene.getAttribute('transform');d.querySelector('#plus').click();
assert.notEqual(scene.getAttribute('transform'),old);
d.querySelector('#source').click();assert.equal(d.querySelector('#full').textContent,map.source.text);
assert.equal(d.querySelector('#full').style.display,'block');
dom.window.close();
const verification={passed:true,language:'ru',canonical_blocks:data.canonical_blocks,map_blocks:data.active_map.blocks,
  offline_interactions:true,source_and_transition_selection:true,zoom:true,russian_labels:true,external_resources:0,visual_inspection:false};
const bytes=JSON.stringify(verification,null,2)+'\n',output=path.join(folder,'html-verification.json');
if(fs.existsSync(output))assert.equal(fs.readFileSync(output,'utf8'),bytes);else fs.writeFileSync(output,bytes,{flag:'wx'});
process.stdout.write(JSON.stringify(verification)+'\n');
