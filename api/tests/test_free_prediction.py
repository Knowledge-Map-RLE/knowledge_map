"""Новизна, область исследования и изоляция свободного прогноза."""
import copy
import json
from dataclasses import replace

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.free_prediction import analogy_candidates, semantic_key, forecast
from domain.reference_prediction import Atom, Occurrence
from application.free_prediction import SealFreePrediction, EvaluateFreePrediction
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import graph, ref
from domain.free_prediction import diagnose_witnesses, already_represented
from infrastructure.free_prediction_snapshots import FileForecastMaps
from domain.article_maps import ArticleMapAccessDenied
from hashlib import sha256


def record(predicate, roles, *, negated=False, scope=None, source="one", sid="s", eligible=True):
    scope = scope or {"scope": {"quantifier": None,"modality": None,"time": "fixed experimental setting",
            "conditions": [], "study_group": None}, "attributes": [], "action_status": None,"logic": "single"}
    atom = Atom(predicate, "state", tuple(sorted(roles)), json.dumps(scope, sort_keys=True), negated)
    return {"occurrence": Occurrence(source,sid,"source text",{"unit_ids":["U1"]},atom),
            "knowledge": {"action_status":None}, "eligible":eligible}


def triplet():
    return [record("binds",[("ligand","alpha"),("receptor","gamma")],sid="a"),
            record("binds",[("ligand","beta"),("receptor","gamma")],sid="b"),
            record("associated with",[("factor","alpha"),("outcome","delta")],sid="q")]


def test_analogy_is_novel_grounded_and_not_deduction():
    records=triplet(); before=copy.deepcopy(records)
    items,stats=analogy_candidates(records,{"one":"f1"})
    assert records==before
    assert len(items)==1 and items[0]["status"]=="exploratory_analogy"
    assert items[0]["support"]==0 and len(items[0]["premises"])==3
    assert ("factor","beta") in items[0]["atom"]["roles"]


def test_analogy_cannot_replace_an_outcome_with_a_narrower_outcome():
    records = [
        record("associated with", [("exposure", "telomere length"), ("outcome", "cognitive decline")], sid="K1S1"),
        record("associated with", [("exposure", "telomere length"), ("outcome", "dementia")], sid="K2S1"),
        record("necessary for cognitive decline", [("exposure", "APOE ε4"), ("outcome", "cognitive decline")],
               negated=True, sid="K3S1"),
    ]
    items, stats = analogy_candidates(records, {"one": "f1"})
    assert items == []
    assert stats["outcome_role_substitution_blocked"] > 0


def test_analogy_cannot_use_two_parts_of_one_canonical_block_as_distinct_premises():
    records = [
        record("binds", [("ligand", "alpha"), ("receptor", "gamma")], sid="K1S1"),
        record("binds", [("ligand", "beta"), ("receptor", "gamma")], sid="K1S2"),
        record("associated with", [("factor", "alpha"), ("outcome", "delta")], sid="K2S1"),
    ]
    items, stats = analogy_candidates(records, {"one": "f1"})
    assert items == []
    assert stats["same_canonical_block_pair_blocked"] > 0


def test_analogy_requires_the_conclusion_premise_to_be_a_distinct_canonical_block():
    records = [
        record("binds", [("ligand", "alpha"), ("receptor", "gamma")], sid="K1S1"),
        record("binds", [("ligand", "beta"), ("receptor", "gamma")], sid="K2S1"),
        record("associated with", [("factor", "alpha"), ("outcome", "delta")], sid="K1S2"),
    ]
    items, stats = analogy_candidates(records, {"one": "f1"})
    assert items == []
    assert stats["same_canonical_block_premises_blocked"] > 0


@pytest.mark.parametrize("field,value",[("modality","may"),("time","other period"),
                                        ("quantifier","some"),("study_group","different cohort")])
