"""Расхождение плазмы и сыворотки не устраняется голосованием или подменой полного текста."""
from copy import deepcopy
import pytest
from application.research_source_access import AuditResearchSourceAccess
from domain.article_maps import ArticleMapError, digest
from domain.research_source_access import audit_source_access
from infrastructure.research_artifacts import FileResearchArtifacts


def candidate():
    return {'doi': '10.1234/test', 'pmid': '123', 'publication_year': 2015, 'cutoff_year': 2022}


def document(kind='journal_abstract', matrix='plasma', scope='baseline_il6'):
    text = 'Methods 🙂 plasma or serum.\nResults.\nReferences.'
    span = {'start': 8, 'end': 9, 'text': '🙂', 'offset_encoding': 'unicode_code_points'}
    def section(value):
        start = text.index(value)
        return {'start': start, 'end': start + len(value), 'text': value, 'offset_encoding': 'unicode_code_points'}
    full = kind == 'full_primary_article'
    return {'id': 'a', 'doi': '10.1234/test', 'pmid': '123', 'kind': kind, 'language': 'en',
            'text': text, 'sha256': digest(text), 'full_text_verified': full,
            'sections': {key: section(value) for key, value in
                         [('methods', 'Methods 🙂 plasma or serum.'), ('results', 'Results.'), ('references', 'References.')]} if full else {},
            'assertions': [{'scope': scope, 'field': 'matrix', 'value': matrix, 'evidence': [span]}]}


@pytest.mark.parametrize('kind', ['journal_abstract', 'author_summary', 'bibliographic_metadata'])
def test_partial_document_never_substitutes_for_full_primary_text(kind):
    d = document(kind)
    if kind == 'bibliographic_metadata': d['assertions'] = []
    result = audit_source_access(candidate(), [d])
    assert not result['ready_for_fulltext_formalization']
    assert result['blockers'] == ['full_primary_text_not_acquired_and_verified']
    d['full_text_verified'] = True
    with pytest.raises(ArticleMapError): audit_source_access(candidate(), [d])


def test_equal_abstracts_do_not_prove_specimen_or_fulltext_admission():
    a = document(); b = deepcopy(a); b['id'] = 'b'
    result = audit_source_access(candidate(), [a, b])
    assert not result['conflicts'] and not result['ready_for_fulltext_formalization']
    assert not result['question_eligibility_confirmed'] and not result['training_support_added']


def test_specimen_conflict_preserved_without_majority_vote():
    a = document(); b = document('author_summary', 'serum'); b['id'] = 'b'; b['language'] = 'ja'
    c = deepcopy(a); c['id'] = 'c'
    result = audit_source_access(candidate(), [a, b, c])
    conflict = result['conflicts'][0]
    assert conflict['resolved_value'] is None and conflict['resolution'] == 'unresolved'
    assert [s['value'] for s in conflict['assertions']] == ['plasma', 'serum', 'plasma']
    assert not result['ready_for_fulltext_formalization']


def test_different_analyses_are_not_specimen_conflicts():
    a = document(); b = document('author_summary', 'serum', 'different_visit'); b['id'] = 'b'
    assert not audit_source_access(candidate(), [a, b])['conflicts']


def test_reviewed_full_primary_text_is_only_ready_for_formalization_not_training():
    result = audit_source_access(candidate(), [document('full_primary_article')])
    assert result['ready_for_fulltext_formalization']
    assert not result['training_support_added'] and not result['question_eligibility_confirmed']


def test_full_text_does_not_silently_discard_conflicting_summary():
    a = document('full_primary_article'); b = document('author_summary', 'serum'); b['id'] = 'b'
    result = audit_source_access(candidate(), [a, b])
    assert result['full_text_document_ids'] == ['a'] and not result['ready_for_fulltext_formalization']


@pytest.mark.parametrize('change', ['hash', 'offset', 'identity', 'reference_only', 'language', 'unknown_kind'])
def test_invalid_provenance_and_completeness_rejected(change):
    d = document('full_primary_article')
    if change == 'hash': d['sha256'] = '0' * 64
    elif change == 'offset': d['assertions'][0]['evidence'][0]['end'] = 10
    elif change == 'identity': d['doi'] = '10.1234/other'
    elif change == 'reference_only': del d['sections']['methods']
    elif change == 'language': d['language'] = 'ja'
    else: d['kind'] = 'ontology_inference'
    with pytest.raises(ArticleMapError): audit_source_access(candidate(), [d])


def test_metadata_cannot_establish_primary_methods():
    with pytest.raises(ArticleMapError): audit_source_access(candidate(), [document('bibliographic_metadata')])


def test_primary_specimen_claim_cannot_use_its_bibliography():
    d = document('full_primary_article')
    d['assertions'][0]['evidence'] = [deepcopy(d['sections']['references'])]
    with pytest.raises(ArticleMapError): audit_source_access(candidate(), [d])


def test_future_and_duplicate_documents_rejected():
    c = candidate(); c['publication_year'] = 2024
    with pytest.raises(ArticleMapError): audit_source_access(c, [document()])
    with pytest.raises(ArticleMapError): audit_source_access(candidate(), [document(), document()])


def test_application_repeats_immutable_audit_without_models(tmp_path):
    from tools.import_codex_article_map import prohibit_generation
    prohibit_generation()
    use_case = AuditResearchSourceAccess(FileResearchArtifacts(tmp_path))
    first = use_case.execute(candidate(), [document()])
    assert use_case.execute(candidate(), [document()]) == first
    assert len(list(tmp_path.glob('*.json'))) == 1 and first['model_calls'] == 0
