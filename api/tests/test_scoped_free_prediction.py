"""Числа, контексты и происхождение остаются проверяемыми после адаптации."""
import copy
import json
from dataclasses import replace
import pytest

from domain.scoped_free_prediction import project_evidence, contextual_analogies, measurement_profile
from domain.article_maps import ArticleMapError
from application.scoped_free_prediction import SealScopedPrediction, EvaluateScopedPrediction
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_free_prediction import triplet as old_triplet, record as old_record
from tests.test_schema6_prediction import graph, ref, Controls


def enrich(r):
    r["knowledge"].update({"id":r["occurrence"].node_id,"text":r["occurrence"].display_text,"knowledge_kind":"assertion"})
    return r


def record(*args,**kwargs):return enrich(old_record(*args,**kwargs))


def triplet():return [enrich(r) for r in old_triplet()]


def test_different_measured_values_do_not_require_equal_numbers():
    records=triplet();first,second=records[:2]
    for r,n in ((first,1.1),(second,2.2)):
        a=r["occurrence"].atom;s=json.loads(a.scope);s["attributes"]=[{"name":"value","value":str(n),"unit":"pg/ml"}]
        r["occurrence"]=replace(r["occurrence"],atom=replace(a,scope=json.dumps(s,sort_keys=True)))
    before=copy.deepcopy(records)
    candidates,d=contextual_analogies(records,{"one":"f1"})
    assert records==before and len(candidates)==1
    assert candidates[0]["status"]=="exploratory_analogy" and candidates[0]["support"]==0
    assert json.loads(candidates[0]["atom"]["scope"])["attributes"]==[]


@pytest.mark.parametrize("name,unit",[("age threshold","year"),("followup","month"),("dose","mg"),("sample size","participants")])
def test_numeric_scientific_restrictions_are_not_masked(name,unit):
    records=triplet()
    for r,n in zip(records[:2],(10,20)):
        a=r["occurrence"].atom;s=json.loads(a.scope);s["attributes"]=[{"name":name,"value":str(n),"unit":unit}]
        r["occurrence"]=replace(r["occurrence"],atom=replace(a,scope=json.dumps(s,sort_keys=True)))
    assert contextual_analogies(records,{"one":"f1"})[0]==[]


def test_numeric_head_is_not_invented_and_unit_mismatch_blocks_witnesses():
    records=triplet()
    for r,unit in zip(records[:2],("percent","per1000personyear")):
        a=r["occurrence"].atom;s=json.loads(a.scope);s["attributes"]=[{"name":"value","value":"10","unit":unit}]
        r["occurrence"]=replace(r["occurrence"],atom=replace(a,scope=json.dumps(s,sort_keys=True)))
    assert contextual_analogies(records,{"one":"f1"})[0]==[]
    records=triplet();a=records[-1]["occurrence"].atom;s=json.loads(a.scope)
    s["attributes"]=[{"name":"r","value":"0.4","unit":"dimensionless"}]
    records[-1]["occurrence"]=replace(records[-1]["occurrence"],atom=replace(a,scope=json.dumps(s,sort_keys=True)))
    assert contextual_analogies(records,{"one":"f1"})[0]==[]


def test_own_head_modality_preserved_without_strengthening():
    records=triplet();a=records[-1]["occurrence"].atom;s=json.loads(a.scope);s["scope"]["modality"]="may"
    records[-1]["occurrence"]=replace(records[-1]["occurrence"],atom=replace(a,scope=json.dumps(s,sort_keys=True)))
    candidates,_=contextual_analogies(records,{"one":"f1"})
    assert candidates and json.loads(candidates[0]["atom"]["scope"])["scope"]["modality"]=="may"


