// Проверка гипотез, базовых режимов, двух языков и источников без сети.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM,VirtualConsole} from 'jsdom';
const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{virtualConsole:vc}),d=dom.window.document;let network=0,fragments=0,candidates=0;
const data=JSON.parse(d.getElementById('data').textContent),forbidden=()=>{network++;throw Error('Network prohibited');};
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe,img').length,0);
for(const lang of ['ru','en']){
 if(d.documentElement.lang!==lang)d.getElementById('language').click();
 assert.equal(d.documentElement.lang,lang);
 assert.deepEqual([...d.querySelectorAll('#stats strong')].map(n=>Number(n.textContent)),[23,6,2,0]);
 assert.equal(d.querySelectorAll('#metadata tr').length,19);
 for(const [mode,count]of [['semantic',2],['known_union',17],['frequency',11]]){
  const select=d.getElementById('mode');select.value=mode;select.dispatchEvent(new dom.window.Event('change'));
  assert.equal(d.querySelectorAll('#candidates tr').length,count);
  for(const button of d.querySelectorAll('#candidates button')){
   button.click();candidates++;
   for(const pre of d.querySelectorAll('#evidence pre[data-proof]')){
    const f=data.seal.inputs.annotation.evidence[pre.dataset.proof];
    const source=readFileSync(data.seal.inputs.annotation.sources[f.source_id].path,'utf8');
    assert.equal(pre.textContent,Array.from(source).slice(f.start,f.end).join(''));fragments++;
   }
  }
 }
}
const old=d.querySelector('#evidence pre').textContent;
d.getElementById('language').click();
assert.equal(d.getElementById('mode').value,'frequency');assert.equal(d.querySelector('#evidence pre').textContent,old);
assert.equal(data.independent_matches,null);assert.equal(data.graph_gain,null);assert.equal(data.evaluation_performed,false);
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],candidateInspections:candidates,sourceFragmentsVerified:fragments,
 modeCounts:{semantic:2,known_union:17,frequency:11},metadataCandidates:19,languageStateChecks:2,
 evaluationPerformed:false,network,jsErrors:errors,method:'Bun with explicit jsdom DOM ports; not a visual browser inspection'};
const output=resolve(dirname(path),'dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
