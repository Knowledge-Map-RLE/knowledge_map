"""Перенос сохраняет различия исследований и не использует значения удержанной группы."""
import copy
import json
from pathlib import Path

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.cohort_transfer import forecast_fold, evaluate_folds, RateContext, RateQuery, RateObservation, screen_pair
from application.cohort_transfer import SealCohortTransfer, EvaluateCohortTransfer
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.empirical_inference_files import FileEmpiricalControls

PREPARED=Path(__file__).resolve().parents[2]/"eval/free_prediction/cohort-transfer-v1/prepared"


def context(study,family):
    source=json.loads((PREPARED/"fold-1.json").read_text(encoding="utf-8"))["training"][0]["context"]
    c=copy.deepcopy(source);c.update(study_id=study,family_id=family,endpoint="MCI",criteria="synthetic diagnostic criterion",
        threshold_sd="1",dementia_exclusion="synthetic verified",norms="synthetic verified",followup_years="5",followup_kind="maximum",
        country="synthetic country",calendar_period="synthetic period",attrition_adjustment="synthetic verified",
        sample_n="100",female_percent="50",education="synthetic verified",place="synthetic site",response_rate="100%")
    return c


def observation(study,family,age,value):
    return {"id":study+str(age),"context":context(study,family),"age":[age,age+4],"value":str(value),
        "interval":[str(value-1),str(value+1)],"evidence_ids":["synthetic-unit"]}


def fold():
    return {"fold_id":"synthetic","withheld_family":"C","training":[observation("a","A",75,10),observation("a","A",80,20),
        observation("b","B",75,11),observation("b","B",80,21)],
        "queries":[{"id":"q","context":context("c","C"),"ages":[[75,79],[80,84]],"evidence_ids":["synthetic-metadata"]}],
        "evidence":{},"labels":{}}


def test_two_groups_support_joint_order_without_numeric_or_causal_claim():
    data=fold();before=copy.deepcopy(data);r=forecast_fold(data)
    assert data==before
    for mode in ("strict","exploratory"):
        p=r["predictions"][mode][0]
        assert p["order"]=="higher" and len(p["family_votes"])==2
        assert p["numeric_prediction"] is None and p["causal"] is False and p["statistical_difference_claimed"] is False
        assert all(len(w["observation_ids"])==2 for w in p["witnesses"])


def test_multiple_publications_in_one_group_are_not_two_supports():
    data=fold()
    for item in data["training"]:item["context"]["family_id"]="A"
    assert forecast_fold(data)["predictions"]["exploratory"][0]["reason"]=="insufficient_distinct_provenance_groups"


def test_conflicting_results_inside_possible_overlap_group_block_consensus():
    data=fold();data["training"] += [observation("a-other","A",75,20),observation("a-other","A",80,10)]
    p=forecast_fold(data)["predictions"]["exploratory"][0]
    assert p["family_votes"]["A"]=="mixed" and p["reason"]=="conflicting_source_orders"


def test_whole_family_including_other_subtype_must_be_excluded():
    data=fold();leak=observation("c-extra","C",75,15);leak["context"]["endpoint"]="aMCI";data["training"].append(leak)
    with pytest.raises(ArticleMapError,match="leaked"):forecast_fold(data)


@pytest.mark.parametrize("field,value",[("endpoint","aMCI"),("measure","prevalence"),("unit","percent"),("design","cross_sectional")])
def test_foundational_context_mismatch_blocks_exploratory_transfer(field,value):
    data=fold();data["queries"][0]["context"][field]=value
    assert forecast_fold(data)["predictions"]["exploratory"][0]["order"] is None


def test_context_difference_is_visible_and_not_declared_equivalence():
    data=fold();data["queries"][0]["context"]["country"]="other country"
    r=forecast_fold(data)
    assert r["predictions"]["strict"][0]["order"] is None
    p=r["predictions"]["exploratory"][0]
    assert p["order"]=="higher" and all("country" in w["differences"] for w in p["witnesses"])
    assert p["status"]=="exploratory_hypothesis"


