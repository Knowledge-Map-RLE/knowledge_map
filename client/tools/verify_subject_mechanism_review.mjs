// Автономная проверка RU/EN, графа, фрагментов и иллюстрации модели.
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM,VirtualConsole} from 'jsdom';
const path=resolve(process.argv[2]),html=readFileSync(path,'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{virtualConsole:vc}),d=dom.window.document;
let network=0;const forbidden=()=>{network++;throw Error('Network forbidden');};
const data=JSON.parse(d.getElementById('data').textContent);
const script=[...d.querySelectorAll('script')].filter(s=>s.type!=='application/json').map(s=>s.textContent).join('\n');
new Function('document','window','fetch','XMLHttpRequest','WebSocket',script)(d,dom.window,forbidden,forbidden,forbidden);
assert.equal(d.querySelectorAll('script[src],link[href],iframe,img').length,0);
let nodes=0,edges=0,fragments=0;
for(const lang of ['ru','en']){
  if(d.documentElement.lang!==lang)d.getElementById('language').click();
  assert.equal(d.documentElement.lang,lang);
  assert.deepEqual([...d.querySelectorAll('#stats strong')].map(n=>Number(n.textContent)),[1,1,7,0]);
  assert.equal(d.querySelectorAll('#profiles tr').length,7);
  assert.equal(d.querySelectorAll('#nodes .node').length,5);
  assert.equal(d.querySelectorAll('#edges .edge').length,4);
  d.getElementById('background').click();
  assert.equal(d.querySelector('#detail a').href,'https://pmc.ncbi.nlm.nih.gov/articles/PMC3507991/');
  const expected=data.seal.generation.candidates[0].graph.edges;
  for(const line of d.querySelectorAll('#edges .edge')){
    assert.ok(expected.some(e=>e.source===line.dataset.source&&e.target===line.dataset.target));edges++;
  }
  for(const node of d.querySelectorAll('#nodes .node')){
    node.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter'}));nodes++;
    assert.ok(d.querySelector('#detail pre').textContent.includes('predicate'));
    const b=data.seal.inputs.knowledge.find(k=>k.knowledge_id===node.dataset.id);
    if(b){
      assert.equal(d.querySelector('#detail h3').textContent,lang==='ru'?b.text_ru:b.text);
      for(const key of b.provenance){
        const f=data.evidence.fragments[key];if(!f)continue;
        const source=readFileSync(data.evidence.sources[f.source_id].path,'utf8');
        assert.equal(Array.from(source).slice(f.start,f.end).join(''),f.text);
        assert.ok(d.getElementById('detail').textContent.includes(f.text));fragments++;
      }
    }else assert.ok(d.getElementById('detail').textContent.includes(lang==='ru'?'Нерешённая задача':'Unresolved task'));
  }
  for(const [key,value]of [['low',2],['high',4],['long',4],['short',2]]){
    d.getElementById(key).value=value;d.getElementById(key).dispatchEvent(new dom.window.Event('input'));
  }
  d.getElementById('calculate').click();assert.ok(d.getElementById('model-result').textContent.startsWith('2.000000 → 1.000000'));
  d.getElementById('short').value='4';d.getElementById('calculate').click();
  assert.ok(d.getElementById('model-result').textContent=== (lang==='ru'?'Нужны H≥L>0 и 0<новый интервал<исходного.':'Require H≥L>0 and 0<new interval<original interval.'));
}
const frameBefore=d.querySelector('#detail pre').textContent;
d.getElementById('low').value='1';d.getElementById('low').dispatchEvent(new dom.window.Event('input'));
d.getElementById('language').click();
assert.equal(d.querySelector('#detail pre').textContent,frameBefore);
assert.equal(d.getElementById('low').value,'1');
for(const f of Object.values(data.evidence.fragments)){
  const source=readFileSync(data.evidence.sources[f.source_id].path,'utf8');
  assert.equal(Array.from(source).slice(f.start,f.end).join(''),f.text);fragments++;
}
assert.equal(network,0);assert.deepEqual(errors,[]);
assert.equal(data.evaluation.scientific_success,false);
const receipt={languages:['ru','en'],graphNodesInspected:nodes,graphEdgesVerified:edges,fragmentsVerified:fragments,
  modelBoundaryChecks:4,languageStateChecks:2,network,jsErrors:errors,scientificSuccess:false,
  method:'Bun with explicit jsdom DOM and SVG ports; not visual browser inspection'};
const output=resolve(dirname(path),'dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
