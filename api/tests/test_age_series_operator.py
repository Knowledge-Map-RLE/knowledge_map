from domain.age_series_operator import (
    build_series,
    evaluate_series,
    extract_rows,
    parse_age_band,
    summarize,
)


def _record(age_role, age_value, rate, *, metric='total rate', study_count=None):
    roles = [{'role': age_role, 'value': age_value}, {'role': 'outcome', 'value': 'incident MCI'}]
    attributes = [{'name': metric, 'value': str(rate), 'unit': 'per 1,000 person-years'}]
    if study_count is not None:
        attributes.append({'name': 'number of studies', 'value': str(study_count), 'unit': 'studies'})
    return {
        'eligible': True,
        'frame': {'statements': [{
            'predicate': 'age-specific incidence', 'roles': roles, 'scope': None,
            'negated': False, 'attributes': attributes,
        }]},
    }


def test_age_role_variants_and_open_intervals_are_read():
    assert parse_age_band('70–74 years').lower == 70
    assert parse_age_band('80⫹').upper is None
    assert parse_age_band('≥85 years').lower == 85
    assert parse_age_band('85 years or older').upper is None
    assert parse_age_band('all ages') is None


def test_direct_age_group_and_stratifier_stratum_produce_the_same_series():
    records = {
        ('study', 'K1'): _record('age group', '70–74 years', 10),
        ('study', 'K2'): {
            'eligible': True,
            'frame': {'statements': [{
                'predicate': 'age-specific incidence',
                'roles': [{'role': 'stratifier', 'value': 'age'}, {'role': 'stratum', 'value': '75–79'}, {'role': 'outcome', 'value': 'incident MCI'}],
                'scope': None, 'negated': False,
                'attributes': [{'name': 'incidence rate', 'value': '12', 'unit': 'per1000personyear'}],
            }]},
        },
        ('study', 'K3'): _record('age band', '80–84', 14),
    }
    rows = extract_rows(records)
    groups = [
        ((('study', 'M1'),), ('study', 'K1')),
        ((('study', 'M1'),), ('study', 'K2')),
        ((('study', 'M1'),), ('study', 'K3')),
    ]
    graph_series, _ = build_series(rows, groups, require_shared_dependencies=True)
    semantic_series, _ = build_series(rows, groups, require_shared_dependencies=False)
    assert len(graph_series) == len(semantic_series) == 1
    checks = evaluate_series(graph_series[0])
    assert checks == [{
        'target_band': '80–84', 'predicted_direction': 1, 'observed_direction': 1,
        'status': 'correct', 'previous_values': ['10', '12'], 'observed_values': ['12', '14'],
    }]


def test_review_median_requires_at_least_two_studies_in_every_mode():
    records = {
        ('review', 'K1'): _record('age band', '70–74', 10, metric='median ir', study_count=1),
        ('review', 'K2'): _record('age band', '75–79', 12, metric='median ir', study_count=3),
        ('review', 'K3'): _record('age band', '80–84', 14, metric='median ir', study_count=4),
    }
    rows = extract_rows(records)
    assert [row['knowledge_id'] for row in rows] == ['K2', 'K3']
    semantic_series, _ = build_series(rows, [], require_shared_dependencies=False)
    assert semantic_series == []


def test_mixed_direction_abstains_and_summary_counts_each_next_band():
    records = {
        ('study', 'K1'): _record('age band', '70–74', 10),
        ('study', 'K2'): _record('age band', '75–79', 8),
        ('study', 'K3'): _record('age band', '80–84', 9),
        ('study', 'K4'): _record('age band', '85+', 10),
    }
    series, _ = build_series(extract_rows(records), [], require_shared_dependencies=False)
    assert len(series) == 1
    checks = evaluate_series(series[0])
    assert [check['status'] for check in checks] == ['error', 'abstention']
    assert summarize(series) == {'series': 1, 'checks': 2, 'issued': 1, 'correct': 0, 'errors': 1, 'abstentions': 1}


def test_graph_mode_requires_shared_parent_group_and_semantic_mode_keeps_unlinked_series():
    records = {
        ('study', 'K1'): _record('age band', '70–74', 10),
        ('study', 'K2'): _record('age band', '75–79', 12),
        ('study', 'K3'): _record('age band', '80–84', 14),
    }
    rows = extract_rows(records)
    semantic, _ = build_series(rows, [], require_shared_dependencies=False)
    graph, rejected = build_series(rows, [], require_shared_dependencies=True)
    assert len(semantic) == 1
    assert graph == []
    assert rejected['no_shared_incoming_dependency_group'] == 1
