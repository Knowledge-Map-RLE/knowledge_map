"""Содержательные проверки обучения, сохранения ограничений, доступности и утечек."""
from copy import deepcopy
from dataclasses import replace
import pytest
from domain.article_maps import fingerprint, ArticleMapError
from domain.semantic_operator_learning import Knowledge, Example, learn, apply
from application.semantic_operator_forecast import SealOperatorForecast, EvaluateOperatorForecast
from infrastructure.development_prediction_store import FilePredictionStore

CTX = {'age_min': 75, 'dementia_excluded': True, 'specimen': 'plasma', 'timing': 'single_baseline',
       'exposure': 'IL6', 'outcome_scope': 'global_change', 'followup_min': 3,
       'instrument': 'mmse', 'estimand': 'annual_change', 'contrast': 'high_low',
       'mci': 'absent', 'adjustment_class': 'basic_baseline'}


def frame(predicate, cohort, **changes):
    return {'kind': 'state', 'action_status': None, 'logic': 'single', 'statements': [
        {'predicate': predicate, 'roles': [{'role': 'cohort', 'value': cohort}, {'role': 'marker', 'value': 'interleukin 6'}],
         'scope': {'quantifier': 'all', 'modality': None, 'time': 'baseline to year 3', 'conditions': ['without baseline dementia']},
         'attributes': [{'name': 'followup', 'value': '36', 'unit': 'month'}],
         'negated': False, 'unknown_context': False, **changes}]}


def knowledge(source, name, predicate, availability='known_before_forecast', family=None, **changes):
    f = frame(predicate, source, **changes)
    return Knowledge(source + '/' + name, source, family or source, '2010-01-01', f, availability,
                     {'source_sha256': 'a'*64, 'run_id': 'run-'+source, 'frame_sha256': fingerprint(f),
                      'provenance': [{'unit_ids': ['u1']}]}, deepcopy(CTX))


def fixture(operator='clinical_transfer'):
    data, examples = [], []
    for source in ('A', 'B'):
        data.extend([knowledge(source, 'p', 'premise one'), knowledge(source, 'q', 'premise two'),
                     knowledge(source, 'h', 'conclusion', 'requires_target_followup')])
        examples.append(Example(source, operator, (source+'/p', source+'/q'), source+'/h', True))
    return data, examples


def fitted(operator='clinical_transfer'):
    return learn(*fixture(operator), '2014-01-01', ['T'])


def premises(): return [knowledge('T', 'p', 'premise one'), knowledge('T', 'q', 'premise two')]


def test_learns_and_applies_two_premise_operator_with_trace():
    learned = fitted(); result = apply(learned, premises(), '2014-01-01', 'clinical', ['T'])
    assert len(learned['rules']) == len(result['predictions']) == 1
    prediction = result['predictions'][0]
    assert prediction['support_families'] == ['A', 'B'] and len(prediction['premises']) == 2
    assert prediction['frame'] == frame('conclusion', 'T')
    assert prediction['status'] == 'statistical_hypothesis' and not prediction['scientific_success']


def test_repeated_publications_of_same_family_do_not_support_rule():
    data, examples = fixture()
    data = [replace(k, family='A') for k in data]
    learned = learn(data, examples, '2014-01-01', ['T'])
    assert not learned['rules'] and learned['unsupported_templates'][0]['support'] == 1


@pytest.mark.parametrize('change', [{'negated': True}, {'unknown_context': True},
                                  {'scope': {'quantifier': 'some', 'modality': None, 'time': 'baseline to year 3', 'conditions': ['without baseline dementia']}},
                                  {'scope': {'quantifier': 'all', 'modality': 'may', 'time': 'baseline to year 3', 'conditions': ['without baseline dementia']}},
                                  {'attributes': [{'name': 'followup', 'value': '36', 'unit': 'year'}]}])
def test_constraints_cannot_be_removed_to_gain_support(change):
    data, examples = fixture(); data[-1] = knowledge('B', 'h', 'conclusion', 'requires_target_followup', **change)
    assert not learn(data, examples, '2014-01-01', ['T'])['rules']


def test_biomarker_is_constant_even_when_cohort_is_variable():
    data, examples = fixture(); altered = []
    for k in data:
        if k.source_id == 'B':
            f = deepcopy(k.frame); f['statements'][0]['roles'][1]['value'] = 'c reactive protein'
            k = replace(k, frame=f, binding={**k.binding, 'frame_sha256': fingerprint(f)})
        altered.append(k)
    assert not learn(altered, examples, '2014-01-01', ['T'])['rules']


