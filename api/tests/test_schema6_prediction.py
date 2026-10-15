"""Раздельная загрузка цели, несколько предпосылок и ограничения прогноза."""
import copy
import json

import pytest

from application.development_prediction import SealSourcePrediction, EvaluateSourcePrediction
from domain.development_prediction import fit_predict
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, fingerprint
from infrastructure.development_prediction_store import FilePredictionStore
from domain.comparison_normalization import normalize_map, semantic_attributes
from domain.article_comparison import compare_knowledge


def graph(article, terms, head=True, alternative=False):
    concepts = [{"id": "C"+str(i), "display_text": t, "aliases": []} for i, t in enumerate(terms)]
    pairs = [(0,1),(1,2)] + ([(0,2)] if head else [])
    knowledge = []
    for i,(a,b) in enumerate(pairs,1):
        s = {"statement_id":"S"+str(i),"predicate":"causes","roles":[{"role":"cause","concept_id":"C"+str(a),"knowledge_id":None},
            {"role":"effect","concept_id":"C"+str(b),"knowledge_id":None}],"quantifier":None,"modality":None,"temporal_context":None,
            "conditions":["Synthetic conditional example"],"negated":False,"qualifiers":{"attributes":[]},"provenance":{"unit_ids":["U1"]}}
        knowledge.append({"knowledge_id":"K"+str(i),"kind":"state","knowledge_kind":"rule","action_status":None,
            "display_text":f'{terms[a]} causes {terms[b]}',"semantic_frame":{"logic":"single","statements":[s]},"provenance":{"unit_ids":["U1"]}})
    transitions = ([{"sources":["B1","B2"],"target":"B3"}] if head else [])
    if alternative and head:
        transitions = [{"sources":["B1"],"target":"B3"},{"sources":["B2"],"target":"B3"}]
    return {"article_id":article,"run_id":"run-"+article,"source":{"sha256":article},"graph":{"schema_version":6,"concepts":concepts,
        "knowledge":knowledge,"nodes":[{"id":"B"+str(i),"knowledge_id":"K"+str(i)} for i in range(1,len(knowledge)+1)],
        "transitions":transitions,"edges":[{"source":s,"target":t["target"]} for t in transitions for s in t["sources"]]}}


def test_source_only_learning_produces_grounded_two_premise_hypotheses(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client,"send",lambda *a,**k: (_ for _ in ()).throw(AssertionError("No model calls")))
    maps=[graph("one",["alpha","beta","gamma"]),graph("two",["delta","epsilon","zeta"]),graph("three",["theta","iota","kappa"],head=False)]
    before=copy.deepcopy(maps);result=fit_predict(maps)
    assert maps==before
    candidates=result["predictions"]["graph"]
    assert candidates and all(c["status"]=="statistical_hypothesis" and c["support"]>=2 for c in candidates)
    assert any({v for _,v in c["atom"]["roles"]}=={"theta","kappa"} for c in candidates)
    assert all(len(c["premises"])==2 for c in candidates)
    assert result["model_calls"]==0


def test_alternative_paths_are_not_combined_into_joint_requirements():
    maps=[graph("one",["alpha","beta","gamma"],alternative=True),graph("two",["delta","epsilon","zeta"],alternative=True)]
    for m in maps:
        for i, k in enumerate(m["graph"]["knowledge"][:2]):
            k["semantic_frame"]["statements"][0]["roles"]=copy.deepcopy(m["graph"]["knowledge"][-1]["semantic_frame"]["statements"][0]["roles"])
            k["semantic_frame"]["statements"][0]["predicate"]="premise "+("first" if i==0 else "second")
    result=fit_predict(maps)
    assert len(result["rules"]["graph"])==2
    assert all(len(rule["body"])==1 for rule in result["rules"]["graph"])


def test_visible_cycle_and_unknown_edge_are_rejected():
    m=graph("one",["alpha","beta","gamma"])
    m["graph"]["edges"].append({"source":"B3","target":"B1"})
    with pytest.raises(ArticleMapError,match="DAG"):fit_predict([m])
    m["graph"]["edges"]=[{"source":"missing","target":"B1"}]
    with pytest.raises(ArticleMapError,match="Unknown"):fit_predict([m])


def test_study_cohorts_can_support_a_template_without_merging_participants():
    maps=[graph("one",["alpha patients","beta","gamma"]),graph("two",["delta patients","epsilon","zeta"]),
          graph("three",["theta patients","iota","kappa"],head=False)]
    # Обе предпосылки и заключение имеют одну область исследования.
    for m in maps:
        for k in m["graph"]["knowledge"]:
            s=k["semantic_frame"]["statements"][0]
            s["roles"].append({"role":"sample","concept_id":"C0","knowledge_id":None})
    result=fit_predict(maps)
    assert result["rules"]["graph"]
    assert result["predictions"]["graph"]
    for c in result["predictions"]["graph"]:
        assert len({p["source_id"] for p in c["premises"]})==1
        assert json.loads(c["atom"]["scope"])["scope"]["study_group"]==c["premises"][0]["source_id"]


