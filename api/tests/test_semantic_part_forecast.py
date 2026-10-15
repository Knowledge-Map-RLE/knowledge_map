"""Новая группа посылок остаётся гипотезой; логическое выделение части не создаёт репликации."""
from copy import deepcopy
from hashlib import sha256

import pytest

from application.semantic_part_forecast import SealSemanticPartForecast
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, fingerprint
from domain.semantic_part_forecast import forecast_parts, LIMITS
from domain.semantic_part_projection import project_parts
from domain.whole_map_forecast import project
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import ref
from tests.test_whole_map_forecast import corpus, families


def prepare(maps):
    for m in maps:
        text = 'Synthetic primary source for ' + m['article_id'] + ' 🙂.'
        m['pipeline_id'] = 'text_reified'
        m['source'] = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'content_end': len(text),
                       'offset_encoding': 'unicode_codepoints', 'units': [{'id': 'U1', 'start': 0, 'end': len(text), 'text': text}]}
    sources = []
    for m in maps:
        u = m['source']['units'][0]
        sources.append({'article_id': m['article_id'], 'run_id': m['run_id'], 'source_sha256': m['source']['sha256'],
            'graph_sha256': fingerprint(m['graph']), 'document_kind': 'primary_study', 'dataset_family': 'primary-' + m['article_id'],
            'reason_ru': 'Синтетический источник для проверки механизма, не научные данные.',
            'evidence': [{**u, 'unit_id': u['id'], 'sha256': sha256(u['text'].encode()).hexdigest()}],
            'knowledge': [{'knowledge_id': k['knowledge_id'], 'knowledge_sha256': fingerprint(k),
                'statements': [{'statement_id': s['statement_id'], 'origin': 'primary_result',
                    'evidence_unit_ids': ['U1'], 'reason_ru': 'Синтетическое утверждение.'} for s in k['semantic_frame']['statements']]}
                for k in m['graph']['knowledge']]})
    return maps, {'version': 'whole-map-evidence-origin-1', 'author': 'Codex', 'model_calls': 0,
                  'expert_validated': False, 'sources': sources}


def execute(maps=None):
    maps, origins = prepare(maps or corpus())
    return forecast_parts(maps, families(maps), None, None, origins)


def test_generates_new_group_without_requiring_existing_author_conclusion():
    r = execute()
    assert r['canonical_blocks'] == r['licensed_parts'] == 8
    candidates = r['predictions']['graph']
    assert candidates and r['predictions']['same_rules_without_dependencies']
    assert all(c['new_joint_group']['known_author_group_required'] is False for c in candidates)
    assert all(c['new_joint_group']['author_asserted_group'] is False and not c['logical_entailment'] for c in candidates)
    assert all(len(c['primary_families']) >= 2 for c in candidates)
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']


def test_source_parent_internal_direction_still_controls_application():
    maps = corpus()
    for m in maps[:2]:
        m['graph']['transitions'].append({'sources': ['B1'], 'target': 'B2'})
        m['graph']['edges'].append({'source': 'B1', 'target': 'B2'})
    r = execute(maps)
    assert not r['predictions']['graph'] and r['predictions']['same_rules_without_dependencies']
    assert r['diagnostics']['graph']['application']['rejected']['missing_learned_internal_dependency'] > 0


def test_two_parts_of_one_receiving_conjunction_can_supply_joint_input():
    maps = corpus(); receiving = maps[-1]
    first, second = receiving['graph']['knowledge']
    first['semantic_frame']['logic'] = 'conjunction'
    first['semantic_frame']['statements'].extend(deepcopy(second['semantic_frame']['statements']))
    receiving['graph']['knowledge'] = [first]; receiving['graph']['nodes'] = [{'id': 'B1', 'knowledge_id': 'K1'}]
    r = execute(maps)
    assert r['predictions']['graph']
    candidate = r['predictions']['graph'][0]
    assert len(candidate['premises']) == 2
    assert len({tuple(p['native_key']) for p in candidate['premises']}) == 1
    assert len({tuple(p['part_key']) for p in candidate['premises']}) == 2
    assert not candidate['independent_replication_certified']


