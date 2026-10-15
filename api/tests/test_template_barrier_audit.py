"""Диагностика не превращает ослабление научных условий в прогноз."""
from copy import deepcopy

import pytest

from domain.article_maps import fingerprint
from domain.template_barrier_audit import signature, analyze, POLICIES
from application.template_barrier_audit import SealTemplateBarrierAudit
from infrastructure.development_prediction_store import FilePredictionStore


def frame(predicate, role, term, time='day 16', negated=False):
    return {'kind': 'state', 'action_status': None, 'logic': 'single', 'statements': [{
        'predicate': predicate, 'roles': [{'role': role, 'value': term, 'reference_kind': 'concept'}],
        'scope': {'time': time, 'conditions': [], 'study_group': {'study_variable': '$study'},
                  'quantifier': None, 'modality': None},
        'attributes': [], 'negated': negated}]}


def rule(source='study-pmc123', body_term=None, head_term=None, time='day 16', negated=False):
    body_term = body_term or {'constant': 'mice in ' + source}
    head_term = head_term or deepcopy(body_term)
    value = {'body': [frame('performed procedure', 'population', body_term, time)],
             'head': frame('reduced', 'population', head_term, time, negated), 'internal_edges': []}
    return {'id': fingerprint(value), **value, 'examples': [], 'families': [source]}


def artifact():
    rules = [rule(), rule('study-pmc456')]
    views, support = [], []
    for i, r in enumerate(rules):
        article = r['families'][0]
        native = {'knowledge_id': 'K1', 'semantic_frame': {}}
        f = deepcopy(r['head'])
        key = [article, 'part1']
        origin = {'origin': 'primary_result'}
        views.append({'key': key, 'native_key': [article, 'K1'], 'frame': f, 'run_id': 'run' + str(i),
            'projection_proof': {'parent_key': [article, 'K1'], 'run_id': 'run' + str(i),
                'view_frame_sha256': fingerprint(f), 'complete_native_knowledge': native,
                'parent_knowledge_sha256': fingerprint(native), 'origin': origin}})
        support.append({'rule_id': r['id'], 'examples': [{'part_head': key, 'native_head': [article, 'K1'],
            'origin': 'primary_result', 'declared_primary_family': 'family' + str(i)}]})
    binding = {'references': [{'article_id': 'study-pmc123'}, {'article_id': 'study-pmc456'}]}
    return {'run_id': fingerprint(binding), 'binding': binding, 'question': None, 'target_read': False,
        'model_calls': 0, 'canonical_blocks': 2, 'licensed_parts': 2, 'part_views': views,
        'learning_by_mode': {'graph': {'publication_supported_rules': [],
            'learning': {'unsupported_rules': rules}, 'unsupported_origin_support': support}},
        'primary_support_by_mode': {'graph': []}, 'predictions': {'graph': []}}


def test_source_labels_preserve_models_and_biological_clock():
    ids = ['study-pmc123', 'study-pmc456']
    a, b = rule(ids[0]), rule(ids[1])
    assert signature(a, 'exact', ids) != signature(b, 'exact', ids)
    assert signature(a, 'source_labels', ids) == signature(b, 'source_labels', ids)
    b['head']['statements'][0]['scope']['time'] = 'day 30'
    assert signature(a, 'source_labels', ids) != signature(b, 'source_labels', ids)
    assert signature(a, 'without_context', ids) == signature(b, 'without_context', ids)
    b['head']['statements'][0]['roles'][0]['value']['constant'] = 'rats in study-pmc456'
    assert signature(a, 'source_labels', ids) != signature(b, 'source_labels', ids)


def test_other_article_id_and_molecular_numbers_are_not_erased():
    a, b = rule(), rule()
    a['head']['statements'][0]['roles'][0]['value'] = {'constant': 'TNFR1 in pmc999'}
    b['head']['statements'][0]['roles'][0]['value'] = {'constant': 'TNFR2 in pmc999'}
    assert signature(a, 'source_labels', ['study-pmc123']) != signature(b, 'source_labels', ['study-pmc123'])
    c = deepcopy(a)
    c['head']['statements'][0]['roles'][0]['value'] = {'constant': 'TNFR1 in pmc1230'}
    assert signature(a, 'source_labels', ['study-pmc123']) != signature(c, 'source_labels', ['study-pmc123'])


