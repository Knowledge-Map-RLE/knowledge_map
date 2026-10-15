"""Имена и роли дают диагностический сигнал, но не лицензию на новые факты."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.semantic_participant_audit import audit_participants
from tests.test_semantic_operator_graph import fixture


def specimen():
    result = fixture()
    # Родные роли в общей фикстуре указывают на существующие понятия.
    concept = result['graph']['concepts'][0]['id']
    for i, role in enumerate(['gene','protein','pathway']):
        result['graph']['knowledge'][i]['semantic_frame']['statements'][0]['roles'] = [
            {'role':role,'concept_id':concept,'knowledge_id':None}]
    return result


def test_gene_protein_alias_collision_reported_without_mutation():
    result = specimen(); before = deepcopy(result); audit = audit_participants([result])
    assert result == before and audit['counts'] == {'gene_protein_identity_needs_review': 1}
    assert len(audit['flags'][0]['locations']) == 3
    assert audit['canonical_blocks'] == 3 and audit['statement_count'] == 3
    assert audit['automatic_expansions'] == audit['new_assertions'] == 0
    assert not audit['semantic_equivalence_established']


def test_separate_native_participants_do_not_collapse_by_case():
    result = specimen(); graph = result['graph']
    old = graph['concepts'][0]['id']; new = deepcopy(graph['concepts'][0]); new['id'] = 'C-separate'; new['display_text'] = 'ALPHA protein'
    graph['concepts'][0]['display_text'] = 'alpha gene'; graph['concepts'].append(new)
    graph['knowledge'][1]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = new['id']
    graph['knowledge'][2]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = new['id']
    assert not audit_participants([result])['flags']


def test_gene_and_pathway_shared_id_is_reviewable_not_equivalent():
    result = specimen(); result['graph']['knowledge'][1]['semantic_frame']['statements'][0]['roles'][0]['role'] = 'subject'
    audit = audit_participants([result])
    assert audit['counts'] == {'gene_pathway_identity_needs_review':1}
    assert not audit['expert_validated'] and not audit['scientific_success']


def test_gene_list_stays_complete_and_opaque_until_review():
    result = fixture(); graph = result['graph']; role = graph['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]
    role['role'] = 'genes'; label = next(c for c in graph['concepts'] if c['id'] == role['concept_id']); label['display_text'] = 'Il6, Nos2 and Cxcl9'
    before = deepcopy(result); audit = audit_participants([result])
    assert result == before and audit['counts'] == {'participant_set_members_not_explicit':1}
    assert audit['flags'][0]['label'] == 'Il6, Nos2 and Cxcl9' and audit['automatic_expansions'] == 0


def test_cohort_label_is_not_automatically_a_set_to_split():
    result = fixture(); role = result['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]
    role['role'] = 'population'
    next(c for c in result['graph']['concepts'] if c['id'] == role['concept_id'])['display_text'] = 'Older adults with and without impairment'
    assert not audit_participants([result])['flags']


def test_source_local_ids_never_create_cross_article_collisions():
    one = fixture(); two = fixture('two')
    one['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]['role'] = 'gene'
    two['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]['role'] = 'protein'
    assert not audit_participants([one,two])['flags']


def test_unlisted_participant_is_rejected():
    result = fixture(); result['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'absent'
    with pytest.raises(ArticleMapError,match='Unknown native participant'):
        audit_participants([result])


def test_all_compound_parts_remain_in_coverage():
    result = fixture(); block = result['graph']['knowledge'][0]
    extra = deepcopy(block['semantic_frame']['statements'][0]); extra['statement_id'] += '-extra'
    extra['negated'] = True; block['semantic_frame']['logic'] = 'contrast'; block['semantic_frame']['statements'].append(extra)
    audit = audit_participants([result])
    assert audit['canonical_blocks'] == 3 and audit['statement_count'] == 4
    assert all(row['full_parent_retained'] for row in audit['coverage'])


def test_application_replays_and_never_opens_unlisted_or_network_target(tmp_path,monkeypatch):
    import socket
    from application.semantic_participant_audit import SealParticipantAudit
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_schema6_prediction import ref
    result=fixture(); reads=[]
    def forbidden(*args,**kwargs):raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    class Port:
        def get(self,article,pipeline,owner,run):
            assert article=='one' and owner=='owner' and article!='target'
            reads.append(article);return result
    store=FilePredictionStore(tmp_path);app=SealParticipantAudit(Port(),store)
    first=app.execute([ref('one')],'owner',{'question':None},{'code':'fixed'})
    assert app.execute([ref('one')],'owner',{'question':None},{'code':'fixed'})==first
    assert reads==['one','one'] and len(list(tmp_path.glob('*/seal.json')))==1


def test_application_access_failure_preserves_existing_seal(tmp_path):
    from application.semantic_participant_audit import SealParticipantAudit
    from infrastructure.development_prediction_store import FilePredictionStore
    from domain.article_maps import ArticleMapAccessDenied
    from tests.test_schema6_prediction import ref
    result=fixture()
    class Port:
        def get(self,article,pipeline,owner,run):
            if owner!='owner':raise ArticleMapAccessDenied('Denied')
            return result
    store=FilePredictionStore(tmp_path);app=SealParticipantAudit(Port(),store)
    first=app.execute([ref('one')],'owner',{}, {'code':'fixed'})
    with pytest.raises(ArticleMapAccessDenied):app.execute([ref('one')],'wrong-owner',{}, {'code':'fixed'})
    assert store.read_seal(first['run_id'])==first and len(list(tmp_path.glob('*/seal.json')))==1


def test_application_rejects_wrong_run_before_publication(tmp_path):
    from application.semantic_participant_audit import SealParticipantAudit
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_schema6_prediction import ref
    result=fixture();result['run_id']='wrong-run'
    class Port:
        def get(self,*args):return result
    with pytest.raises(ArticleMapError,match='differs'):
        SealParticipantAudit(Port(),FilePredictionStore(tmp_path)).execute([ref('one')],'owner',{}, {'code':'fixed'})
    assert not list(tmp_path.glob('*/seal.json'))


def test_unknown_hidden_knowledge_reference_is_not_silently_skipped():
    result=fixture();role=result['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]
    role['concept_id']=None;role['knowledge_id']='absent'
    with pytest.raises(ArticleMapError,match='Unknown native knowledge'):
        audit_participants([result])


def test_double_reference_rejected_and_hidden_cycle_is_allowed():
    result=fixture();role=result['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]
    role['knowledge_id']=result['graph']['knowledge'][1]['knowledge_id']
    with pytest.raises(ArticleMapError,match='Exactly one'):
        audit_participants([result])
    role['concept_id']=None
    back=result['graph']['knowledge'][1]['semantic_frame']['statements'][0]['roles'][0]
    back['concept_id']=None;back['knowledge_id']=result['graph']['knowledge'][0]['knowledge_id']
    audit=audit_participants([result])
    assert audit['canonical_blocks']==3 and audit['statement_count']==3 and not audit['flags']