@pytest.mark.parametrize("field,value",[("negated",True),("quantifier","some"),("modality","may"),("temporal_context","different period")])
def test_constraints_cannot_be_dropped_to_inflate_cross_source_support(field,value):
    maps=[graph("one",["alpha","beta","gamma"]),graph("two",["delta","epsilon","zeta"])]
    maps[1]["graph"]["knowledge"][-1]["semantic_frame"]["statements"][0][field]=value
    assert fit_predict(maps)["rules"]["graph"]==[]


def test_auxiliary_description_is_preserved_outside_semantic_equality():
    a,b=graph("one",["alpha","beta","gamma"]),graph("two",["alpha","beta","gamma"])
    a["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]["qualifiers"]["attributes"]=[{"name":"source_grounded_description","value":"Paraphrased text","unit":None}]
    left,right=normalize_map(a)[0],normalize_map(b)[0]
    assert left["statements"][0]["auxiliary_attributes"][0]["value"]=="Paraphrased text"
    assert compare_knowledge(left,right)["relations"]==["equivalent"]


def test_conversion_range_boundaries_match_without_equating_units():
    a,_=semantic_attributes([{"name":"conversion_percent_min","value":6,"unit":None},{"name":"conversion_percent_max","value":44.8,"unit":None}],"mci_progression_risk")
    b,_=semantic_attributes([{"name":"range","value":"6.0–44.8","unit":"percent"}],"conversion_range")
    assert a==b
    c,_=semantic_attributes([{"name":"range","value":"6.0–44.8","unit":"per1000personyear"}],"conversion_range")
    assert a!=c


def ref(article):return {"article_id":article,"pipeline_id":"text_reified","run_id":"run-"+article}


class Maps:
    def __init__(self,store):self.store=store;self.calls=[]
    def authorize(self,article,owner):
        if owner!="owner":raise ArticleMapAccessDenied("Denied")
    def get(self,article,pipeline,owner,run):
        self.authorize(article,owner);self.calls.append(article)
        if article=="target":assert any(self.store.root.glob("*/seal.json")),"Target read before seal"
        return graph(article,["alpha","beta","gamma"])


class Controls:
    def select(self,refs):return {"version":"unannotated","pairs":[]}


def test_target_is_loaded_only_after_immutable_seal_and_repeat_is_reproducible(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    app=SealSourcePrediction(maps,store)
    sealed=app.execute([ref("one"),ref("two")],"owner")
    assert maps.calls==["one","two"]
    seal_path=store.path(sealed["run_id"])/"predictions.json";before=seal_path.read_bytes()
    result=EvaluateSourcePrediction(maps,store,Controls()).execute(sealed["run_id"],ref("target"),"owner")
    assert maps.calls[-1]=="target" and seal_path.read_bytes()==before
    assert result["binding"]["prediction_sha256"]==fingerprint(sealed)
    assert app.execute([ref("one"),ref("two")],"owner")==sealed


def test_full_explicit_corpus_above_legacy_twenty_source_limit_is_supported(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    refs=[ref(f"source-{index}") for index in range(21)]
    sealed=SealSourcePrediction(maps,store).execute(refs,"owner")
    assert len(sealed["binding"]["sources"])==21
    assert len({item["article_id"] for item in sealed["binding"]["sources"]})==21
    assert len(maps.calls)==21


def test_leaked_target_and_foreign_owner_are_rejected(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    sealed=SealSourcePrediction(maps,store).execute([ref("one"),ref("two")],"owner")
    with pytest.raises(ArticleMapError,match="leaked"):
        EvaluateSourcePrediction(maps,store,Controls()).execute(sealed["run_id"],ref("one"),"owner")
    with pytest.raises(ArticleMapAccessDenied):SealSourcePrediction(maps,store).execute([ref("one"),ref("two")],"other")


def test_modified_seal_is_rejected(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    sealed=SealSourcePrediction(maps,store).execute([ref("one"),ref("two")],"owner")
    path=store.path(sealed["run_id"])/"predictions.json";changed=copy.deepcopy(sealed);changed["predictions"]["graph"]=[]
    changed["limits"]["min_support"]=1;path.write_text(json.dumps(changed),encoding="utf-8")
    with pytest.raises(ArticleMapError,match="changed"):store.read_seal(sealed["run_id"])
