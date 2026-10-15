// Проверка локального двуязычного отчёта и SVG, без внешних ресурсов.
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
assert.equal(d.getElementById('mode').value,'dependencies');
let inspected=0,proofs=0,nodes=0,edges=0,languageState=0;
function change(id,value){const s=d.getElementById(id);s.value=value;s.dispatchEvent(new dom.window.Event('change'))}
function proof(){
  const id=d.getElementById('fragment').dataset.proof,p=data.evidence[id];
  assert.equal(d.getElementById('fragment').textContent,Array.from(data.texts[p.source_id]).slice(p.start,p.end).join(''));
  assert.equal(d.querySelector('#full-text mark').textContent,p.text);
  assert.equal(d.getElementById('full-text').textContent,data.texts[p.source_id]);proofs++;
}
function inspect(b){b.click();inspected++;proof()}
for(const lang of ['ru','en']){
  d.getElementById(lang).click();assert.equal(d.documentElement.lang,lang);
  assert.deepEqual([...d.querySelectorAll('#stats strong')].map(n=>Number(n.textContent)),[12,23,5,0]);
  assert.equal(d.querySelectorAll('#operations tr').length,5);
  change('graph-choice','foundation');
  assert.equal(d.querySelectorAll('#graph g').length,12);
  assert.equal(d.querySelectorAll('#graph path[marker-end]').length,2);
  edges+=2;
  for(const g of d.querySelectorAll('#graph g')){
    g.dispatchEvent(new dom.window.MouseEvent('click'));nodes++;
    assert.equal(d.getElementById('node-title').textContent,g.dataset.node);
    assert.ok(d.getElementById('node-frame').textContent.includes('conditions'));
  }
  for(const [id,p]of Object.entries(data.derivations)){
    change('graph-choice',id);
    assert.equal(d.querySelectorAll('#graph g').length,p.graph.nodes.length);
    assert.equal(d.querySelectorAll('#graph path[marker-end]').length,p.graph.edges.length);
    edges+=p.graph.edges.length;
    for(const g of d.querySelectorAll('#graph g')){
      g.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter'}));nodes++;
      assert.equal(d.getElementById('node-detail').hidden,false);
      assert.ok(d.getElementById('node-frame').textContent.length>10);
    }
  }
  const before=d.getElementById('node-frame').textContent;
  d.getElementById(lang==='ru'?'en':'ru').click();
  assert.equal(d.getElementById('node-detail').hidden,false);
  assert.equal(d.getElementById('node-frame').textContent,before);languageState++;
  d.getElementById(lang).click();
  for(const mode of ['articles','comparison','derivation','dependencies']){
    change('mode',mode);change('fold','all');
    assert.equal(d.querySelectorAll('#cases tr').length,23);
    assert.equal(d.querySelectorAll('#cases .good').length,data.evaluation.totals[mode].qualitative_pattern_match||0);
    for(const b of d.querySelectorAll('#cases button'))inspect(b);
    for(const f of data.evaluation.folds){
      change('fold',f.fold_id);
      assert.equal(d.querySelectorAll('#cases tr').length,f.modes[mode].rows.length);
      assert.ok([...d.querySelectorAll('#cases tr')].every(n=>n.dataset.fold===f.fold_id));
    }
    change('fold','all');
  }
  for(const b of d.querySelectorAll('#operations button')){
    inspect(b);
    for(const p of d.querySelectorAll('#proof-buttons button'))inspect(p);
  }
  for(const b of d.querySelectorAll('#repair-buttons button'))inspect(b);
  change('mode','dependencies');change('fold','all');
  const match=d.querySelector('#cases tr:has(.good)');inspect(match.querySelector('button'));
  assert.equal(d.querySelectorAll('#premises button').length,2);
  const audit=d.getElementById('audit').textContent;
  d.getElementById(lang==='ru'?'en':'ru').click();
  assert.equal(d.querySelectorAll('#premises button').length,2);
  assert.equal(d.getElementById('audit').textContent,audit);languageState++;
  d.getElementById(lang).click();
  for(const b of d.querySelectorAll('#premises button'))inspect(b);
}
assert.equal(network,0);assert.deepEqual(errors,[]);
const receipt={languages:['ru','en'],foundationBlocks:12,sourceObservations:23,conditionalConsequences:5,sourceRepairs:5,
  inspected,verifiedFragments:proofs,graphNodesInspected:nodes,graphEdgesVerified:edges,languageStateChecks:languageState,
  network,jsErrors:errors,method:'Bun with explicit jsdom DOM and SVG ports; not a visual browser inspection'};
const output=resolve(path,'../dom-validation.json'),raw=JSON.stringify(receipt,null,2);
if(existsSync(output))assert.equal(readFileSync(output,'utf8'),raw);else writeFileSync(output,raw);
process.stdout.write(JSON.stringify(receipt)+'\n');dom.window.close();
