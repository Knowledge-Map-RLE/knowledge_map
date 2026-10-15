"""Вложенный выбор не получает внешние числа и учитывает группы происхождения."""
import copy
import json
from pathlib import Path

import pytest

from domain.article_maps import ArticleMapError
from domain.cohort_transfer import RateObservation, RateQuery, witness_pairs
from domain.conditional_cohort_transfer import CANDIDATES, fit, predict, forecast_conditional_fold, evaluate
from application.conditional_cohort_transfer import SealConditionalTransfer, EvaluateConditionalTransfer
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.development_prediction_store import FilePredictionStore

PREPARED = Path(__file__).resolve().parents[2]/"eval/free_prediction/cohort-transfer-v1/prepared"


def prepared_fold():
    return json.loads((PREPARED/"fold-1.json").read_text(encoding="utf-8"))


def context(study, family, criteria="criterion-A"):
    c = copy.deepcopy(prepared_fold()["training"][0]["context"])
    c.update(study_id=study, family_id=family, endpoint="MCI", criteria=criteria, threshold_sd="1", norms="known",
             dementia_exclusion="known", followup_kind="maximum")
    return c


def pair(study, family, left, right, criteria="criterion-A", ages=(75,80)):
    return [RateObservation.parse({"id": study+str(age), "context": context(study, family, criteria),
            "age": [age,age+4], "value": str(value), "interval": [str(value-1),str(value+1)], "evidence_ids": ["synthetic"]})
            for age,value in zip(ages,(left,right))]


def query(criteria="criterion-A"):
    return RateQuery.parse({"id": "q", "context": context("query","Q",criteria), "ages": [[75,79],[80,84]], "evidence_ids": ["synthetic-metadata"]})


def spec(name):
    return next(s for s in CANDIDATES if s.id==name)


def test_joint_premises_context_filter_and_majority_preserve_hypothesis_status():
    obs = pair("a","A",10,20)+pair("b","B",12,22)+pair("c","C",20,10,"criterion-B")
    w = witness_pairs(obs)
    assert predict(query(),w,spec("none:unanimous"))["order"] is None
    for s in ("none:two_thirds","criteria:unanimous"):
        p = predict(query(),w,spec(s))
        assert p["order"]=="higher" and p["causal"] is False and p["numeric_prediction"] is None
        assert p["equivalence_confirmed"] is False and all(len(x["observation_ids"])==2 for x in p["witnesses"])
    filtered = predict(query(),w,spec("criteria:unanimous"))
    assert filtered["rejected"]["required_modifier_unknown_or_different"]==1


def test_unknown_required_context_is_not_a_match():
    raw = {"id":"q","context":context("query","Q"),"ages":[[75,79],[80,84]],"evidence_ids":["metadata"]}
    raw["context"]["criteria"] = None
    p = predict(RateQuery.parse(raw),witness_pairs(pair("a","A",10,20)+pair("b","B",10,20)),spec("criteria:two_thirds"))
    assert p["order"] is None and p["rejected"]["required_modifier_unknown_or_different"]==2


def test_mixed_group_is_not_discarded_to_manufacture_majority():
    obs=pair("a","A",10,20)+pair("b","B",10,20)+pair("c","C",10,20)+pair("cx","C",20,10)+pair("d","D",20,10)
    p=predict(query(),witness_pairs(obs),spec("none:two_thirds"))
    assert p["family_votes"]["C"]=="mixed" and p["order"] is None


def test_subtypes_and_repeated_publications_are_not_extra_independent_support():
    obs=pair("a","A",10,20)+pair("b","A",10,20)
    assert predict(query(),witness_pairs(obs),spec("none:two_thirds"))["order"] is None


@pytest.mark.parametrize("field,value",[("endpoint","aMCI"),("measure","prevalence"),("unit","percent"),("design","cross_sectional")])
def test_core_mismatch_blocks_every_specification(field,value):
    raw={"id":"q","context":context("query","Q"),"ages":[[75,79],[80,84]],"evidence_ids":["metadata"]}
    raw["context"][field]=value
    w=witness_pairs(pair("a","A",10,20)+pair("b","B",10,20))
    assert all(predict(RateQuery.parse(raw),w,s)["order"] is None for s in CANDIDATES)


def test_inner_training_excludes_entire_validation_family():
    obs=pair("a","A",10,20)+pair("b","B",10,20)+pair("c","C",10,20)+pair("d","D",10,20)
    result=fit(obs)
    assert len(result["scores"])==12 and result["outer_controls_read"] is False
    assert result["selected"]["id"]=="none:unanimous"
    byid={o.id:o.context.family_id for o in obs}
    for audit in result["inner_audit"]:
        for g in audit["groups"]:
            assert g["validation_family"] not in g["fit_families"]
            assert all(byid[k]!=g["validation_family"] for k in g["fit_observation_ids"])
            assert all(byid[k]!=g["validation_family"] for r in g["rows"] for k in r["support_observation_ids"])