@pytest.mark.parametrize('body_kind,head_kind', [('state', 'state'), ('state', 'action'), ('action', 'state'), ('action', 'action')])
def test_state_and_action_kinds_and_statuses_survive_projection(body_kind, head_kind):
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            kind = head_kind if k['knowledge_id'] == 'K3' else body_kind
            k['kind'] = kind
            k['action_status'] = 'performed' if kind == 'action' else None
    r = execute(maps)
    for v in r['part_views']:
        proof = v['projection_proof']; native = proof['complete_native_knowledge']
        assert v['frame']['kind'] == native['kind']
        assert v['frame']['action_status'] == native['action_status']
    assert all(c['frame']['kind'] == head_kind and c['frame']['action_status'] == ('performed' if head_kind == 'action' else None)
               for c in r['predictions']['graph'])


def test_conjunction_parts_keep_complete_guard_parent_and_provenance():
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            k['semantic_frame']['logic'] = 'conjunction'
            extra = deepcopy(k['semantic_frame']['statements'][0]); extra['statement_id'] += '-second'
            extra['predicate'] = 'reported extra'; extra['negated'] = True; extra['quantifier'] = 'some'
            extra['modality'] = 'may'; k['semantic_frame']['statements'].append(extra)
    r = execute(maps)
    assert r['licensed_parts'] == 16
    for v in r['part_views']:
        proof = v['projection_proof']
        assert proof['operator'] == 'conjunction_elimination'
        assert len(proof['complete_parent_frame']['statements']) == 2
        assert len(proof['complete_native_knowledge']['semantic_frame']['statements']) == 2
        assert fingerprint(proof['complete_native_knowledge']) == proof['parent_knowledge_sha256']
        assert len(proof['complete_parent_provenance']) == 2
        assert not proof['new_empirical_observation'] and not proof['independent_replication']
    selected = [v for v in r['part_views'] if v['statement_position'] == 1]
    assert all(v['frame']['statements'][0]['negated'] and v['frame']['statements'][0]['scope']['quantifier'] == 'some'
               and v['frame']['statements'][0]['scope']['modality'] == 'may' for v in selected)


@pytest.mark.parametrize('logic', ['contrast', 'argument', 'partition'])
def test_unlicensed_compound_never_becomes_independent_premises(logic):
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']: k['semantic_frame']['logic'] = logic
    r = execute(maps)
    assert r['licensed_parts'] == 0 and r['part_views'] == []
    assert r['coverage']['counts']['compound_requires_separate_operator_license'] == 8
    assert all(not candidates for candidates in r['predictions'].values())


def test_known_statement_inside_unlicensed_contrast_is_not_new_prediction():
    maps = corpus(); m = maps[-1]
    k = deepcopy(m['graph']['knowledge'][0]); k['knowledge_id'] = 'K3'
    s = k['semantic_frame']['statements'][0]; s['statement_id'] = 'S3'; s['roles'][1]['concept_id'] = 'C2'
    extra = deepcopy(s); extra['statement_id'] = 'S4'; extra['predicate'] = 'other comparison'
    k['semantic_frame']['logic'] = 'contrast'; k['semantic_frame']['statements'].append(extra)
    m['graph']['knowledge'].append(k); m['graph']['nodes'].append({'id': 'B3', 'knowledge_id': 'K3'})
    r = execute(maps)
    assert not r['predictions']['graph']
    assert r['diagnostics']['graph']['application']['rejected']['known_part_conclusion'] > 0


def test_numeric_head_is_not_invented_by_part_projection():
    maps = corpus()
    for m in maps[:2]:
        m['graph']['knowledge'][-1]['semantic_frame']['statements'][0]['qualifiers']['attributes'] = [
            {'name': 'dose', 'value': '12', 'unit': 'mg'}]
    r = execute(maps)
    assert r['learning_by_mode']['graph']['learning']['rejected']['unmodelled_numeric_conclusion'] == 2
    assert not r['predictions']['graph']


