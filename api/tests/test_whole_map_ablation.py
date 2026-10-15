"""Удаление и перестановка связей не меняют исходные семантические блоки."""
from copy import deepcopy
from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups, known_baselines
from domain.whole_map_forecast import project, forecast
from tests.test_whole_map_forecast import corpus, families


def test_source_neighborhood_uses_source_units_without_access_to_dependencies():
    maps = corpus()
    records, groups, _ = project(maps)
    neighborhood = source_neighborhood_groups(records)
    assert neighborhood and all(len(body) <= 3 and all(p[0] == head[0] for p in body) for body, head in neighborhood)
    changed = deepcopy(maps)
    for m in changed:
        m['graph']['transitions'] = []
        m['graph']['edges'] = []
    assert source_neighborhood_groups(project(changed)[0]) == neighborhood
    # Два блока с одинаковым субъектом, но из разных фрагментов, не становятся группой.
    isolated = deepcopy(records)
    for i, r in enumerate(isolated.values()):
        r['provenance'] = [{'unit_ids': ['unique-' + str(i)]}]
    assert source_neighborhood_groups(isolated) == []


def test_permutation_is_reproducible_preserves_joint_sizes_and_article_boundaries():
    records, groups, _ = project(corpus())
    shuffled = permuted_groups(records, groups)
    assert shuffled == permuted_groups(records, groups) and shuffled != groups
    assert [len(body) for body, _ in shuffled] == [len(body) for body, _ in groups]
    assert all(head in records and all(p in records and p[0] == head[0] and p != head for p in body)
               for body, head in shuffled)


def test_six_modes_are_sealed_without_claiming_scientific_advantage():
    maps = corpus()
    before = deepcopy(maps)
    result = forecast(maps, families(maps))
    assert set(result['predictions']) == {'graph', 'same_rules_without_dependencies',
        'source_neighborhood_without_dependencies', 'permuted_dependencies', 'known_union', 'frequency'}
    assert maps == before and not result['graph_advantage_demonstrated']
    assert all(len(p) <= result['limits']['candidate_limit'] for p in result['predictions'].values())
    assert all(not p['novel_claim'] for mode in ('known_union', 'frequency') for p in result['predictions'][mode])


def test_frequency_support_counts_families_not_repeated_publications():
    maps = corpus()
    maps[1] = deepcopy(maps[0])
    maps[1]['article_id'] = 'two'
    maps[1]['run_id'] = 'run-two'
    records = project(maps)[0]
    modes, diagnostics = known_baselines(records, {'one': 'shared', 'two': 'shared', 'three': 'third'}, 20)
    assert diagnostics['eligible_known_pool'] < len(records)
    assert all(p['support_families'] == ['shared'] for p in modes['frequency'] if len(p['premises']) == 2)
