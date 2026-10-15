// Проверка RU/EN, происхождения, сохранения выбора и латентных временных линий.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM,VirtualConsole} from 'jsdom';
const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{virtualConsole:vc}),d=dom.window.document;let network=0,fragmentChecks=0,timelines=0;
const forbidden=()=>{network++;throw Error('Network prohibited');};
const data=JSON.parse(d.getElementById('data').textContent);
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe,img').length,0);
for(const lang of ['ru','en']){
 if(d.documentElement.lang!==lang)d.getElementById('language').click();
 assert.equal(d.documentElement.lang,lang);
 assert.deepEqual([...d.querySelectorAll('#stats strong')].map(n=>Number(n.textContent)),[7,12,2,0]);
 assert.equal(d.querySelectorAll('#protocols tr').length,7);
 assert.equal(d.querySelectorAll('#table-rows tr').length,2);
 assert.deepEqual([...d.querySelector('#table-rows tr').querySelectorAll('td')].map(n=>n.textContent),['MCI · n=58','2','41.4%','6.9%','10.3%','3.5%','8.6%','29.3%']);
 for(const b of d.querySelectorAll('#protocols button')){
  b.click();for(const pre of d.querySelectorAll('#source pre')){
   const f=data.inputs.evidence.fragments[pre.dataset.proof],s=readFileSync(data.inputs.evidence.sources[f.source_id].path,'utf8');
   assert.equal(pre.textContent,Array.from(s).slice(f.start,f.end).join(''));fragmentChecks++;
  }
 }
 for(let world=0;world<2;world++){
  const circles=[...d.querySelectorAll('#timeline circle')];assert.equal(circles.length,9);
  assert.deepEqual(circles.map(c=>c.dataset.observation),['normal','MCI','normal','normal','MCI','normal','normal','MCI','normal']);
  const high=Number(d.querySelector('#timeline rect').getAttribute('width'));
  const second=Number(d.querySelectorAll('#timeline rect')[1].getAttribute('width'));
  assert.equal(high>second,world===0);timelines++;
  d.getElementById('world').click();
 }
}
d.getElementById('world').click();const before=d.getElementById('timeline').innerHTML;
const selected=d.querySelector('#source h3').textContent;d.getElementById('language').click();
assert.equal(d.querySelector('#source h3').textContent,selected);
assert.equal(d.querySelector('#timeline rect').getAttribute('data-history'),'short');
assert.notEqual(d.getElementById('timeline').innerHTML,before);
assert.equal(data.audit.empirical_predictions,0);assert.equal(data.audit.scientific_success,false);
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],sourceFragmentsVerified:fragmentChecks,timelineWorldChecks:timelines,
 languageStateChecks:2,network,jsErrors:errors,scientificSuccess:false,
 method:'Bun with explicit jsdom DOM and SVG ports; not a visual browser inspection'};
const output=resolve(dirname(path),'dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
