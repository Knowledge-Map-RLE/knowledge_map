"""Границы покрытия и неизменяемость исходных карт проверяются до прогноза."""
import json
from copy import deepcopy
from hashlib import sha256
import pytest
from domain.article_maps import ArticleMapError
from domain.whole_map_input_audit import audit_source_coverage, audit_corpus
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tests.test_free_prediction import snapshot


def coverage(m):
    u = m['source']['units'][0]
    m['source']['references_excluded'] = True
    return {'units': [{'unit_id': u['id'], 'start': u['start'], 'end': u['end'],
            'knowledge_ids': [k['knowledge_id'] for k in m['graph']['knowledge']],
            'status': 'selected_propositions_represented', 'reason_ru': None}],
            'complete_semantic_coverage': False, 'references_excluded': True,
            'complete_source_reviewed': True, 'table_cells_exhaustively_formalized': False,
            'source_limitations': ['Табличные ячейки не включены.']}


def test_partial_map_never_becomes_complete_article(tmp_path):
    m, _, _ = snapshot(tmp_path); c = coverage(m); before = deepcopy(m)
    audit = audit_source_coverage(m, c, 'hash')
    assert m == before and audit['canonical_blocks'] == 3
    assert audit['scope'] == 'selected_propositions_only'
    assert not audit['expert_verified_complete_semantic_coverage']
    m['forecast_input_coverage'] = audit
    result = audit_corpus([m], {})
    assert result['all_canonical_blocks_processed'] and result['partial_maps'] == 1
    assert not result['entire_article_semantics_verified']


@pytest.mark.parametrize('change,message', [
    ('coordinate', 'coordinates'), ('unknown', 'Unknown coverage'),
    ('omitted', 'omits canonical'), ('duplicate', 'Duplicate coverage'),
    ('false_complete', 'Partial coverage')])
def test_invalid_coverage_is_rejected(tmp_path, change, message):
    m, _, _ = snapshot(tmp_path); c = coverage(m)
    if change == 'coordinate': c['units'][0]['start'] = 1
    elif change == 'unknown': c['units'][0]['knowledge_ids'].append('absent')
    elif change == 'omitted': c['units'][0]['knowledge_ids'].pop()
    elif change == 'duplicate': c['units'].append(deepcopy(c['units'][0])); m['source']['units'].append({'id': 'U2'})
    elif change == 'false_complete': c['complete_semantic_coverage'] = True
    with pytest.raises(ArticleMapError, match=message): audit_source_coverage(m, c, 'hash')


def test_coverage_requires_direct_unit_provenance(tmp_path):
    m, _, _ = snapshot(tmp_path); c = coverage(m)
    m['graph']['knowledge'][0]['semantic_frame']['statements'][0]['provenance']['unit_ids'] = ['other']
    with pytest.raises(ArticleMapError, match='provenance'): audit_source_coverage(m, c, 'hash')


def test_changed_coverage_file_is_rejected_before_read_receipt(tmp_path):
    m, entry, path = snapshot(tmp_path); c = coverage(m)
    raw=json.dumps(m).encode(); path.write_bytes(raw); entry['file_sha256'] = sha256(raw).hexdigest()
    cp=tmp_path/'coverage.json'; cp.write_text(json.dumps(c), encoding='utf-8')
    entry['coverage_artifact'] = {'path': str(cp), 'sha256': sha256(cp.read_bytes()).hexdigest()}
    port=FileForecastMaps([entry]); loaded=port.get('one','text_reified',port.owner,'run-one')
    assert loaded['forecast_input_coverage']['canonical_blocks'] == 3
    assert json.loads(path.read_bytes()) == m
    cp.write_bytes(cp.read_bytes()+b' ')
    with pytest.raises(ArticleMapError, match='Coverage artifact bytes changed'):
        port.get('one','text_reified',port.owner,'run-one')
    assert len(port.reads) == 1


def test_mixed_prompts_need_explicit_diagnostic_policy(tmp_path):
    m,_,_=snapshot(tmp_path); n=deepcopy(m)
    m['prompt']={'version':'3'}; n['prompt']={'version':'4'}
    with pytest.raises(ArticleMapError, match='Mixed prompt'): audit_corpus([m,n], {})
    result=audit_corpus([m,n], {'formalization_compatibility':'schema6_diagnostic_mixed_prompt_versions'})
    assert result['mixed_prompt_versions'] and not result['confirmatory_corpus']


@pytest.mark.parametrize('status,ids,reason',[
    ('represented',[],None),
    ('represented',['K1'],'Исключён одновременно'),
    ('excluded',['K1'],'Содержит знания'),
    ('excluded',[],None),
])
def test_coverage_status_cannot_hide_unrepresented_source(tmp_path,status,ids,reason):
    m,_,_=snapshot(tmp_path); c=coverage(m)
    if ids: ids=[m['graph']['knowledge'][0]['knowledge_id']]
    c['units'][0].update(status=status,knowledge_ids=ids,reason_ru=reason)
    with pytest.raises(ArticleMapError,match='coverage|Excluded'):
        audit_source_coverage(m,c,'hash')