def test_unknown_modifier_is_not_a_proven_equal_context():
    data=fold()
    for item in data["training"]:item["context"]["norms"]=None
    data["queries"][0]["context"]["norms"]=None
    assert forecast_fold(data)["predictions"]["strict"][0]["order"] is None
    assert forecast_fold(data)["predictions"]["exploratory"][0]["witnesses"][0]["differences"]["norms"]=={"source":None,"query":None}


def test_different_age_pair_is_not_replaced_by_a_global_trend():
    data=fold();data["queries"][0]["ages"]=[[70,74],[75,79]]
    assert forecast_fold(data)["predictions"]["exploratory"][0]["order"] is None
    assert forecast_fold(data)["frequency"][0]["order"]=="higher"


def test_hidden_value_extra_field_and_nonadjacent_query_rejected():
    data=fold();data["queries"][0]["values"]=[10,20]
    with pytest.raises(ArticleMapError,match="hidden estimates"):forecast_fold(data)
    del data["queries"][0]["values"];data["queries"][0]["ages"]=[[70,74],[80,84]]
    with pytest.raises(ArticleMapError,match="adjacent"):forecast_fold(data)


def test_rate_interval_and_duplicate_observations_rejected():
    data=fold();data["training"][0]["interval"]=["11","12"]
    with pytest.raises(ArticleMapError,match="outside"):forecast_fold(data)
    data=fold();data["training"].append(copy.deepcopy(data["training"][0]))
    with pytest.raises(ArticleMapError,match="Duplicate"):forecast_fold(data)


def test_source_pair_screen_rejects_prevalence_and_overlap():
    a,b=context("a","A"),context("b","B");b["measure"]="prevalence"
    assert screen_pair(RateContext.parse(a),RateContext.parse(b))["reason"]=="different_measure"
    b=context("b","A")
    assert screen_pair(RateContext.parse(a),RateContext.parse(b))["status"]=="not_independent_support"


def test_wrong_order_is_retained_and_overlapping_intervals_not_called_significance():
    results=[forecast_fold(fold())]
    control={"q":{"values":["20","10"],"intervals":[["5","30"],["5","30"]]}}
    r=evaluate_folds(results,control)
    assert r["modes"]["exploratory"]["wrong_order"]==1
    assert r["modes"]["exploratory"]["rows"][0]["intervals_overlap"] is True
    assert r["new_scientific_predictions"]==0 and r["independent_success"] is False
    assert results[0]["predictions"]["exploratory"][0]["order"]=="higher"


def test_prepared_fold_evidence_does_not_expose_held_out_numeric_cells():
    data=FileCohortTransferInputs(PREPARED/"inputs-manifest.json").read_inputs()
    hidden=json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))
    assert len(data["folds"])==6
    for f in data["folds"]:
        refs={k for q in f["queries"] for k in hidden["controls"][q["id"]]["evidence_ids"] if k!="T2:incidence-unit"}
        assert not refs & set(f["evidence"])
        assert all(o["context"]["family_id"]!=f["withheld_family"] for o in f["training"])


class Controls:
    def __init__(self,store):self.store,self.reads=store,0
    def read_controls(self):
        assert list(self.store.root.glob("*/seal.json"));self.reads+=1
        return json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))


def test_all_folds_sealed_before_controls_and_repeat_preserves_bytes(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,"create_connection",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No models or network")))
    store=FilePredictionStore(tmp_path);inputs=FileCohortTransferInputs(PREPARED/"inputs-manifest.json");controls=Controls(store)
    with pytest.raises(ArticleMapError,match="Seal required"):EvaluateCohortTransfer(controls,store).execute("0"*64,{"code":"1"})
    assert controls.reads==0
    sealed=SealCohortTransfer(inputs,store).execute({"code":"1"});path=store.path(sealed["run_id"])/"predictions.json";raw=path.read_bytes()
    with pytest.raises(ArticleMapError,match="implementation changed"):
        EvaluateCohortTransfer(controls,store).execute(sealed["run_id"],{"code":"2"})
    assert controls.reads==0
    ev=EvaluateCohortTransfer(controls,store).execute(sealed["run_id"],{"code":"1"})
    assert ev["independent_success"] is False and ev["modes"]["exploratory"]["queries"]==32
    assert SealCohortTransfer(inputs,store).execute({"code":"1"})==sealed and path.read_bytes()==raw
