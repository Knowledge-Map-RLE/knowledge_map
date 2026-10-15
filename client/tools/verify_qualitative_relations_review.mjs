// Проверяет локальный двуязычный отчёт; модельные и сетевые вызовы запрещены.
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));let network=0;
const dom=new JSDOM(html,{virtualConsole:vc}),d=dom.window.document;
const data=JSON.parse(d.getElementById('data').textContent);
const forbidden=()=>{network++;throw Error('Network forbidden')};
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe').length,0);
assert.deepEqual(data.validation.qualitative_records,23);
assert.equal(data.validation.sources_verified,7);
assert.equal(data.validation.comparison_controls,9);
let inspected=0,verifiedProofs=0,traceChecks=0;
function change(id,value){const s=d.getElementById(id);s.value=value;s.dispatchEvent(new dom.window.Event('change'))}
function proof(){
  const id=d.getElementById('fragment').dataset.proof,p=data.evidence[id];
  const expected=Array.from(data.texts[p.source_id]).slice(p.start,p.end).join('');
  assert.equal(d.getElementById('fragment').textContent,expected);
  assert.equal(d.querySelector('#full-text mark').textContent,expected);
  assert.equal(d.getElementById('full-text').textContent,data.texts[p.source_id]);verifiedProofs++;
}
function inspect(button){
  button.click();inspected++;proof();
  const id=d.getElementById('fragment').dataset.proof,claim=Object.values(data.claims).find(c=>c.provenance.includes(id));
  assert.deepEqual(JSON.parse(d.getElementById('frame').textContent),claim.semantic_frame);
  assert.deepEqual(JSON.parse(d.getElementById('context').textContent),claim.context);
}
for(const lang of ['ru','en']){
  d.getElementById(lang).click();assert.equal(d.documentElement.lang,lang);
  assert.equal(d.querySelectorAll('#pairs tr').length,9);
  assert.deepEqual([...d.querySelectorAll('#stats strong')].map(n=>Number(n.textContent)),[23,6,3,0]);
  for(const mode of ['semantic','known_union','frequency']){
    change('mode',mode);change('fold','all');change('factor','all');
    assert.equal(d.querySelectorAll('#cases tr').length,23);
    for(const b of d.querySelectorAll('#cases button'))inspect(b);
    for(const fold of data.evaluation.folds){
      change('fold',fold.fold_id);
      assert.equal(d.querySelectorAll('#cases tr').length,fold.modes[mode].rows.length);
      assert.ok([...d.querySelectorAll('#cases tr')].every(n=>n.dataset.fold===fold.fold_id));
    }
    change('fold','all');
    for(const factor of ['age','sex','education']){
      change('factor',factor);
      assert.equal(d.querySelectorAll('#cases tr').length,Object.values(data.claims).filter(c=>c.factor===factor).length);
    }
    change('factor','all');
  }
  for(const b of d.querySelectorAll('#pairs button'))inspect(b);
  change('mode','semantic');change('fold','all');change('factor','all');
  for(const tr of d.querySelectorAll('#cases tr')){
    if(!tr.querySelector('.good'))continue;
    inspect(tr.querySelector('button'));
    const trace=d.querySelectorAll('#trace button');assert.equal(trace.length,2);traceChecks++;
    const audits=d.getElementById('context-audit').textContent;
    d.getElementById(lang==='ru'?'en':'ru').click();
    assert.equal(d.querySelectorAll('#trace button').length,2);
    assert.equal(d.getElementById('context-audit').textContent,audits);
    d.getElementById(lang).click();
    for(const b of d.querySelectorAll('#trace button'))inspect(b);
  }
}
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],records:23,cohorts:6,sources:7,controlPairs:9,inspected,verifiedProofs,traceChecks,network,jsErrors:errors,
  method:'Bun with explicit jsdom DOM ports; not a visual browser inspection'};
const output=resolve(path,'../dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