def test_review_repetitions_not_primary_support():
    maps, audit = prepare(corpus())
    for source in audit['sources']:
        source['document_kind'] = 'systematic_review'; source['dataset_family'] = None
        for k in source['knowledge']:
            for s in k['statements']: s['origin'] = 'review_result'
    r = forecast_parts(maps, families(maps), None, None, audit)
    assert r['learning_by_mode']['graph']['publication_supported_rules']
    assert not r['learning_by_mode']['graph']['primary_supported_rules'] and not r['predictions']['graph']


def test_same_declared_primary_dataset_cannot_supply_two_replications():
    maps, audit = prepare(corpus())
    for source in audit['sources']: source['dataset_family'] = 'same-primary-data'
    r = forecast_parts(maps, families(maps), None, None, audit)
    assert r['learning_by_mode']['graph']['publication_supported_rules']
    assert not r['learning_by_mode']['graph']['primary_supported_rules']


def test_unknown_scope_kept_not_repaired():
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            for s in k['semantic_frame']['statements']: s['conditions'] = []
    r = execute(maps)
    assert r['licensed_parts'] == 0 and r['coverage']['counts']['unknown_parent_context'] == 8


def test_hidden_reference_cycle_is_retained_as_unknown_not_used_as_equivalence():
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            s = k['semantic_frame']['statements'][0]
            s['roles'][0]['concept_id'] = None; s['roles'][0]['knowledge_id'] = k['knowledge_id']
    r = execute(maps)
    assert r['licensed_parts'] == 0


def test_visible_cycle_rejected():
    maps = corpus(); maps[0]['graph']['edges'].append({'source': 'B3', 'target': 'B1'})
    with pytest.raises(ArticleMapError, match='DAG'): execute(maps)


def test_alignment_budget_failure_does_not_publish_partial(tmp_path, monkeypatch):
    monkeypatch.setitem(LIMITS, 'training_alignments', 0)
    maps, origin = prepare(corpus())
    class Port:
        def get(self, article, pipeline, owner, run): return next(m for m in maps if m['article_id'] == article)
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {m['article_id']: '2020-01-01' for m in maps}}
    store = FilePredictionStore(tmp_path)
    with pytest.raises(ArticleMapError, match='budget'):
        SealSemanticPartForecast(Port(), store).execute([ref(m['article_id']) for m in maps], families(maps), 'owner', metadata, {}, None, None, origin)
    assert not list(tmp_path.glob('*/seal.json'))


def test_seal_replay_owner_cutoff_identity_and_no_model_calls(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('No network'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('No provider or local models'))
    maps, origin = prepare(corpus()); reads = []
    class Port:
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner differs')
            assert article != 'target'; reads.append(article)
            return next(m for m in maps if m['article_id'] == article)
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {m['article_id']: '2020-01-01' for m in maps}}
    store = FilePredictionStore(tmp_path); app = SealSemanticPartForecast(Port(), store)
    refs = [ref(m['article_id']) for m in maps]
    first = app.execute(refs, families(maps), 'owner', metadata, {'test': 'fixed'}, None, None, origin)
    assert first == app.execute(refs, families(maps), 'owner', metadata, {'test': 'fixed'}, None, None, origin)
    assert not first['target_read'] and first['model_calls'] == 0 and len(list(tmp_path.glob('*/seal.json'))) == 1
    with pytest.raises(ArticleMapAccessDenied): app.execute(refs, families(maps), 'other', metadata, {}, None, None, origin)
    changed = deepcopy(metadata); changed['source_dates']['one'] = '2023-01-01'
    with pytest.raises(ArticleMapError, match='Future'): app.execute(refs, families(maps), 'owner', changed, {}, None, None, origin)
    wrong = deepcopy(refs); wrong[0]['run_id'] = 'another-run'
    with pytest.raises(ArticleMapError, match='identity'): app.execute(wrong, families(maps), 'owner', metadata, {}, None, None, origin)
    assert set(reads) == {'one', 'two', 'three'}


