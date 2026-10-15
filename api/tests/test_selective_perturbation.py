"""Неопределённость переноса и проверки источниковых ролей."""
from copy import deepcopy
from hashlib import sha256
import pytest
from domain.article_maps import fingerprint
from domain.semantic_operator_graph import VERSION as GRAPH_VERSION
from domain.selective_perturbation import generate, validate_licenses, AUDIT_VERSION
from application.selective_perturbation import SealSelectivePerturbation
from infrastructure.development_prediction_store import FilePredictionStore


def fixture():
    nodes = {v: {'kind': 'concept', 'article_id': 'source', 'label': v} for v in ('a', 'b', 'loss_a', 'loss_ab', 'drug', 'mouse')}
    g = {'version': GRAPH_VERSION, 'nodes': nodes, 'statements': {}, 'parents': {}, 'source_units': {},
         'canonical_blocks': 3, 'statement_count': 3}; entries = []
    for sid, intervention, targets, population, kind, predicate, direction in (
            ('good', 'loss_a', ['a'], 'mouse', 'observed_perturbation', 'reduced_after_intervention', 'decrease'),
            ('bad', 'loss_ab', ['a', 'b'], 'mouse', 'observed_perturbation', 'exacerbated_after_intervention', 'increase'),
            ('broad', 'drug', ['a', 'b'], None, 'broad_mechanism', 'inhibitor_mechanism', None)):
        original = {'predicate': predicate, 'modality': None, 'qualifiers': {'attributes': [{'value': 'Blocks target a and target b.'}]}}
        parent = {'semantic_frame': {'logic': 'single', 'statements': [original]}}
        g['parents'][sid] = {'knowledge_id': sid, 'article_id': 'source', 'knowledge_sha256': fingerprint(parent), 'complete_parent': parent}
        s = {'id': sid, 'parent': sid, 'article_id': 'source', 'negated': False, 'state_or_action': 'state', 'action_status': None,
             'original_statement': original, 'parent_logic': 'single', 'scope': {'model': 'reported'},
             'roles': [{'native_role': 'intervention', 'target': intervention}], 'evidence': [sid]}
        if population: s['roles'].append({'native_role': 'population', 'target': population})
        g['statements'][sid] = s; text = 'The source reports target a and target b.'
        g['source_units'][sid] = {'start': 10, 'end': 10 + len(text), 'text': text}
        outcomes = [] if direction is None else [{'key': 'pathology', 'direction': direction, 'label_ru': 'патология'}]
        claims = ['intervention', 'targets', 'population', 'perturbation'] + ([] if not outcomes else ['outcome:pathology'])
        entries.append({'statement': sid, 'parent_sha256': fingerprint(parent), 'statement_sha256': fingerprint(s), 'kind': kind,
            'perturbation': 'genetic_loss' if kind == 'observed_perturbation' else 'pharmacological_signaling_blockade',
            'bindings': {'intervention': intervention, 'targets': targets, 'population': population}, 'outcomes': outcomes,
            'quotes': [{'claim': c, 'unit': sid, 'start': 10, 'end': 10 + len(text), 'text': text, 'sha256': sha256(text.encode()).hexdigest()} for c in claims],
            'target_identity_proofs': [{'target': t, 'statement': sid, 'quote': {'unit': sid, 'start': 10, 'end': 10 + len(text), 'text': text, 'sha256': sha256(text.encode()).hexdigest()}} for t in targets],
            'reason_ru': 'Разметка источника.', 'context_limitations_ru': ['Подробные протоколы неизвестны.'],
            'independent_primary_replications_certified': False})
    a = {'version': AUDIT_VERSION, 'graph_sha256': fingerprint(g), 'author': 'Codex', 'expert_validated': False, 'entries': entries}
    return g, a


