"""Допуск противопоставления не стирает область, отрицание, модальность и полного родителя."""
from copy import deepcopy
import pytest

from domain.article_maps import fingerprint, ArticleMapError
from domain.compound_part_licenses import VERSION
from domain.evidence_origin_audit import validate_origins
from domain.semantic_part_projection import project_parts
from domain.whole_map_forecast import project
from tests.test_semantic_part_forecast import prepare
from tests.test_whole_map_forecast import corpus


def fixture():
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            k['grounding'] = 'source_explicit'
            k['semantic_frame']['logic'] = 'contrast'
            extra = deepcopy(k['semantic_frame']['statements'][0])
            extra['statement_id'] += '-other'
            extra['predicate'] = 'not statistically detected'
            extra['negated'] = True; extra['quantifier'] = 'some'; extra['modality'] = 'may'
            k['semantic_frame']['statements'].append(extra)
    maps, audit = prepare(maps)
    origins = validate_origins(maps, audit)
    records, _, _ = project(maps)
    for m in maps:
        for k in m['graph']['knowledge']:
            records[m['article_id'], k['knowledge_id']]['native_knowledge'] = deepcopy(k)
    entries = []
    for key, raw in records.items():
        k = raw['native_knowledge']; source = origins['sources'][key[0]]
        entries.append({'article_id': key[0], 'knowledge_id': key[1], 'run_id': raw['run_id'],
            'source_sha256': source['source_sha256'], 'graph_sha256': source['graph_sha256'],
            'knowledge_sha256': fingerprint(k), 'statement_ids': [s['statement_id'] for s in k['semantic_frame']['statements']],
            'asserted_under_recorded_scope': True, 'discourse_relation_retained': True,
            'reason_ru': 'Синтетический тест самостоятельных сообщений, не научное подтверждение.',
            'evidence': deepcopy(source['evidence'])})
    license = {'version': VERSION, 'author': 'Codex', 'model_calls': 0, 'expert_validated': False, 'entries': entries}
    return records, origins, license


def test_no_implicit_contrast_permission():
    records, origins, _ = fixture()
    views, _, _, coverage = project_parts(records, records, origins)
    assert not views and coverage['counts']['compound_requires_separate_operator_license'] == 8


def test_complete_scoped_contrast_and_parent_remain_in_proof():
    records, origins, license = fixture(); before = deepcopy((records, origins, license))
    views, _, _, coverage = project_parts(records, records, origins, license)
    assert (records, origins, license) == before
    assert len(views) == 16 and coverage['compound_licenses']['projected_parents'] == 8
    for v in views.values():
        proof = v['projection_proof']; i = v['statement_position']
        assert proof['operator'] == 'source_asserted_contrast_clause'
        assert proof['complete_parent_frame']['logic'] == 'contrast'
        assert proof['complete_native_knowledge']['semantic_frame']['logic'] == 'contrast'
        assert v['frame']['statements'][0] == proof['comparison_parent_frame']['statements'][i]
        assert not proof['conditions_removed'] and not proof['independent_replication']
        assert not proof['clauses_are_independent_replications'] and proof['discourse_relation_retained']
        if i == 1:
            s = v['frame']['statements'][0]
            assert s['negated'] and s['scope']['modality'] == 'may' and s['scope']['quantifier'] == 'some'


@pytest.mark.parametrize('field,value', [('run_id', 'changed'), ('source_sha256', 'changed'),
    ('graph_sha256', 'changed'), ('knowledge_sha256', 'changed'),
    ('statement_ids', []), ('asserted_under_recorded_scope', False), ('discourse_relation_retained', False)])
def test_binding_or_assertion_mismatch_is_rejected(field, value):
    records, origins, license = fixture(); license['entries'][0][field] = value
    with pytest.raises(ArticleMapError): project_parts(records, records, origins, license)


def test_changed_unicode_source_evidence_is_rejected():
    records, origins, license = fixture(); license['entries'][0]['evidence'][0]['text'] += 'changed'
    with pytest.raises(ArticleMapError, match='evidence differs'): project_parts(records, records, origins, license)


def test_argument_and_partition_are_not_implicitly_licensed():
    for logic in ['argument', 'partition']:
        records, origins, license = fixture()
        k = tuple((license['entries'][0]['article_id'], license['entries'][0]['knowledge_id']))
        records[k]['native_knowledge']['semantic_frame']['logic'] = records[k]['frame']['logic'] = logic
        license['entries'][0]['knowledge_sha256'] = fingerprint(records[k]['native_knowledge'])
        with pytest.raises(ArticleMapError, match='contrasts'): project_parts(records, records, origins, license)


def test_license_does_not_override_unknown_context():
    records, origins, license = fixture()
    for r in records.values(): r['eligible'] = False
    views, _, _, coverage = project_parts(records, records, origins, license)
    assert not views and coverage['compound_licenses']['projected_parents'] == 0
    assert not coverage['compound_licenses']['context_guard_overridden']


def test_partial_evidence_and_repeated_license_are_rejected():
    for mutate in [lambda l: l['entries'][0].update(evidence=[]),
                   lambda l: l['entries'].append(deepcopy(l['entries'][0]))]:
        records, origins, license = fixture(); mutate(license)
        with pytest.raises(ArticleMapError): project_parts(records, records, origins, license)