def test_target_in_experiment_prefix_is_not_source_pmcid():
    a, b = rule(), rule()
    a['head']['statements'][0]['roles'][0]['value'] = {'constant': 'reported in pmc10000452'}
    b['head']['statements'][0]['roles'][0]['value'] = {'constant': 'reported in pmc123'}
    assert signature(a, 'source_labels', ['pilot-pmc10000452-pmc123-abc']) != signature(b, 'source_labels', ['pilot-pmc10000452-pmc123-abc'])


def test_relational_shape_preserves_coreference():
    a = rule(body_term={'constant': 'mice'}, head_term={'constant': 'mice'})
    b = rule(body_term={'constant': 'rats'}, head_term={'constant': 'rats'})
    c = rule(body_term={'constant': 'rats'}, head_term={'constant': 'humans'})
    assert signature(a, 'relational_structure', []) == signature(b, 'relational_structure', [])
    assert signature(a, 'relational_structure', []) != signature(c, 'relational_structure', [])


@pytest.mark.parametrize('policy', POLICIES)
def test_negation_and_action_status_are_never_erased(policy):
    a, b = rule(), rule(negated=True)
    assert signature(a, policy, []) != signature(b, policy, [])
    b = deepcopy(a)
    b['head']['kind'], b['head']['action_status'] = 'action', 'unresolved'
    assert signature(a, policy, []) != signature(b, policy, [])


def test_alpha_renaming_and_premise_permutation_preserve_edges():
    a = rule(body_term={'variable': '$0'}, head_term={'variable': '$0'})
    a['body'].append(frame('measured', 'subject', {'variable': '$1'}))
    a['internal_edges'] = [[0, 1]]
    b = deepcopy(a)
    b['body'].reverse()
    b['internal_edges'] = [[1, 0]]
    for f in [*b['body'], b['head']]:
        for r in f['statements'][0]['roles']:
            r['value']['variable'] += '-rename'
    for policy in POLICIES:
        assert signature(a, policy, []) == signature(b, policy, [])
    b['internal_edges'] = []
    assert signature(a, 'predicate_topology', []) != signature(b, 'predicate_topology', [])


def test_collision_is_not_prediction_and_inputs_unchanged():
    original = artifact()
    before = deepcopy(original)
    result = analyze(original)
    assert result['modes']['graph']['policies']['exact']['multi_family_collision_groups'] == 0
    groups = result['modes']['graph']['policies']['source_labels']['collision_groups']
    assert len(groups) == 1 and groups[0]['valid_inference'] is False
    assert result['new_predictions'] == 0 and result['scientific_success'] is False
    assert original == before


def test_same_family_does_not_count_twice():
    a = artifact()
    for r in a['learning_by_mode']['graph']['unsupported_origin_support']:
        r['examples'][0]['declared_primary_family'] = 'same'
    result = analyze(a)
    assert all(p['multi_family_collision_groups'] == 0 for p in result['modes']['graph']['policies'].values())


def test_cited_result_is_not_primary_support():
    a = artifact()
    a['part_views'][1]['projection_proof']['origin']['origin'] = 'cited_result'
    e = a['learning_by_mode']['graph']['unsupported_origin_support'][1]['examples'][0]
    e['origin'], e['declared_primary_family'] = 'cited_result', None
    result = analyze(a)
    assert result['modes']['graph']['primary_result_templates'] == 1


@pytest.mark.parametrize('mutation', ['frame', 'native', 'seal', 'target', 'model', 'support'])
def test_corrupt_or_leaking_inputs_refused(mutation):
    a = artifact()
    if mutation == 'frame': a['part_views'][0]['frame']['logic'] = 'conjunction'
    elif mutation == 'native': a['part_views'][0]['projection_proof']['complete_native_knowledge']['knowledge_id'] = 'K2'
    elif mutation == 'seal': a['binding']['extra'] = True
    elif mutation == 'target': a['target_read'] = True
    elif mutation == 'model': a['model_calls'] = 1
    else: a['learning_by_mode']['graph']['unsupported_origin_support'].pop()
    with pytest.raises(ValueError): analyze(a)


def test_immutable_repeat_and_invalid_run_not_published(tmp_path):
    store = FilePredictionStore(tmp_path)
    use_case = SealTemplateBarrierAudit(store)
    a = artifact()
    first = use_case.execute(a, {'code': 'v1'})
    assert first == use_case.execute(a, {'code': 'v1'})
    assert first['run_id'] != use_case.execute(a, {'code': 'v2'})['run_id']
    a['model_calls'] = 1
    with pytest.raises(ValueError): use_case.execute(a, {'code': 'v3'})
    assert len(list(tmp_path.iterdir())) == 2