def test_generic_unary_predicate_does_not_make_entities_interchangeable():
    r=[record("characterized by",[("subject","cytokine")],sid="a"),
       record("characterized by",[("subject","bias scale")],sid="b"),
       record("associated with",[("factor","cytokine"),("outcome","decline")],sid="q")]
    items,d=contextual_analogies(r,{"one":"f1"})
    assert not items and d["counts"]["unary_generic_predicate"]==1


def test_adapter_retains_scientific_values_and_separate_provenance():
    m=graph("one",["alpha","beta","gamma"]);k=m["graph"]["knowledge"][0];s=k["semantic_frame"]["statements"][0]
    k["display_text"]+=" (Table 2)"
    s["qualifiers"]["attributes"]=[{"name":"table","value":2,"unit":None},{"name":"p","value":.05,"unit":None},
        {"name":"beta","value":-.13,"unit":None},{"name":"age threshold","value":60,"unit":"year"}]
    before=copy.deepcopy(m);projected,ledger=project_evidence([m]);attrs=projected[0]["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]["qualifiers"]["attributes"]
    assert m==before
    assert attrs==[{"name":"p","value":.05,"unit":"dimensionless"},{"name":"beta","value":-.13,"unit":None},
                  {"name":"age threshold","value":60,"unit":"year"}]
    assert len(ledger)==2 and all(x["provenance"]["unit_ids"]==["U1"] for x in ledger)


def test_unproven_provenance_marker_stays_in_semantics():
    m=graph("one",["alpha","beta","gamma"])
    s=m["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]
    s["qualifiers"]["attributes"]=[{"name":"table","value":2,"unit":None}]
    p,l=project_evidence([m])
    assert p==[m] and l==[]


@pytest.mark.parametrize("marker",[2,"2","Table 2"])
def test_explicit_table_marker_formats_go_to_evidence(marker):
    m=graph("one",["alpha","beta","gamma"]);k=m["graph"]["knowledge"][0];k["display_text"]+=" (Table 2)"
    k["semantic_frame"]["statements"][0]["qualifiers"]["attributes"]=[{"name":"table","value":marker,"unit":None}]
    p,l=project_evidence([m]);assert len(l)==1 and l[0]["original"]["value"]==marker
    assert p[0]["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]["qualifiers"]["attributes"]==[]


def test_author_speech_and_diagnostic_definition_are_not_predicted_by_analogy():
    for predicate,kind,reason in (("author interpretation","observation","source_bound_attribution_not_transferable"),
        ("has dementia","definition","diagnostic_definition_not_a_new_forecast")):
        r=triplet();a=r[-1]["occurrence"].atom;r[-1]["occurrence"]=replace(r[-1]["occurrence"],atom=replace(a,predicate=predicate))
        r[-1]["knowledge"]["knowledge_kind"]=kind
        candidates,d=contextual_analogies(r,{"one":"f1"})
        assert not candidates and d["counts"][reason]>0


class Maps:
    def __init__(self,store):self.store,self.reads=store,[]
    def authorize(self,article,owner):assert owner=="owner"
    def get(self,article,pipeline,owner,run):
        self.authorize(article,owner)
        if article=="target":assert list(self.store.root.glob("*/seal.json"))
        self.reads.append(article)
        return graph(article,["alpha","beta","gamma"])


def test_source_only_seal_and_target_evaluation_are_separate(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    sealed=SealScopedPrediction(maps,store).execute([ref("one"),ref("two")],{"one":"f1","two":"f2"},"owner",{})
    assert maps.reads==["one","two"]
    before=(store.path(sealed["run_id"])/"predictions.json").read_bytes()
    ev=EvaluateScopedPrediction(maps,store,Controls()).execute(sealed["run_id"],ref("target"),"owner")
    assert maps.reads[-1]=="target" and ev["independent_success"] is False
    assert (store.path(sealed["run_id"])/"predictions.json").read_bytes()==before
    with pytest.raises(ArticleMapError,match="leaked"):
        EvaluateScopedPrediction(maps,store,Controls()).execute(sealed["run_id"],ref("one"),"owner")
