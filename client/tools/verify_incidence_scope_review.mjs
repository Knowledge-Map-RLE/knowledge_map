// Проверяет семантический отчёт в Bun с явными DOM-портами, без сети.
import { readFileSync,existsSync,writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM,VirtualConsole } from 'jsdom';

const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));let network=0;
const dom=new JSDOM(html,{virtualConsole:vc,beforeParse(w){w.HTMLElement.prototype.scrollIntoView=()=>{};}});
const d=dom.window.document,data=JSON.parse(d.getElementById('data').textContent);
function forbidden(){network++;throw Error('Network forbidden')}
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe').length,0);
let inspected=0,verifiedProofs=0;
function change(id,value){const s=d.getElementById(id);s.value=value;s.dispatchEvent(new dom.window.Event('change'))}
function inspect(button){
  button.click();inspected++;assert.equal(d.getElementById('detail').hidden,false);
  for(const b of d.querySelectorAll('#proof-buttons button')){
    b.click();const raw=d.getElementById('fragment').dataset.proof;
    const [source,start,end]=raw.split(':'),text=Array.from(data.texts[source]).slice(Number(start),Number(end)).join('');
    assert.equal(d.getElementById('fragment').textContent,text);
    assert.equal(d.querySelector('#full-text mark').textContent,text);verifiedProofs++;
  }
}
for(const lang of ['ru','en']){
  d.getElementById(lang).click();assert.equal(d.documentElement.lang,lang);
  change('filter','all');assert.equal(d.querySelectorAll('#queries tr').length,30);
  assert.equal(d.querySelectorAll('#metrics tr').length,4);
  for(const b of d.querySelectorAll('#queries button')){
    inspect(b);change('candidate-filter','sameAge');
    const p=data.predictions[d.getElementById('context-note').textContent];
    assert.equal(d.querySelectorAll('#candidates tr').length,p.candidate_audits.filter(a=>!a.reasons.includes('different_age_bounds')).length);
    for(const candidate of d.querySelectorAll('#candidates button'))inspect(candidate);
    change('candidate-filter','all');assert.equal(d.querySelectorAll('#candidates tr').length,p.candidate_audits.length);
  }
  change('filter','unknown');assert.equal(d.querySelectorAll('#queries tr').length,21);
  change('filter','complete');assert.equal(d.querySelectorAll('#queries tr').length,9);
}
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],queries:30,unknown:21,complete:9,inspected,verifiedProofs,network,jsErrors:errors};
const output=resolve(path,'../dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
