"""Проверка источника и научно значимых ограничений новой ручной карты EAE."""
import importlib.util
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import PROMPT_PATH, DEPENDENCY_PROMPT_PATH
from domain.article_maps import fingerprint
from domain.evidence_origin_audit import validate_origins
from domain.knowledge_development import model_contract, validate_development_map
from domain.whole_map_input_audit import audit_source_coverage
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools.run_free_prediction import disable_network

ROOT = Path(__file__).resolve().parents[2] / 'eval/whole_map_forecast/eae-primary-map-v1'
REGISTRY = ROOT / 'prepared-v2/sources.json'


@pytest.fixture(scope='module')
def bundle():
    manifest = json.loads(REGISTRY.read_bytes())
    entry = manifest['sources'][-1]
    folder = Path(entry['path']).parent
    result = json.loads((folder / 'map.json').read_bytes())
    authored = json.loads((folder / 'authored.json').read_bytes())
    ids = json.loads((folder / 'key-to-id.json').read_bytes())
    return manifest, entry, folder, result, authored, ids


def block(bundle, key):
    ids, result = bundle[-1], bundle[3]
    return next(k for k in result['graph']['knowledge'] if k['knowledge_id'] == ids[key])


def test_full_source_xml_and_unicode_offsets_are_bound(bundle):
    _, entry, folder, result, _, _ = bundle
    source = result['source']
    assert sha256(source['text'].encode()).hexdigest() == entry['source_sha256']
    packet = json.loads((folder / 'source-origin.json').read_bytes())
    assert packet['doi'] == '10.1038/s41598-017-13984-y'
    assert packet['reference_count'] == 77
    assert sha256((folder / 'article.xml').read_bytes()).hexdigest() == packet['raw_xml_sha256']
    for a, b in zip(source['units'], packet['source']['units'], strict=True):
        assert (a['id'], a['start'], a['end'], a['text']) == (b['id'], b['start'], b['end'], b['text'])
        assert source['text'][a['start']:a['end']] == a['text']
        assert a['end'] <= source['content_end']
    assert 'References' in source['text'][source['content_end']:]


def test_table_cells_and_printed_anomalies_are_retained(bundle):
    authored = bundle[4]
    table = [k for k in authored['knowledge'] if k['key'].startswith('table-') and k['key'] != 'table-discrepancies']
    assert len(table) == 14 and all(len(k['claims']) == 5 for k in table)
    row = next(k for k in table if k['key'] == 'table-p150-TROS')
    assert row['claims'][-1]['attrs']['printed_percentage']['value'] == '85.6%'
    assert row['claims'][-1]['attrs']['case_count']['value'] == 11
    assert row['claims'][-1]['attrs']['denominator']['value'] == 13
    assert row['claims'][-2]['attrs']['SEM']['value'] == 1.67
    row = next(k for k in table if k['key'] == 'table-t30-TROS')
    assert row['claims'][2]['attrs']['mean']['value'] == 5.38
    assert row['claims'][-1]['attrs']['printed_percentage']['value'] == 'NA'
    assert row['claims'][-1]['attrs']['case_count']['value'] is None


def test_local_failure_is_not_erased_by_systemic_success(bundle):
    local = block(bundle, 'local-outcomes')['semantic_frame']
    assert local['logic'] == 'contrast'
    assert 'sustained_protection_not_established' in {s['predicate'] for s in local['statements']}
    clinical = block(bundle, 'therapeutic-clinical')['semantic_frame']
    assert all('intraperitoneally' in ' '.join(s['conditions']) for s in clinical['statements'])
    assert all('day 30' in s['temporal_context'] for s in clinical['statements'])
    assert any('dose and timing' in c for s in local['statements'] for c in s['conditions'])


def test_no_il6_reduction_or_iba1_measurement_is_invented(bundle):
    cytokines = block(bundle, 'csf-cytokine-nondifference')['semantic_frame']
    assert cytokines['logic'] == 'contrast'
    assert {s['predicate'] for s in cytokines['statements']} == {'concentration_increased', 'difference_not_statistically_detected'}
    all_concepts = {c['display_text'] for c in bundle[3]['graph']['concepts']}
    assert not any('IBA1' in c for c in all_concepts)
    non = block(bundle, 'therapeutic-nondifferences')['semantic_frame']['statements']
    assert all(s['predicate'] == 'difference_not_statistically_detected' for s in non)


def test_actions_and_future_tasks_remain_distinct(bundle):
    assert block(bundle, 'therapeutic-dose')['action_status'] == 'performed'
    assert block(bundle, 'tnfr2-mechanism-task')['action_status'] == 'unresolved'
    assert block(bundle, 'bispecific-task')['action_status'] == 'unresolved'
    assert block(bundle, 'summary')['semantic_frame']['statements'][0]['modality'] is not None


def test_all_units_have_accounting_without_claiming_expert_completeness(bundle):
    _, entry, folder, result, _, _ = bundle
    raw = (folder / 'coverage.json').read_bytes()
    audit = audit_source_coverage(result, json.loads(raw), sha256(raw).hexdigest())
    assert audit['source_units'] == 105
    assert not audit['declared_complete_semantic_coverage']
    assert not audit['expert_verified_complete_semantic_coverage']
    assert audit['complete_source_reviewed']
    assert audit['table_cells_exhaustively_formalized']
    assert entry['coverage_artifact']['sha256'] == sha256(raw).hexdigest()


def test_previous_nine_maps_and_origins_unchanged_and_target_absent(bundle):
    manifest = bundle[0]
    old = ROOT.parent / 'analogy-transport-v1/runs/66eba5ff0c5244b5facd4363f932ba2f2c383a70d8fdbfca1f941dc7f91f6a9a'
    assert manifest['sources'][:-1] == json.loads((old / 'source-manifest.json').read_bytes())['sources']
    assert all(s['pmcid'] != 'pmc10000452' for s in manifest['sources'])
    origins = json.loads((ROOT / 'prepared-v2/origin-audit.json').read_bytes())
    assert origins['sources'][:-1] == json.loads((old / 'origin-audit.json').read_bytes())['sources']
    maps = FileForecastMaps(manifest['sources'])
    loaded = [maps.get(s['reference']['article_id'], s['reference']['pipeline_id'], maps.owner, s['reference']['run_id']) for s in manifest['sources']]
    assert len(validate_origins(loaded, origins)['sources']) == 10


def test_visible_edges_exactly_project_justified_groups(bundle):
    result = bundle[3]
    graph = validate_development_map(model_contract(result['graph']), result['source'])
    assert graph == result['graph']
    assert len(graph['nodes']) == len(graph['knowledge'])
    assert {(e['source'], e['target']) for e in graph['edges']} == {(p, t['target']) for t in graph['transitions'] for p in t['sources']}


def test_preparation_reproduces_map_with_transport_forbidden(bundle, monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError('Network or model transport forbidden')
    monkeypatch.setattr(httpx.Client, 'request', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'request', forbidden)
    result, authored = bundle[3], bundle[4]
    before = deepcopy(authored)
    rebuilt = prepare_manual_map(result['article_id'], result['source']['text'], result['source']['sha256'], authored,
        PROMPT_PATH.read_text(encoding='utf-8'), DEPENDENCY_PROMPT_PATH.read_text(encoding='utf-8'))
    assert authored == before and rebuilt['map.json'] == result
    assert result['generation']['external_llm_calls'] == result['generation']['local_llm_calls'] == result['generation']['embedding_calls'] == 0