def test_analogy_cannot_mix_contexts(field,value):
    records=triplet(); atom=records[1]["occurrence"].atom
    scope=json.loads(atom.scope); scope["scope"][field]=value
    records[1]["occurrence"]=replace(records[1]["occurrence"],atom=replace(atom,scope=json.dumps(scope,sort_keys=True)))
    assert analogy_candidates(records,{"one":"f1"})[0]==[]


def test_known_inverse_and_explicit_contradiction_are_not_new():
    records=triplet(); c=analogy_candidates(records,{"one":"f1"})[0][0]
    roles=c["atom"]["roles"]
    for negated in (False,True):
        items,stats=analogy_candidates([*records,record("associated with",roles,negated=negated,sid="known")],{"one":"f1"})
        assert all(i["id"]!=c["id"] for i in items)
    a=record("associated with",[("factor","alpha"),("outcome","beta")])["occurrence"].atom
    b=replace(a,roles=(("factor","beta"),("outcome","alpha")))
    assert semantic_key(a)==semantic_key(b)


def test_numeric_transfer_unknown_context_and_cohort_substitution_are_blocked():
    records=triplet(); atom=records[-1]["occurrence"].atom
    scope=json.loads(atom.scope);scope["attributes"]=[{"name":"beta","value":0.3,"unit":None}]
    records[-1]["occurrence"]=replace(records[-1]["occurrence"],atom=replace(atom,scope=json.dumps(scope,sort_keys=True)))
    assert analogy_candidates(records,{"one":"f1"})[0]==[]
    records=triplet();records[-1]["eligible"]=False
    assert analogy_candidates(records,{"one":"f1"})[0]==[]
    records=[record("has",[("sample",p),("marker","gamma")],sid=p) for p in ("alpha patients","beta patients")]
    records.append(record("associated with",[("factor","alpha patients"),("outcome","delta")],sid="q"))
    assert analogy_candidates(records,{"one":"f1"})[0]==[]


def test_same_provenance_family_cannot_support_learned_template():
    maps=[graph("one",["alpha","beta","gamma"]),graph("two",["delta","epsilon","zeta"]),
          graph("three",["theta","iota","kappa"],head=False)]
    result=forecast(maps,{"one":"same","two":"same","three":"third"})
    assert result["diagnostics"]["family_rejected_templates"]>0
    assert not any(c["operator"]=="source_supported_template" for c in result["predictions"]["free"])


class Maps:
    def __init__(self,store):self.store=store;self.calls=[]
    def authorize(self,article,owner):assert owner=="owner"
    def get(self,article,pipeline,owner,run):
        self.authorize(article,owner)
        if article=="target":assert list(self.store.root.glob("*/seal.json"))
        self.calls.append(article)
        return graph(article,["alpha","beta","gamma"])


class Controls:
    def select(self,refs):return {"pairs":[]}


