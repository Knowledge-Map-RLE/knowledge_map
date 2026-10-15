// Проверяет автономный отчёт без сетевого доступа и исполняет обе локализации.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM, VirtualConsole } from 'jsdom';

const path=resolve(process.argv[2]);
const html=readFileSync(path,'utf8');
const errors=[];
const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
let attemptedNetwork=0;
const dom=new JSDOM(html,{virtualConsole:console,beforeParse(w){
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.fetch=()=>{attemptedNetwork++;throw Error('Network forbidden')};
  w.XMLHttpRequest=class{constructor(){attemptedNetwork++;throw Error('Network forbidden')}};
  w.WebSocket=class{constructor(){attemptedNetwork++;throw Error('Network forbidden')}};
}});
const d=dom.window.document,data=JSON.parse(d.getElementById('data').textContent);
// Bun 1.2 не поддерживает vm.DONT_CONTEXTIFY из jsdom. Исполняем тот же
// встроенный скрипт с явными DOM-портами, без Node VM и автоматической загрузки.
const source=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',source)(
  d,dom.window,dom.window.fetch,dom.window.XMLHttpRequest,dom.window.WebSocket);
assert.equal(d.querySelectorAll('script[src],link[href],iframe').length,0);
let inspected=0,verifiedProofs=0;
function inspect(button){
  button.click();assert.equal(d.getElementById('detail').hidden,false);inspected++;
  for(const proofButton of d.querySelectorAll('#proof-buttons button')){
    proofButton.click();const key=d.getElementById('fragment').dataset.proof,p=data.evidence[key];
    assert.equal(d.getElementById('fragment').textContent,p.text);
    assert.equal(Array.from(data.texts[p.source_id]).slice(p.start,p.end).join(''),p.text);
    assert.equal(d.querySelector('#full-text mark').textContent,p.text);
    assert.match(d.getElementById('table-image').src,/^data:image\/png;base64,/);verifiedProofs++;
  }
}
function change(id,value){const s=d.getElementById(id);s.value=value;s.dispatchEvent(new dom.window.Event('change'))}
for(const language of ['ru','en']){
  d.getElementById(language).click();assert.equal(d.documentElement.lang,language);
  change('source-filter','all');change('rate-filter','all');
  assert.equal(d.querySelectorAll('#cards .card').length,7);
  assert.equal(d.querySelectorAll('#rates tr').length,49);
  assert.equal(d.querySelectorAll('#audit tr').length,45);
  for(const b of d.querySelectorAll('#cards button,#rates button'))inspect(b);
  change('source-filter','katz2012');assert.equal(d.querySelectorAll('#rates tr').length,10);
  change('rate-filter','repair');assert.equal(d.querySelectorAll('#rates tr').length,8);
  change('source-filter','busse2003');assert.equal(d.querySelectorAll('#rates tr').length,0);
  for(const mode of ['strict','exploratory','frequency']){
    change('mode-filter',mode);change('outcome-filter','all');
    assert.equal(d.querySelectorAll('#forecasts tr').length,30);
    for(const b of d.querySelectorAll('#forecasts button'))inspect(b);
    change('outcome-filter','wrong');assert.equal(d.querySelectorAll('#forecasts tr').length,data.evaluation.modes[mode].wrong_order);
  }
}
assert.equal(attemptedNetwork,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],rates:49,review_cells:45,queries:30,inspected,verifiedProofs,attemptedNetwork,jsErrors:errors};
writeFileSync(resolve(path,'../dom-validation.json'),JSON.stringify(receipt,null,2));
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
