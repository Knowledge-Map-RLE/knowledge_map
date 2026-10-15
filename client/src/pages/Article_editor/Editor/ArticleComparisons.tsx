import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { comparisonDisplayMap, createComparison, getComparison, getComparisonPairs, listComparisons, listComparisonRuns,
    type ArticleComparison, type ComparisonMap, type ComparisonMode, type ComparisonPair, type ComparisonRun, type ComparisonSummary,
    type MapReference } from '../../../services/api/article_comparisons';
import ArticleMapCanvas from './ArticleMapCanvas';
import styles from './ArticleComparisons.module.css';

const refOf = (run: ComparisonRun): MapReference => ({ article_id: run.article_id, pipeline_id: 'text_reified', run_id: run.run_id });
const relations = ['equivalent', 'partial', 'template', 'topical', 'contradiction', 'insufficient'];
const ruRelations: Record<string, string> = { equivalent:'Эквивалентность', partial:'Частичное совпадение', template:'Общий шаблон',
    topical:'Тематическая близость', contradiction:'Противоречие', insufficient:'Недостаточно данных' };
export default function ArticleComparisons({ docId, enabled }: { docId: string | null; enabled: boolean }) {
    const { i18n } = useTranslation(); const ru = i18n.resolvedLanguage === 'ru';
    const l = (a: string, b: string) => ru ? a : b;
    const [runs,setRuns] = useState<ComparisonRun[]>([]), [saved,setSaved] = useState<ComparisonSummary[]>([]);
    const [target,setTarget] = useState(''), [sourceRuns,setSourceRuns] = useState<string[]>([]), [chosen,setChosen] = useState('');
    const [comparison,setComparison] = useState<ArticleComparison | null>(null), [pairs,setPairs] = useState<ComparisonPair[]>([]);
    const [mode,setMode] = useState<ComparisonMode>('hybrid'), [left,setLeft] = useState(''), [source,setSource] = useState('');
    const [relation,setRelation] = useState(''), [offset,setOffset] = useState(0), [total,setTotal] = useState(0);
    const [selected,setSelected] = useState<ComparisonPair | null>(null), [locale,setLocale] = useState<'en'|'ru'>('en');
    const [error,setError] = useState(''), [busy,setBusy] = useState(false);
    const generation = useRef(0), build = useRef<AbortController | null>(null);
    const selectionRequest = useRef<AbortController | null>(null);
    useEffect(() => {
        const controller = new AbortController(); const version = ++generation.current;
        build.current?.abort(); setComparison(null); setPairs([]); setSelected(null); setChosen(''); setSaved([]); setRuns([]);
        setTarget(''); setSourceRuns([]); setError(''); setBusy(false); setLocale('en'); setOffset(0); setSource(''); setRelation('');
        if (!docId || !enabled) return () => controller.abort();
        void Promise.all([listComparisonRuns(controller.signal), listComparisons(docId,controller.signal)]).then(([available,results]) => {
            if (controller.signal.aborted || version !== generation.current) return;
            setRuns(available); setSaved(results.comparisons);
            setTarget(available.find(r=>r.article_id===docId)?.run_id || '');
            setChosen(results.comparisons[0]?.comparison_id || '');
        }).catch(e=>{ if (!controller.signal.aborted) setError(String(e)); });
        return () => { controller.abort(); build.current?.abort(); };
    },[docId,enabled]);
    useEffect(() => {
        const controller = new AbortController(); setComparison(null); setPairs([]); setSelected(null); setError('');
        if (chosen) void getComparison(chosen,controller.signal).then(result=>{
            if (controller.signal.aborted) return;
            setComparison(result); setLeft(result.maps[0].graph.knowledge?.[0]?.knowledge_id || ''); setOffset(0);
        }).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
        return ()=>controller.abort();
    },[chosen]);
    useEffect(()=>{
        selectionRequest.current?.abort();
        const controller=new AbortController(); setPairs([]); setSelected(null); setTotal(0);
        if(comparison && left) void getComparisonPairs(comparison.comparison_id,{mode,left_knowledge_id:left,offset:String(offset),limit:'10',
            ...(source?{source_article_id:source}:{}),...(relation?{relation}:{})},controller.signal).then(result=>{
                if(controller.signal.aborted)return;setPairs(result.pairs);setTotal(result.total);setSelected(result.pairs[0]||null);
            }).catch(e=>{if(!controller.signal.aborted)setError(String(e));});
        return ()=>{controller.abort();selectionRequest.current?.abort();};
    },[comparison,left,mode,offset,source,relation]);
    const baseMap = comparison?.maps[0], rightMap = comparison?.maps.find(m=>m.article_id===selected?.right_article_id);
    const leftDisplay = useMemo(()=>baseMap?comparisonDisplayMap(baseMap,locale):null,[baseMap,locale]);
    const rightDisplay = useMemo(()=>rightMap?comparisonDisplayMap(rightMap,locale):null,[rightMap,locale]);
    const label=(map:ComparisonMap|undefined,id:string)=>locale==='ru'?(map?.translations?.ru?.knowledge_labels[id]||map?.graph.knowledge?.find(k=>k.knowledge_id===id)?.display_text):map?.graph.knowledge?.find(k=>k.knowledge_id===id)?.display_text;
    async function selectRight(id: string) {
        if (!comparison || !rightMap) return;
        selectionRequest.current?.abort(); const controller = new AbortController(); selectionRequest.current = controller;
        try {
            const result = await getComparisonPairs(comparison.comparison_id, {mode,left_knowledge_id:left,
                source_article_id:rightMap.article_id,right_knowledge_id:id,limit:'1'},controller.signal);
            if (!controller.signal.aborted) setSelected(result.pairs[0] || null);
        } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    }
    async function create() {
        const targetRun=runs.find(r=>r.run_id===target); const selectedRuns=runs.filter(r=>sourceRuns.includes(r.run_id));
        if(!targetRun||!selectedRuns.length)return;
        const controller=new AbortController(),version=generation.current;build.current=controller;setBusy(true);setError('');
        try{const result=await createComparison(refOf(targetRun),selectedRuns.map(refOf),controller.signal);
            if(controller.signal.aborted||version!==generation.current)return;
            setSaved(prev=>[result,...prev.filter(r=>r.comparison_id!==result.comparison_id)]);setChosen(result.comparison_id);
        }catch(e){if(!controller.signal.aborted)setError(String(e));}
        finally{if(version===generation.current)setBusy(false);}
    }
    if(!docId||!enabled)return <div className={styles.root}>{l('Выберите статью и войдите в систему.','Select an article and sign in.')}</div>;
    const sourceChoices=runs.filter(r=>r.article_id!==runs.find(x=>x.run_id===target)?.article_id);
    const selectedArticles=sourceChoices.filter(r=>sourceRuns.includes(r.run_id)).map(r=>r.article_id);
    return <section className={styles.root} aria-label={l('Сравнение статей','Article comparison')}>
        <div className={styles.toolbar}><label>{l('Целевая версия','Target run')} <select aria-label={l('Целевая версия','Target run')} value={target} onChange={e=>{setTarget(e.target.value);setSourceRuns([]);}}>
            <option value="">{l('Выберите запуск','Select a run')}</option>{runs.filter(r=>r.article_id===docId).map(r=><option key={r.run_id} value={r.run_id}>{r.title} · {r.updated_at} · {r.run_id.slice(0,8)}</option>)}</select></label></div>
        <details className={styles.sources}><summary>{l('Версии источников','Source runs')} ({sourceRuns.length})</summary>
            {sourceChoices.map(r=><label key={r.run_id}><input type="checkbox" checked={sourceRuns.includes(r.run_id)}
                disabled={!sourceRuns.includes(r.run_id)&&selectedArticles.includes(r.article_id)}
                onChange={e=>setSourceRuns(prev=>e.target.checked?[...prev,r.run_id]:prev.filter(id=>id!==r.run_id))}/>{r.title} · {r.updated_at} · {r.run_id.slice(0,8)}</label>)}</details>
        <div className={styles.toolbar}><button className={styles.button} disabled={busy||!target||!sourceRuns.length} onClick={()=>void create()}>{busy?l('Сравнение…','Comparing…'):l('Сравнить выбранные версии','Compare selected runs')}</button>
            <select aria-label={l('Сохранённое сравнение','Saved comparison')} value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">{l('Сохранённое сравнение','Saved comparison')}</option>{saved.map(r=><option key={r.comparison_id} value={r.comparison_id}>{r.created_at} · {r.references.length-1} {l('источников','sources')} · {r.comparison_id.slice(0,8)}</option>)}</select></div>
        {error&&<div role="alert" className={styles.error}>{error}</div>}
        {!comparison&&<p className={styles.note}>{l('Выберите сохранённое сравнение или создайте его по явным версиям схемы 6. Модельные вызовы не используются.','Select a saved comparison or create one from explicit schema-6 runs. No model calls are used.')}</p>}
        {comparison&&<>
            <p className={styles.note}>{comparison.analysis.pair_count} {l('пар','pairs')} · BM25 / {l('семантика','semantics')} / RRF {comparison.analysis.rrf_constant}. {l('Автоматическое сходство требует экспертной проверки.','Automated similarity requires expert review.')}</p>
            {comparison.summary?.unique_target_knowledge_by_relation && <p className={styles.note}>
                {l('Блоки цели: полное совпадение','Target blocks: equivalent')} {comparison.summary.unique_target_knowledge_by_relation.equivalent?.length || 0}
                {' · '}{l('частичное сходство','partial similarity')} {comparison.summary.unique_target_knowledge_by_relation.partial?.length || 0}
                {' · '}{l('общий шаблон','shared template')} {comparison.summary.unique_target_knowledge_by_relation.template?.length || 0}
                {' · '}{l('совпавшие числовые/иные параметры','shared numerical/other attributes')} {comparison.summary.shared_attribute_targets?.length || 0}.
                {' '}{l('Категории могут пересекаться; совпадение параметра не покрывает всё утверждение.','Categories may overlap; a shared attribute does not cover the whole assertion.')}
            </p>}
            <div className={styles.toolbar}><select aria-label={l('Режим','Mode')} value={mode} onChange={e=>{setMode(e.target.value as ComparisonMode);setOffset(0);}}>{['hybrid','text','semantic'].map(m=><option key={m} value={m}>{m==='hybrid'?l('Совместный','Hybrid'):m==='text'?'BM25':l('Семантический','Semantic')}</option>)}</select>
                <select aria-label={l('Знание цели','Target knowledge')} value={left} onChange={e=>{setLeft(e.target.value);setOffset(0);}}>{baseMap?.graph.knowledge?.map(k=><option key={k.knowledge_id} value={k.knowledge_id}>{k.knowledge_id} · {label(baseMap,k.knowledge_id)}</option>)}</select>
                <select aria-label={l('Источник','Source')} value={source} onChange={e=>{setSource(e.target.value);setOffset(0);}}><option value="">{l('Все источники','All sources')}</option>{comparison.maps.slice(1).map(m=><option key={m.article_id} value={m.article_id}>{m.article_id}</option>)}</select>
                <select aria-label={l('Отношение','Relation')} value={relation} onChange={e=>{setRelation(e.target.value);setOffset(0);}}><option value="">{l('Все отношения','All relations')}</option>{relations.map(r=><option key={r} value={r}>{ru?ruRelations[r]:r}</option>)}</select>
                <select aria-label={l('Язык карты','Map language')} value={locale} onChange={e=>setLocale(e.target.value as 'en'|'ru')}><option value="en">English</option><option value="ru">Русский</option></select></div>
            <div className={styles.matches}><table className={styles.table}><thead><tr><th>{l('Соответствие','Match')}</th><th>{l('Оценки и отношения','Scores and relations')}</th></tr></thead><tbody>{pairs.map(p=>{
                const m=comparison.maps.find(m=>m.article_id===p.right_article_id);return <tr key={p.pair_id} data-selected={p.pair_id===selected?.pair_id} tabIndex={0} onClick={()=>setSelected(p)} onKeyDown={e=>{if(e.key==='Enter')setSelected(p);}}>
            <td>{p.right_article_id.split('-')[2]} · {p.right_knowledge_id}<br/>{label(m,p.right_knowledge_id)}</td><td>{p.relations.map(r=>ru?ruRelations[r]:r).join(', ')}<br/>BM25 {p.text_score.toFixed(2)} · S {p.semantic_score.toFixed(3)} · RRF {p.hybrid_score.toFixed(4)}<br/>{l('Покрытие','Coverage')} {(100*p.coverage_left).toFixed(0)}% / {(100*p.coverage_right).toFixed(0)}%</td></tr>})}</tbody></table></div>
            <div className={styles.toolbar}><button className={styles.button} disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-10))}>{l('Назад','Previous')}</button><span>{total?offset+1:0}–{Math.min(offset+10,total)} / {total}</span><button className={styles.button} disabled={offset+10>=total} onClick={()=>setOffset(x=>x+10)}>{l('Далее','Next')}</button></div>
            <div className={styles.grid}><div className={styles.map}>{leftDisplay&&<ArticleMapCanvas result={leftDisplay} selectedKnowledgeId={left} onKnowledgeSelect={id=>{setLeft(id);setOffset(0);}} hideDetails/>}</div><div className={styles.map}>{rightDisplay&&<ArticleMapCanvas result={rightDisplay} selectedKnowledgeId={selected?.right_knowledge_id} onKnowledgeSelect={id=>void selectRight(id)} hideDetails/>}</div></div>
            {selected&&<><p className={styles.note}>{l('Шаблон / форма цепочки (не эквивалентность фактов)','Template / chain shape (not factual equivalence)')}: {selected.template_score.toFixed(3)} / {selected.dag_shape_score.toFixed(3)}</p>
                <details><summary>{l('Утверждения и расхождения','Statements and differences')}</summary><pre className={styles.fragment}>{JSON.stringify(selected.statement_matches,null,2)}</pre></details>
                <div className={styles.grid}><Fragments map={baseMap} knowledgeId={left} title={l('Источник целевого знания','Target source')}/><Fragments map={rightMap} knowledgeId={selected.right_knowledge_id} title={l('Источник соответствия','Matched source')}/></div></>}
            <details><summary>{l('Контроль цитирования','Citation controls')}</summary><pre className={styles.fragment}>{JSON.stringify(comparison.evaluation,null,2)}</pre></details>
        </>}
    </section>;
}
function Fragments({map,knowledgeId,title}:{map?:ComparisonMap;knowledgeId:string;title:string}){
    const units=map?.graph.knowledge?.find(k=>k.knowledge_id===knowledgeId)?.provenance.unit_ids||[];
    return <div><h4>{title}</h4>{map?.source.units.filter(u=>units.includes(u.id)).map(u=><details key={u.id}><summary>{u.id} · {u.start}–{u.end} · Unicode</summary><pre className={styles.fragment}>{u.text}</pre>{map.source_attachments?.filter(a=>a.unit_id===u.id).map((a,i)=><pre key={i} className={styles.fragment}>{a.text}</pre>)}</details>)}</div>;
}