def test_analogy_not_entailment_and_all_parents_kept():
    g, a = fixture(); before = deepcopy(g); r = generate(g, a)
    assert g == before and len(r['coverage']) == 3
    c = r['candidates']['semantic_role_join'][0]
    assert len(c['parent_frames']) == 3 and c['conclusion']['preserve_targets'] == ['b']
    assert not c['logical_entailment'] and not c['comparative_efficacy_predicted']
    assert not c['human_efficacy_predicted'] and not c['scientific_novelty_certified']
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']
    assert not r['candidates']['single_parent']


@pytest.mark.parametrize('mutation', ['target_missing', 'foreign_target', 'intervention_role', 'population_role',
                                    'unknown_statement', 'repeated_statement', 'parent_hash', 'statement_hash',
                                    'negation', 'modality', 'intention', 'argument', 'direction', 'no_quote',
                                    'quote_text', 'quote_offset', 'quote_hash', 'primary_claim'])
def test_reject_unlicensed_fields(mutation):
    g, a = fixture(); e = a['entries'][0]
    if mutation == 'target_missing': e['bindings']['targets'] = []
    elif mutation == 'foreign_target': g['nodes']['a']['article_id'] = 'other'
    elif mutation == 'intervention_role': e['bindings']['intervention'] = 'drug'
    elif mutation == 'population_role': e['bindings']['population'] = 'b'
    elif mutation == 'unknown_statement': e['statement'] = 'unknown'
    elif mutation == 'repeated_statement': a['entries'].append(deepcopy(e))
    elif mutation == 'parent_hash': e['parent_sha256'] = 'changed'
    elif mutation == 'statement_hash': e['statement_sha256'] = 'changed'
    elif mutation == 'negation': g['statements']['good']['negated'] = True
    elif mutation == 'modality': g['statements']['good']['original_statement']['modality'] = 'may'
    elif mutation == 'intention': g['statements']['good']['action_status'] = 'intended'
    elif mutation == 'argument': g['statements']['good']['parent_logic'] = 'argument'
    elif mutation == 'direction': e['outcomes'][0]['direction'] = 'increase'
    elif mutation == 'no_quote': e['quotes'].pop()
    elif mutation == 'quote_text': e['quotes'][0]['text'] = 'invented'
    elif mutation == 'quote_offset': e['quotes'][0]['start'] = 0
    elif mutation == 'quote_hash': e['quotes'][0]['sha256'] = 'changed'
    else: e['independent_primary_replications_certified'] = True
    a['graph_sha256'] = fingerprint(g)
    if mutation not in {'unknown_statement', 'statement_hash'}: e['statement_sha256'] = fingerprint(g['statements']['good'])
    with pytest.raises(ValueError): validate_licenses(g, a)


def test_missing_broad_branch_blocks_join():
    g, a = fixture(); a['entries'][2]['bindings']['targets'] = ['a', 'mouse']
    with pytest.raises(ValueError): generate(g, a)


def test_target_identity_cannot_use_same_quote_for_unmentioned_entity():
    g, a = fixture(); e = a['entries'][0]; e['bindings']['targets'] = ['mouse']; e['target_identity_proofs'][0]['target'] = 'mouse'
    with pytest.raises(ValueError): generate(g, a)


def test_target_cannot_come_only_from_unrelated_sentence_in_same_unit():
    g, a = fixture(); e = a['entries'][0]; q = next(q for q in e['quotes'] if q['claim'] == 'targets')
    text = 'target a'; start = g['source_units']['good']['text'].index(text) + 10
    q.update({'text': text, 'start': start, 'end': start + len(text), 'sha256': sha256(text.encode()).hexdigest()})
    e['bindings']['targets'] = ['b']; e['target_identity_proofs'][0]['target'] = 'b'
    with pytest.raises(ValueError): generate(g, a)


def test_replay_and_no_target_access(tmp_path):
    g, a = fixture(); source = {'run_id': 'source-run', 'semantic_graph': g, 'target_read': False, 'model_calls': 0}
    service = SealSelectivePerturbation(FilePredictionStore(tmp_path)); r = service.execute(source, a, {'implementation': 'test'})
    assert service.execute(source, a, {'implementation': 'test'}) == r
    source['target_read'] = True
    with pytest.raises(ValueError): service.execute(source, a, {})