def test_selector_can_learn_context_when_independent_training_groups_support_it():
    # Искусственный контроль способности обучения, а не результат научных источников.
    obs=[]
    for i in range(3):obs+=pair("a"+str(i),"A"+str(i),10,20,"criterion-A")
    for i in range(3):obs+=pair("b"+str(i),"B"+str(i),20,10,"criterion-B")
    r=fit(obs)
    assert r["selected"]["id"]=="criteria:unanimous"
    w=witness_pairs(obs)
    assert predict(query("criterion-A"),w,spec(r["selected"]["id"]))["order"]=="higher"
    assert predict(query("criterion-B"),w,spec(r["selected"]["id"]))["order"]=="lower"


def test_selector_does_not_depend_on_outer_queries_or_values():
    fold=prepared_fold();result=forecast_conditional_fold(fold)
    changed=copy.deepcopy(fold)
    for q in changed["queries"]:q["context"].update(criteria="changed outer context",country="other")
    assert forecast_conditional_fold(changed)["selection"]==result["selection"]
    changed=copy.deepcopy(fold);changed["queries"][0]["values"]=["9","4"]
    with pytest.raises(ArticleMapError,match="hidden estimates"):forecast_conditional_fold(changed)


def test_whole_outer_group_exclusion_is_required():
    fold=prepared_fold();leak=copy.deepcopy(fold["training"][0]);leak["id"]="leak"
    leak["context"]["family_id"]=fold["withheld_family"];leak["context"]["endpoint"]="aMCI";fold["training"].append(leak)
    with pytest.raises(ArticleMapError,match="leaked"):forecast_conditional_fold(fold)


def test_no_inner_coverage_does_not_trigger_another_predictor():
    obs=pair("a","A",10,20,ages=(65,70))+pair("b","B",10,20,ages=(75,80))+pair("c","C",10,20,ages=(85,90))
    r=fit(obs)
    assert r["selected"] is None and all(not s["eligible"] for s in r["scores"])


def test_too_few_training_groups_rejected():
    with pytest.raises(ArticleMapError,match="three training"):fit(pair("a","A",10,20)+pair("b","B",10,20))


class Controls:
    def __init__(self,store):self.store,self.reads=store,0
    def read_controls(self):
        assert list(self.store.root.glob("*/seal.json"));self.reads+=1
        return json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))


def test_seal_before_controls_repeat_and_implementation_mismatch(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,"create_connection",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No models/network")))
    store=FilePredictionStore(tmp_path);ctrl=Controls(store)
    with pytest.raises(ArticleMapError,match="Seal required"):EvaluateConditionalTransfer(ctrl,store).execute("0"*64,{"code":"1"})
    assert ctrl.reads==0
    port=FileCohortTransferInputs(PREPARED/"inputs-manifest.json")
    sealed=SealConditionalTransfer(port,store).execute({"code":"1"})
    before=(store.path(sealed["run_id"])/"predictions.json").read_bytes()
    assert SealConditionalTransfer(port,store).execute({"code":"1"})==sealed
    with pytest.raises(ArticleMapError,match="implementation changed"):EvaluateConditionalTransfer(ctrl,store).execute(sealed["run_id"],{"code":"2"})
    assert ctrl.reads==0
    result=EvaluateConditionalTransfer(ctrl,store).execute(sealed["run_id"],{"code":"1"})
    assert result["independent_success"] is False and result["new_scientific_predictions"]==0
    assert result["modes"]["conditional"]["queries"]==32
    assert (store.path(sealed["run_id"])/"predictions.json").read_bytes()==before
    assert EvaluateConditionalTransfer(ctrl,store).execute(sealed["run_id"],{"code":"1"})==result


def test_control_family_or_query_identity_mismatch_rejected():
    data=FileCohortTransferInputs(PREPARED/"inputs-manifest.json").read_inputs()
    folds=[forecast_conditional_fold(f) for f in data["folds"]]
    controls=json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))["controls"]
    bad=copy.deepcopy(controls);next(iter(bad.values()))["family_id"]="unrelated"
    with pytest.raises(ArticleMapError,match="outside held-out"):evaluate(folds,bad)
    bad=copy.deepcopy(controls);bad.pop(next(iter(bad)))
    with pytest.raises(ArticleMapError,match="identities"):evaluate(folds,bad)
