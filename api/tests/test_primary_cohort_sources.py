"""Контроль остаётся метаданными, а сохранённые первичные тексты проверяются по хешам."""
import copy

import pytest

from application.primary_cohort_sources import AuditPrimarySources
from domain.article_maps import ArticleMapError
from domain.primary_cohort_sources import metadata_record, training_access, xml_identity
from infrastructure.primary_cohort_sources import EuropePmcPrimarySources,FilePrimarySourceStore,convert_primary_xml
from infrastructure.public_article_text import convert_xml

ENTRY={"id":"synthetic-source","doi":"10.1234/synthetic","role":"training_candidate"}
ROW={"id":"1","source":"MED","pmcid":"PMC1","doi":"10.1234/synthetic","title":"Synthetic article",
     "authorString":"Synthetic author","firstPublicationDate":"2000-01-01","isOpenAccess":"Y","inPMC":"Y"}
XML='''<article><front><article-meta><article-id pub-id-type="doi">10.1234/synthetic</article-id><title-group><article-title>Synthetic article</article-title></title-group></article-meta></front><body><sec><title>Methods</title><p>Synthetic methods.</p></sec><sec><title>Results</title><p>Synthetic results.</p><table-wrap id="T1"><label>Table 1</label><graphic href="table.png"/></table-wrap></sec></body><back><ref-list><ref><mixed-citation>Synthetic citation</mixed-citation></ref></ref-list></back></article>'''


class Provider:
    def __init__(self):self.calls=[]
    def metadata(self,expected):self.calls.append(("metadata",expected));return metadata_record(ROW)
    def training_xml(self,entry,record):training_access(entry);self.calls.append(("fulltext",entry["id"]));return XML
    def control_candidates(self):raise AssertionError("Audit must not fetch control content")


def test_lite_metadata_rejects_abstract_and_preserves_access_flags():
    r=metadata_record(ROW)
    assert r["metadata_only"] and r["is_open_access"] and r["doi"]==ENTRY["doi"]
    bad={**ROW,"abstractText":"not permitted"}
    with pytest.raises(ArticleMapError,match="abstract"):metadata_record(bad)


def test_control_download_rejected_before_any_http(monkeypatch):
    provider=EuropePmcPrimarySources()
    monkeypatch.setattr(provider,"_get",lambda *a:(_ for _ in ()).throw(AssertionError("Must not call HTTP")))
    with pytest.raises(ArticleMapError,match="Control full text"):
        provider.training_xml({**ENTRY,"role":"control_candidate"},metadata_record(ROW))


def test_xml_identity_doi_and_full_body_required():
    identity=xml_identity(XML,metadata_record(ROW))
    assert identity["tables"][0]["image_only"] is True and identity["references"]==1
    with pytest.raises(ArticleMapError,match="DOI differs"):xml_identity(XML.replace("10.1234/synthetic","10.1234/other"),metadata_record(ROW))
    with pytest.raises(ArticleMapError,match="Complete"):xml_identity("<article><front/></article>",metadata_record(ROW))


def test_training_source_is_immutable_and_resume_makes_no_requests(tmp_path):
    p=Provider();store=FilePrimarySourceStore(tmp_path);usecase=AuditPrimarySources(p,store,convert_xml)
    result=usecase.execute([ENTRY]);assert len(p.calls)==2
    assert result[0]["table_numbers_complete"] is False
    assert usecase.execute([ENTRY])==result and len(p.calls)==2
    assert "References" in (tmp_path/ENTRY["id"]/"article.md").read_text(encoding="utf-8")


def test_cached_text_tampering_rejected(tmp_path):
    p=Provider();store=FilePrimarySourceStore(tmp_path);AuditPrimarySources(p,store,convert_xml).execute([ENTRY])
    (tmp_path/ENTRY["id"]/"article.md").write_text("changed",encoding="utf-8")
    with pytest.raises(ArticleMapError,match="Cached primary text"):store.read(ENTRY)


def test_changed_entry_or_role_cannot_reuse_cached_source(tmp_path):
    store=FilePrimarySourceStore(tmp_path);AuditPrimarySources(Provider(),store,convert_xml).execute([ENTRY])
    with pytest.raises(ArticleMapError,match="binding"):store.read({**ENTRY,"doi":"10.1234/other"})
    with pytest.raises(ArticleMapError,match="Control full text"):store.read({**ENTRY,"role":"control_candidate"})


def test_control_rejected_before_metadata_or_cache_access(tmp_path):
    p=Provider()
    with pytest.raises(ArticleMapError,match="Control full text"):
        AuditPrimarySources(p,FilePrimarySourceStore(tmp_path),convert_xml).execute([{**ENTRY,"role":"control_candidate"}])
    assert p.calls==[]


def test_no_pmc_route_is_not_abstract_as_fulltext(tmp_path):
    p=Provider();p.metadata=lambda _:metadata_record({**ROW,"pmcid":None,"isOpenAccess":"N","inPMC":"N"})
    r=AuditPrimarySources(p,FilePrimarySourceStore(tmp_path),convert_xml).execute([ENTRY])[0]
    assert r["status"]=="no_pmc_xml_route" and not (tmp_path/ENTRY["id"]/"article.md").exists()


def test_network_failure_does_not_publish_partial_fulltext(tmp_path):
    p=Provider();p.training_xml=lambda *args:(_ for _ in ()).throw(TimeoutError("Synthetic HTTP timeout"))
    with pytest.raises(TimeoutError):AuditPrimarySources(p,FilePrimarySourceStore(tmp_path),convert_xml).execute([ENTRY])
    assert not (tmp_path/ENTRY["id"]/"metadata.json").exists()


def test_non_open_access_pmc_is_recorded_without_a_different_download_route(tmp_path):
    p=Provider();p.metadata=lambda _:metadata_record({**ROW,"isOpenAccess":"N"})
    r=AuditPrimarySources(p,FilePrimarySourceStore(tmp_path),convert_xml).execute([ENTRY])[0]
    assert r["status"]=="not_selected_for_open_access_xml" and p.calls==[]
    assert not (tmp_path/ENTRY["id"]/"article.md").exists()


def test_detached_tables_figures_and_captions_are_preserved_once():
    xml=XML.replace('<table-wrap id="T1"><label>Table 1</label><graphic href="table.png"/></table-wrap>','')
    xml=xml.replace('</article>','<floats-group><table-wrap id="T2"><label>Table 2</label><caption><p>Detached caption</p></caption><table><tr><th>Age</th><th>Rate</th></tr><tr><td>75–79</td><td>12.4</td></tr></table></table-wrap><fig id="F1"><caption><p>Detached figure caption</p></caption></fig></floats-group></article>')
    text=convert_primary_xml(xml);identity=xml_identity(xml,metadata_record(ROW))
    assert text.count('Table 2 Detached caption')==1 and text.count('75–79 | 12.4')==1
    assert text.count('Detached figure caption')==1 and len(identity["tables"])==1
    assert identity["tables"][0]["xml_rows"]==2 and identity["figures"]==1


def test_inline_objects_not_duplicated_by_primary_converter():
    assert convert_primary_xml(XML).count('Table 1')==1
