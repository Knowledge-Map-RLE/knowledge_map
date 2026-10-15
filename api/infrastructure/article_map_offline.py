"""Автономное представление карты; все данные и ресурсы встроены в HTML."""
from __future__ import annotations

import json


def render_article_map(result: dict) -> str:
    payload = json.dumps(result, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    from html import escape
    title = escape(result.get("article_title", result["article_id"]))
    return TEMPLATE.replace("__PAYLOAD__", payload).replace("PMC10000452 · Cretan Aging Cohort", title).replace(
        "PMC10000452 — Карта знаний / Knowledge map", title + " — Карта знаний / Knowledge map")


TEMPLATE = r'''<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMC10000452 — Карта знаний / Knowledge map</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#17243b;font:14px system-ui,sans-serif}
header{height:104px;padding:12px 18px;background:white;border-bottom:1px solid #ced7e3;display:flex;flex-direction:column;gap:10px}
.line{display:flex;align-items:center;gap:10px;flex-wrap:wrap}h1{font-size:18px;margin:0}small{color:#52647c}
button,select,input{font:inherit;border:1px solid #a4b5cd;border-radius:7px;padding:7px 12px;background:white;color:#17243b}
button{cursor:pointer;background:#e8efff}button:hover{background:#cedcff}button:focus-visible{outline:3px solid #587de5}
input{min-width:250px}main{display:flex;height:calc(100vh - 104px)}#view{flex:1;position:relative;overflow:hidden;touch-action:none;background-image:radial-gradient(#c4cfdd 1px,transparent 1px);background-size:20px 20px}
svg{width:100%;height:100%;display:block}.edge{fill:none;stroke:#8796ae;stroke-width:2;cursor:pointer}.edge:hover,.edge.selected{stroke:#265cdb;stroke-width:4}
.hit{stroke:transparent;stroke-width:16;fill:none;cursor:pointer}.card{height:100%;width:100%;padding:14px;border:2px solid #8db9c9;border-radius:10px;background:#eefbff;box-shadow:0 3px 8px #10203814;cursor:pointer;overflow:hidden;white-space:normal;line-height:1.45;font-size:14px}
.card.action{border-color:#d4a565;background:#fff5e4}.card.selected{border-color:#315ce1;box-shadow:0 0 0 3px #315ce12b}.card b{display:block;color:#52647c;font-size:11px;margin-bottom:7px}
aside{width:410px;flex-shrink:0;padding:18px;overflow:auto;background:white;border-left:1px solid #ced7e3}aside h2{font-size:18px;margin:0 0 12px}aside h3{font-size:14px;margin:18px 0 8px}
blockquote{margin:8px 0;border-left:3px solid #91a9d1;padding:8px 10px;background:#f2f5fa;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}
pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:14px}p{line-height:1.5}#full{display:none;position:absolute;inset:20px;background:white;z-index:5;overflow:auto;padding:22px;border:1px solid #a4b5cd;border-radius:10px;white-space:pre-wrap;line-height:1.6}#hint{position:absolute;bottom:14px;left:14px;background:#ffffffeb;border:1px solid #ced7e3;padding:8px;border-radius:6px}#matches{max-width:240px}
@media(max-width:900px){aside{width:300px}header{height:140px}main{height:calc(100vh - 140px)}input{min-width:150px;width:170px}}
</style>
<header><div class="line"><h1>PMC10000452 · Cretan Aging Cohort</h1><small id="stats"></small></div><div class="line">
<button id="fit">Вместить / Fit</button><button id="plus">+</button><button id="minus">−</button>
<select id="language" aria-label="Map language"><option value="en">English</option><option value="ru">Русский</option></select>
<input id="search" placeholder="Найти знание / Find knowledge" aria-label="Find knowledge"><select id="matches" aria-label="Search matches"><option>Поиск / Search</option></select>
<button id="source">Полный источник / Full source</button><small>Codex · schema 6 · требует экспертной проверки</small>
</div></header><main><div id="view"><svg aria-label="Knowledge development DAG"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#8796ae"/></marker></defs><g id="scene"></g></svg><div id="full"></div><div id="hint">Колесо: масштаб · Перетаскивание: перемещение · Щелчок: источник</div></div><aside id="details"></aside></main>
<script id="data" type="application/json">__PAYLOAD__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent),graph=data.graph,view=document.getElementById('view'),scene=document.getElementById('scene'),panel=document.getElementById('details');
const byId=new Map(graph.nodes.map(n=>[n.id,n])),knowledge=new Map(graph.knowledge.map(k=>[k.knowledge_id,k])),units=new Map(data.source.units.map(u=>[u.id,u]));
let language='en',scale=1,tx=20,ty=20,selected=null,drag=null;const positions=new Map(),neighbor=new Map(graph.nodes.map(n=>[n.id,[]]));
for(const e of graph.edges){neighbor.get(e.source).push(e.target);neighbor.get(e.target).push(e.source)}
const groups=[],seen=new Set();for(const n of graph.nodes){if(seen.has(n.id))continue;let queue=[n.id],ids=[];seen.add(n.id);while(queue.length){let id=queue.shift();ids.push(id);for(const next of neighbor.get(id))if(!seen.has(next)){seen.add(next);queue.push(next)}}groups.push(ids)}
groups.sort((a,b)=>b.length-a.length);let offset=40;
function label(n){return language==='ru'?data.translations.ru.labels[n.id]:knowledge.get(n.knowledge_id).display_text}
// Компоненты разнесены по полосам; внутри слоя сохраняется канонический порядок.
for(const ids of groups){let nextY=new Map(),bottom=offset;for(const n of ids.map(id=>byId.get(id)).sort((a,b)=>a.rank-b.rank||a.order-b.order)){let h=Math.max(120,60+Math.ceil(Math.max(knowledge.get(n.knowledge_id).display_text.length,data.translations.ru.labels[n.id].length)/38)*20),y=nextY.get(n.rank)||offset;positions.set(n.id,{x:40+n.rank*380,y,w:320,h});nextY.set(n.rank,y+h+30);bottom=Math.max(bottom,y+h)}offset=bottom+70}
const width=Math.max(...[...positions.values()].map(p=>p.x+p.w))+50,height=offset;const svgns='http://www.w3.org/2000/svg';
function svg(tag,attrs){const el=document.createElementNS(svgns,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);return el}
function update(){scene.setAttribute('transform',`translate(${tx} ${ty}) scale(${scale})`)}
function fit(){scale=Math.min(view.clientWidth/width,view.clientHeight/height,1)*.94;tx=(view.clientWidth-width*scale)/2;ty=(view.clientHeight-height*scale)/2;update()}
function zoom(f,x=view.clientWidth/2,y=view.clientHeight/2){const old=scale;scale=Math.max(.025,Math.min(3,scale*f));tx=x-(x-tx)*scale/old;ty=y-(y-ty)*scale/old;update()}
function element(tag,value,parent=panel){const el=document.createElement(tag);if(value!==undefined)el.textContent=value;parent.append(el);return el}
function quote(ids){for(const id of [...new Set(ids)]){const u=units.get(id);if(!u)continue;element('small',`${id} · Unicode [${u.start}, ${u.end})`);element('blockquote',u.text);for(const a of data.source_attachments||[])if(a.unit_id===id){element('small','Приложение / Source attachment · '+a.xml_asset);element('blockquote',a.text)}}}
function show(){panel.replaceChildren();if(!selected){element('h2','Карта развития знаний');element('p','Выберите блок или стрелку. Голубые блоки — состояния, оранжевые — действия. Скрытая семантика не образует стрелки автоматически.');element('p','Несколько входов одного обоснования используются совместно; разные обоснования — альтернативные пути.');element('small',`run ${data.run_id}`);return}
if(selected.kind==='node'){const n=byId.get(selected.id),k=knowledge.get(n.knowledge_id);element('h2',`${n.id} · ${k.knowledge_id}`);element('p',label(n));element('small',`${k.kind} / ${k.knowledge_kind}${k.action_status?' / '+k.action_status:''}`);element('h3','Исходные фрагменты / Source fragments');quote(k.provenance.unit_ids);const detail=element('details');element('summary','Семантический frame (English)',detail);element('pre',JSON.stringify(k.semantic_frame,null,2),detail);}
else{element('h2',`${selected.source} → ${selected.target}`);const transitions=graph.transitions.filter(t=>t.target===selected.target&&t.sources.includes(selected.source));for(const t of transitions){element('h3',`${t.id} · ${t.usage}`);element('p',`Совместные входы / Joint inputs: ${t.sources.join(' + ')} → ${t.target}`);element('p',t.reason);if(t.conditions.length)element('p',t.conditions.join('; '));quote(t.unit_ids)}}}
function draw(){scene.replaceChildren();for(const e of graph.edges){const a=positions.get(e.source),b=positions.get(e.target),x=a.x+a.w,y=a.y+a.h/2,endY=b.y+b.h/2,d=`M${x},${y} C${x+35},${y} ${b.x-35},${endY} ${b.x},${endY}`;const path=svg('path',{d,class:'edge'+(selected?.source===e.source&&selected?.target===e.target?' selected':''),'marker-end':'url(#arrow)'});scene.append(path);const hit=svg('path',{d,class:'hit'});hit.addEventListener('click',ev=>{ev.stopPropagation();selected={kind:'edge',...e};draw();show()});scene.append(hit)}
for(const n of graph.nodes){const p=positions.get(n.id),fo=svg('foreignObject',{x:p.x,y:p.y,width:p.w,height:p.h}),card=document.createElementNS('http://www.w3.org/1999/xhtml','div');card.className='card '+n.kind+(selected?.id===n.id?' selected':'');const b=document.createElement('b');b.textContent=`${n.id} · ${n.knowledge_id} · ${n.kind}${knowledge.get(n.knowledge_id).action_status?' / '+knowledge.get(n.knowledge_id).action_status:''}`;card.append(b,document.createTextNode(label(n)));card.addEventListener('click',ev=>{ev.stopPropagation();selected={kind:'node',id:n.id};draw();show()});fo.append(card);scene.append(fo)}update()}
function focus(id){const p=positions.get(id);if(!p)return;selected={kind:'node',id};scale=1;tx=view.clientWidth/2-(p.x+p.w/2);ty=view.clientHeight/2-(p.y+p.h/2);draw();show()}
function search(){const q=document.getElementById('search').value.toLocaleLowerCase(),list=document.getElementById('matches');list.replaceChildren();const empty=document.createElement('option');empty.textContent='Выбрать / Select';empty.value='';list.append(empty);for(const n of graph.nodes.filter(n=>`${n.id} ${label(n)}`.toLocaleLowerCase().includes(q)).slice(0,50)){const option=document.createElement('option');option.value=n.id;option.textContent=`${n.id}: ${label(n).slice(0,75)}`;list.append(option)}}
document.getElementById('stats').textContent=`${graph.knowledge.length} знаний · ${graph.edges.length} связей · ${graph.analysis.depth} слоёв`;
document.getElementById('fit').onclick=fit;document.getElementById('plus').onclick=()=>zoom(1.3);document.getElementById('minus').onclick=()=>zoom(1/1.3);document.getElementById('search').oninput=search;document.getElementById('matches').onchange=e=>focus(e.target.value);
document.getElementById('language').onchange=e=>{language=e.target.value;draw();show();search()};const full=document.getElementById('full');full.textContent=data.source.text;document.getElementById('source').onclick=()=>{full.style.display=full.style.display==='block'?'none':'block'};
view.addEventListener('wheel',e=>{if(full.style.display==='block')return;e.preventDefault();const rect=view.getBoundingClientRect();zoom(e.deltaY<0?1.12:1/1.12,e.clientX-rect.left,e.clientY-rect.top)},{passive:false});
view.addEventListener('pointerdown',e=>{if(e.target.closest('.card,.hit,#full'))return;drag={x:e.clientX,y:e.clientY,tx,ty};view.setPointerCapture(e.pointerId)});view.addEventListener('pointermove',e=>{if(drag){tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;update()}});view.addEventListener('pointerup',()=>drag=null);view.addEventListener('pointercancel',()=>drag=null);
window.addEventListener('resize',fit);draw();show();search();fit();
</script></html>'''
