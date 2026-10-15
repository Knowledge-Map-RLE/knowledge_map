import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import i18n from '../../../shared/i18n';
import ArticleComparisons from './ArticleComparisons';
import * as api from '../../../services/api/article_comparisons';
import type { ArticleComparison, ComparisonMap, ComparisonPair } from '../../../services/api/article_comparisons';

vi.mock('./ArticleMapCanvas',()=>({ default:({result,selectedKnowledgeId,onKnowledgeSelect}:{result:ComparisonMap;selectedKnowledgeId:string;onKnowledgeSelect:(id:string)=>void})=>
    <div data-testid="comparison-map">{result.graph.nodes[0]?.display_text} · {selectedKnowledgeId}
        <button onClick={()=>onKnowledgeSelect('K1')}>Select {result.article_id}</button></div> }));
vi.mock('../../../services/api/article_comparisons',async()=>({ ...await vi.importActual('../../../services/api/article_comparisons'),
    listComparisonRuns:vi.fn(),listComparisons:vi.fn(),getComparison:vi.fn(),getComparisonPairs:vi.fn(),createComparison:vi.fn() }));
function map(article:string):ComparisonMap{return {article_id:article,pipeline_id:'text_reified',run_id:'run-'+article,
    updated_at:'2026-10-06',input_fingerprint:'hash',builder_version:'3',graph_schema_version:6,
    graph:{schema_version:6,nodes:[{id:'N1',knowledge_id:'K1',rank:0,order:0,block_type:'state',display_text:'English '+article}],edges:[],
        knowledge:[{knowledge_id:'K1',kind:'state',knowledge_kind:'observation',display_text:'English '+article,action_status:null,
            semantic_frame:{},provenance:{unit_ids:['U1']}}]},source:{sha256:'hash',units:[{id:'U1',text:'Source '+article,start:0,end:10}]},
    translations:{ru:{knowledge_labels:{K1:'Русский '+article}}}};}
const pair:ComparisonPair={pair_id:'pair',left_knowledge_id:'K1',right_knowledge_id:'K1',right_article_id:'source',text_score:5,
    semantic_score:.4,hybrid_score:.03,relations:['partial'],coverage_left:0,coverage_right:0,template_score:1,dag_shape_score:0,
    statement_matches:[{left_statement:'S1',right_statement:'S1',relation:'partial',differences:[{field:'units',left:'percent',right:'per1000personyear'}]}]};
const comparison:ArticleComparison={comparison_id:'comparison',created_at:'2026-10-06',references:[{article_id:'target',pipeline_id:'text_reified',run_id:'run-target'}],
    maps:[map('target'),map('source')],analysis:{pair_count:20,normalizer_version:'v1',comparator_version:'v1',rrf_constant:60},
    evaluation:{retrieval_at_k:{},observations:[]}};
beforeEach(async()=>{vi.resetAllMocks();await i18n.changeLanguage('ru');
    vi.mocked(api.listComparisonRuns).mockResolvedValue([{article_id:'target',pipeline_id:'text_reified',run_id:'run-target',title:'Target',updated_at:'date',schema_version:6}]);
    vi.mocked(api.listComparisons).mockResolvedValue({comparisons:[comparison]});vi.mocked(api.getComparison).mockResolvedValue(comparison);
    vi.mocked(api.getComparisonPairs).mockResolvedValue({pairs:[pair],total:20});});
test('defaults to hybrid, pages by ten and switches cached labels without changing semantics',async()=>{
    render(<ArticleComparisons docId="target" enabled/>);await screen.findAllByText(/English source/);
    expect(screen.getByLabelText('Режим')).toHaveValue('hybrid');
    expect(api.getComparisonPairs).toHaveBeenLastCalledWith('comparison',expect.objectContaining({mode:'hybrid',limit:'10',offset:'0'}),expect.any(AbortSignal));
    fireEvent.change(screen.getByLabelText('Язык карты'),{target:{value:'ru'}});await screen.findAllByText(/Русский source/);
    expect(comparison.maps[1].graph.nodes[0].display_text).toBe('English source');
    fireEvent.click(screen.getByRole('button',{name:'Далее'}));await waitFor(()=>expect(api.getComparisonPairs).toHaveBeenLastCalledWith('comparison',expect.objectContaining({offset:'10'}),expect.any(AbortSignal)));
    expect(screen.getByText(/per1000personyear/)).toBeInTheDocument();expect(api.createComparison).not.toHaveBeenCalled();
});
test('late response from the previous article cannot restore its comparison',async()=>{
    let resolve!:(value:ArticleComparison)=>void;
    vi.mocked(api.getComparison).mockImplementation(()=>new Promise(r=>{resolve=r;}));
    const view=render(<ArticleComparisons docId="target" enabled/>);await waitFor(()=>expect(api.getComparison).toHaveBeenCalled());
    vi.mocked(api.listComparisons).mockResolvedValue({comparisons:[]});view.rerender(<ArticleComparisons docId="other" enabled/>);
    await act(async()=>{resolve(comparison);});expect(screen.queryByTestId('comparison-map')).not.toBeInTheDocument();
});
test('load errors are explicit in English UI',async()=>{
    await i18n.changeLanguage('en');vi.mocked(api.listComparisons).mockRejectedValue(new Error('Access denied'));
    render(<ArticleComparisons docId="target" enabled/>);expect(await screen.findByRole('alert')).toHaveTextContent('Access denied');
    expect(screen.getByRole('button',{name:'Compare selected runs'})).toBeDisabled();
});
test('counts unique target blocks separately from pair counts and shared attributes',async()=>{
    vi.mocked(api.getComparison).mockResolvedValue({...comparison,summary:{equivalent_pairs:0,covered_target_statements:[],
        unique_target_knowledge_by_relation:{equivalent:[],partial:['K1','K2','K3'],template:['K1','K2']},shared_attribute_targets:['K2']}});
    render(<ArticleComparisons docId="target" enabled/>);
    expect(await screen.findByText(/частичное сходство.*3.*общий шаблон.*2.*параметры.*1/)).toBeInTheDocument();
});
test('selecting a source block requests its exact pair and ignores an obsolete selection response',async()=>{
    render(<ArticleComparisons docId="target" enabled/>);await screen.findByRole('button',{name:'Select source'});
    let resolve!:(value:{pairs:ComparisonPair[];total:number})=>void;
    vi.mocked(api.getComparisonPairs).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
    fireEvent.click(screen.getByRole('button',{name:'Select source'}));
    expect(api.getComparisonPairs).toHaveBeenLastCalledWith('comparison',expect.objectContaining({source_article_id:'source',right_knowledge_id:'K1',limit:'1'}),expect.any(AbortSignal));
    fireEvent.change(screen.getByLabelText('Режим'),{target:{value:'text'}});
    await waitFor(()=>expect(api.getComparisonPairs).toHaveBeenLastCalledWith('comparison',expect.objectContaining({mode:'text',limit:'10'}),expect.any(AbortSignal)));
    await act(async()=>{resolve({pairs:[{...pair,right_article_id:'obsolete'}],total:1});});
    expect(screen.getByRole('button',{name:'Select source'})).toBeInTheDocument();
});
