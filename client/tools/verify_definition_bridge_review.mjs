// Проверяет локальный двуязычный отчёт без сетевых запросов и автозапуска jsdom.
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));let network=0;
const dom=new JSDOM(html,{virtualConsole:vc}),d=dom.window.document;
const data=JSON.parse(d.getElementById('data').textContent);
function forbidden(){network++;throw Error('Network forbidden')}
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe').length,0);
let inspected=0,verifiedProofs=0;
function change(id,value){const s=d.getElementById(id);s.value=value;s.dispatchEvent(new dom.window.Event('change'))}
function inspect(button){
  button.click();inspected++;
  const key=d.getElementById('fragment').dataset.proof,p=data.evidence[key];
  const expected=Array.from(data.texts[p.source_id]).slice(p.start,p.end).join('');
  assert.equal(d.getElementById('fragment').textContent,expected);
  assert.equal(d.querySelector('#full-text mark').textContent,expected);
  assert.equal(d.getElementById('full-text').textContent,data.texts[p.source_id]);verifiedProofs++;
}
for(const lang of ['ru','en']){
  d.getElementById(lang).click();assert.equal(d.documentElement.lang,lang);
  assert.ok(d.querySelector('[data-i="title"]').textContent.length>20);
  assert.equal(d.querySelectorAll('#repairs tr').length,3);
  assert.equal(d.querySelectorAll('#rates tr').length,12);
  for(const button of d.querySelectorAll('#rates button'))inspect(button);
  for(let i=0;i<data.result.comparisons.length;i++){
    change('comparison',String(i));change('age-filter','all');
    const c=data.result.comparisons[i];assert.equal(d.querySelectorAll('#orders tr').length,c.rows.length);
    assert.equal(d.querySelectorAll('#orders .bad').length,c.rows.filter(r=>!r.point_order_preserved).length);
    for(const button of d.querySelectorAll('#orders button'))inspect(button);
    change('age-filter','adjacent');assert.equal(d.querySelectorAll('#orders tr').length,c.rows.filter(r=>r.adjacent).length);
    for(const button of d.querySelectorAll('#orders button'))inspect(button);
  }
  for(const button of d.querySelectorAll('#proof-buttons button'))inspect(button);
}
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],rates:12,sourceRepairs:3,definitionComparisons:4,inspected,verifiedProofs,network,jsErrors:errors,
  method:'Bun with explicit jsdom DOM ports; not a visual browser inspection'};
const output=resolve(path,'../dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