def test_parent_registry_tampering_rejected():
    from domain.evidence_origin_audit import validate_origins
    maps, audit = prepare(corpus()); originals, _, _ = project(maps)
    records = deepcopy(originals); records['one', 'K1']['frame']['statements'].append(deepcopy(records['one', 'K1']['frame']['statements'][0]))
    with pytest.raises(ArticleMapError, match='statement order'):
        project_parts(records, originals, validate_origins(maps, audit))


def test_protocol_operator_control_is_sealed_separately_and_bad_mode_never_publishes(tmp_path):
    maps, origin = prepare(corpus())
    class Port:
        def get(self, article, pipeline, owner, run):
            assert owner == 'owner' and article != 'target'
            return next(m for m in maps if m['article_id'] == article)
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {m['article_id']: '2020-01-01' for m in maps}}
    app = SealSemanticPartForecast(Port(),FilePredictionStore(tmp_path)); refs = [ref(m['article_id']) for m in maps]
    enabled = app.execute(refs,families(maps),'owner',{**metadata,'protocol_parameters_enabled':True},{},None,None,origin)
    control = app.execute(refs,families(maps),'owner',{**metadata,'protocol_parameters_enabled':False},{},None,None,origin)
    assert enabled['run_id'] != control['run_id']
    assert enabled['protocol_parameters_enabled'] and not control['protocol_parameters_enabled']
    assert len(list(tmp_path.glob('*/seal.json'))) == 2
    with pytest.raises(ArticleMapError,match='must be boolean'):
        app.execute(refs,families(maps),'owner',{**metadata,'protocol_parameters_enabled':'yes'},{},None,None,origin)
    assert len(list(tmp_path.glob('*/seal.json'))) == 2


def test_role_binding_mode_is_explicit_immutable_and_errors_do_not_publish(tmp_path, monkeypatch):
    import socket
    import httpx
    from domain.operation_role_bindings import VERSION as ROLE_VERSION
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('No network'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('No model calls'))
    maps, origin = prepare(corpus())
    class Port:
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner differs')
            assert article != 'target'
            return next(m for m in maps if m['article_id'] == article)
    audit = {'version': ROLE_VERSION, 'author': 'Codex', 'model_calls': 0, 'expert_validated': False, 'entries': []}
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {m['article_id']: '2020-01-01' for m in maps}}
    app = SealSemanticPartForecast(Port(), FilePredictionStore(tmp_path)); refs = [ref(m['article_id']) for m in maps]
    control = app.execute(refs, families(maps), 'owner', metadata, {}, None, None, origin)
    enabled = app.execute(refs, families(maps), 'owner', metadata, {}, None, None, origin, role_bindings=audit)
    assert enabled['run_id'] != control['run_id']
    assert enabled['binding']['role_bindings_sha256'] == fingerprint(audit)
    assert control['operation_role_bindings'] is None
    assert enabled['operation_role_bindings']['added_views'] == 0
    assert enabled == app.execute(refs, families(maps), 'owner', metadata, {}, None, None, origin, role_bindings=audit)
    assert len(list(tmp_path.glob('*/seal.json'))) == 2
    bad = deepcopy(audit); bad['entries'] = [{'part_key': ['one', 'nonexistent']}]
    with pytest.raises(ArticleMapError, match='Unknown binding part'):
        app.execute(refs, families(maps), 'owner', metadata, {}, None, None, origin, role_bindings=bad)
    assert len(list(tmp_path.glob('*/seal.json'))) == 2
    with pytest.raises(ArticleMapAccessDenied):
        app.execute(refs, families(maps), 'wrong-owner', metadata, {}, None, None, origin, role_bindings=audit)