def test_target_read_only_after_seal_reproducible_and_no_training_on_target(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    app=SealFreePrediction(maps,store)
    sealed=app.execute([ref("one"),ref("two")],{"one":"f1","two":"f2"},"owner",{"question":None})
    assert maps.calls==["one","two"]
    path=store.path(sealed["run_id"])/"predictions.json";before=path.read_bytes()
    result=EvaluateFreePrediction(maps,store,Controls()).execute(sealed["run_id"],ref("target"),"owner")
    assert maps.calls[-1]=="target" and path.read_bytes()==before
    assert result["independent_success"] is False
    with pytest.raises(ArticleMapError,match="leaked"):
        EvaluateFreePrediction(maps,store,Controls()).execute(sealed["run_id"],ref("one"),"owner")
    assert app.execute([ref("one"),ref("two")],{"one":"f1","two":"f2"},"owner",{"question":None})==sealed


def test_diagnostic_context_and_attribute_counts_are_separate():
    records=triplet()[:2];atom=records[1]["occurrence"].atom
    scope=json.loads(atom.scope);scope["scope"]["time"]="another period";scope["attributes"]=[{"name":"n","value":10,"unit":"person"}]
    records[1]["occurrence"]=replace(records[1]["occurrence"],atom=replace(atom,scope=json.dumps(scope,sort_keys=True)))
    counts=diagnose_witnesses(records)["counts"]
    assert counts["single_role_structural_pairs"]==counts["different_scope_bundle_pairs"]==1
    assert counts["different_attributes_pairs"]==counts["different_context_pairs"]==1


def test_weaker_already_known_claim_is_not_novel():
    records=triplet();candidate=analogy_candidates(records,{"one":"f1"})[0][0]
    atom=Atom(**{**candidate["atom"],"roles":tuple(tuple(r) for r in candidate["atom"]["roles"])})
    scope=json.loads(atom.scope);scope["attributes"]=[{"name":"estimate","value":0.7,"unit":"score"}]
    known=record(atom.predicate,atom.roles,scope=scope,sid="known")
    assert already_represented(atom,[known])


def test_duplicate_full_texts_cannot_manufacture_support(tmp_path):
    store=FilePredictionStore(tmp_path);maps=Maps(store)
    original=maps.get
    def duplicate(*args):
        m=original(*args);m["source"]["sha256"]="same-source";return m
    maps.get=duplicate
    with pytest.raises(ArticleMapError,match="Duplicate source text"):
        SealFreePrediction(maps,store).execute([ref("one"),ref("two")],{"one":"f1","two":"f2"},"owner",{})
    assert not list(tmp_path.glob("*/seal.json"))


def snapshot(tmp_path):
    m=graph("one",["alpha","beta","gamma"]);text="😀 scientifically grounded source"
    m["pipeline_id"]="text_reified"
    m["source"]={"text":text,"sha256":sha256(text.encode()).hexdigest(),"offset_encoding":"unicode_codepoints",
                 "content_end":len(text),"units":[{"id":"U1","start":0,"end":len(text),"text":text}]}
    raw=json.dumps(m).encode();path=tmp_path/"map.json";path.write_bytes(raw)
    entry={"reference":ref("one"),"path":str(path),"file_sha256":sha256(raw).hexdigest(),
           "graph_sha256":fingerprint(m["graph"]),"source_sha256":m["source"]["sha256"]}
    return m,entry,path


def test_snapshot_unicode_hashes_and_authorization(tmp_path):
    m,entry,path=snapshot(tmp_path);maps=FileForecastMaps([entry])
    assert maps.get("one","text_reified",maps.owner,"run-one")==m
    with pytest.raises(ArticleMapAccessDenied):maps.get("one","text_reified","foreign","run-one")
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ArticleMapError,match="bytes changed"):maps.get("one","text_reified",maps.owner,"run-one")


def test_snapshot_invalid_unicode_provenance_is_rejected(tmp_path):
    m,entry,path=snapshot(tmp_path)
    m["source"]["units"][0]["start"]=1
    raw=json.dumps(m).encode();path.write_bytes(raw);entry["file_sha256"]=sha256(raw).hexdigest()
    maps=FileForecastMaps([entry])
    with pytest.raises(ArticleMapError,match="Provenance text differs"):
        maps.get("one","text_reified",maps.owner,"run-one")


def test_visible_dag_cycle_rejected_before_forecast():
    m=graph("one",["alpha","beta","gamma"])
    m["graph"]["edges"].append({"source":"B3","target":"B1"})
    with pytest.raises(ArticleMapError,match="DAG"):forecast([m],{"one":"f1"})


def test_total_candidate_budget_and_rank_reproducibility(monkeypatch):
    import domain.free_prediction as module
    items=[{"id":str(i),"support_families":[],"source_families":["f1"],"premises":[{}]} for i in range(25)]
    monkeypatch.setattr(module,"analogy_candidates",lambda *args:(items,{"examined_analogy_combinations":25}))
    maps=[graph("one",["alpha","beta","gamma"]),graph("two",["delta","epsilon","zeta"])]
    a=forecast(maps,{"one":"f1","two":"f2"});b=forecast(maps,{"one":"f1","two":"f2"})
    assert len(a["predictions"]["free"])==20 and a==b