@pytest.mark.parametrize('context', [None, {**CTX, 'mci': None}, {**CTX, 'specimen': 'serum'}, {**CTX, 'age_min': 55}])
def test_clinical_context_must_be_complete_and_eligible(context):
    data, examples = fixture(); data = [replace(k, question_context=context) for k in data]
    learned = learn(data, examples, '2014-01-01', ['T'])
    assert not learned['rules'] and all('incomplete_or_ineligible_clinical_context' in e['reasons'] for e in learned['rejected_examples'])


def test_future_measurements_block_application_and_clinical_learning():
    learned = fitted()
    result = apply(learned, [replace(k, availability='requires_target_followup') for k in premises()], '2014-01-01', 'clinical', ['T'])
    assert not result['predictions'] and len(result['excluded_premises']) == 2
    data, examples = fixture(); data[0] = replace(data[0], availability='requires_target_followup')
    assert not learn(data, examples, '2014-01-01', ['T'])['rules']


def test_method_and_task_are_not_clinical_predictions():
    learned = fitted('limitation_to_task')
    assert apply(learned, premises(), '2014-01-01', 'research_task', ['T'])['predictions']
    assert not apply(learned, premises(), '2014-01-01', 'clinical', ['T'])['predictions']


def test_joint_premise_cannot_be_dropped_or_mixed_across_sources():
    assert not apply(fitted(), premises()[:1], '2014-01-01', 'clinical', ['T'])['predictions']
    other = [premises()[0], knowledge('U', 'q', 'premise two')]
    assert not apply(fitted(), other, '2014-01-01', 'clinical', ['T'])['predictions']


def test_known_head_not_reported_as_new_prediction():
    assert not apply(fitted(), [*premises(), knowledge('T', 'h', 'conclusion')], '2014-01-01', 'clinical', ['T'])['predictions']


def test_dates_and_heldout_excluded_before_learning():
    data, examples = fixture(); data = [replace(k, published_on='2014-01-01') if k.family == 'B' else k for k in data]
    assert not learn(data, examples, '2014-01-01', ['T'])['rules']
    assert not learn(*fixture(), '2014-01-01', ['A'])['rules']


def test_unknown_action_status_rejected():
    k = knowledge('A', 'x', 'method'); f = {**k.frame, 'kind': 'action'}
    with pytest.raises(ArticleMapError): replace(k, frame=f).validate()


class Corpus:
    def __init__(self): self.reads = []
    def training(self, refs):
        self.reads.append('training'); k, e = fixture()
        return {'knowledge': k, 'examples': e, 'bindings': [{'reference': r} for r in refs]}
    def premises(self, ref):
        self.reads.append('premises')
        return {'knowledge': premises(), 'binding': {'reference': ref, 'article_id': 'T', 'source_sha256': 'a'*64,
                                                   'sha256': fingerprint([k.binding for k in premises()])}}
    def outcomes(self, ref):
        self.reads.append('outcomes')
        return {'knowledge': [knowledge('T', 'h', 'conclusion')], 'binding': {'premises_sha256': fingerprint(self.premises(ref)['binding']),
                                                                         'source': {'article_id': 'T', 'source_sha256': 'a'*64}}}


def test_application_seals_before_separate_outcome_read_and_reproduces(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: (_ for _ in ()).throw(AssertionError('No network')))
    corpus = Corpus(); store = FilePredictionStore(tmp_path)
    run = SealOperatorForecast(corpus, store).execute(['A', 'B'], 'T', '2014-01-01', ['T'], 'a'*64)
    assert corpus.reads == ['training', 'premises']
    evaluation = EvaluateOperatorForecast(corpus, store).execute(run['run_id'])
    assert evaluation['rows']['clinical'][0]['matched_semantic_units'] == ['T/h']
    assert not evaluation['scientific_success'] and not evaluation['blind_test']
    assert SealOperatorForecast(corpus, store).execute(['A', 'B'], 'T', '2014-01-01', ['T'], 'a'*64) == run


def test_training_leakage_rejected_without_outcome_read(tmp_path):
    corpus = Corpus()
    with pytest.raises(ArticleMapError):
        SealOperatorForecast(corpus, FilePredictionStore(tmp_path)).execute(['A', 'B'], 'T', '2014-01-01', ['A'], 'a'*64)
    assert corpus.reads == ['training'] and not list(tmp_path.rglob('predictions.json'))
