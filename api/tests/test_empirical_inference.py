"""Статистический вывод не теряет ограничения и не подменяет научный прогноз."""
import copy
import json
from pathlib import Path

import pytest

from domain.article_maps import ArticleMapError
from domain.empirical_inference import run_cases, score
from application.empirical_inference import SealEmpiricalInference, EvaluateEmpiricalInference
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.empirical_inference_files import FileEmpiricalInputs

PREPARED=Path(__file__).resolve().parents[2]/"eval/free_prediction/typed-empirical-pilot-v1/prepared"


def fixture():
    dataset=json.loads((PREPARED/"inputs.json").read_text(encoding="utf-8"))
    return dataset,copy.deepcopy(dataset["cases"][1])


def test_reported_correction_blocks_nominally_significant_sleep_effect():
    dataset,_=fixture();case=dataset["cases"][0]
    result=run_cases([case])[0]
    assert result["status"]=="threshold_not_met" and result["direction"] is None
    assert result["point_sign"]=="positive" and result["causal"] is False and result["future_outcome"] is False
    assert result["premise_groups"]==[[case["effect"]["id"],case["policy"]["id"]]]


@pytest.mark.parametrize("field,value",[("study_id","other-study"),("analysis_id","other-model"),
    ("population_id","other-population"),("design","longitudinal"),("time","follow-up"),
    ("outcome","other-biomarker"),("outcome_scale","log-transformed"),("adjustment",["age"]),("sample_n",63)])
def test_every_context_dimension_blocks_an_unlicensed_join(field,value):
    _,case=fixture();case["policy"]["context"][field]=value
    assert run_cases([case])[0]["reason"]=="incompatible_context"


def test_ambiguous_coding_does_not_make_inactivity_protective():
    dataset,_=fixture();r=run_cases([dataset["cases"][3]])[0]
    assert r["status"]=="threshold_met" and r["direction"]=="negative"
    assert r["real_world_direction"] is None and r["coding"]=="binary_label_ambiguous"


def test_inconsistent_source_is_preserved_and_abstained_not_repaired():
    dataset,_=fixture();before=copy.deepcopy(dataset["cases"][2])
    result=run_cases([before])[0]
    assert result["reason"]=="coefficient_outside_its_reported_interval"
    assert before==dataset["cases"][2] and before["effect"]["coefficient"]=="−0.102"


def test_unknown_units_never_produce_new_effect_size_or_cross_study_claim():
    _,case=fixture();before=copy.deepcopy(case)
    result=run_cases([case])[0]
    assert case==before and case["effect"]["coefficient_unit"] is None
    assert result["invented_effect"] is None
    assert set(result["context"]["adjustment"])==set(case["effect"]["context"]["adjustment"])
    assert {k:v for k,v in result["context"].items() if k!="adjustment"}=={k:v for k,v in case["effect"]["context"].items() if k!="adjustment"}


def test_strict_threshold_boundary_and_zero_coefficient_guard():
    _,case=fixture();case["effect"]["p_value"]=case["policy"]["alpha"]
    assert run_cases([case])[0]["status"]=="threshold_not_met"
    case["effect"].update(coefficient="0",p_value="0.001",interval=None,interval_level=None)
    assert run_cases([case])[0]["reason"]=="zero_coefficient_with_significant_p_requires_review"


def test_missing_p_and_mismatched_measure_abstain():
    _,case=fixture();case["effect"]["p_value"]=None
    assert run_cases([case])[0]["reason"]=="missing_p_value"
    case["effect"].update(p_value="0.001",measure="odds_ratio")
    case["policy"]["measure"]="odds_ratio"
    assert run_cases([case])[0]["reason"]=="unsupported_or_mismatched_measure"


@pytest.mark.parametrize("value",["NaN","Infinity","-Infinity"])
def test_nonfinite_numeric_input_rejected(value):
    _,case=fixture();case["effect"]["coefficient"]=value
    with pytest.raises(ArticleMapError,match="Nonfinite"):run_cases([case])


def test_extra_expected_labels_and_duplicate_ids_rejected():
    _,case=fixture();case["expected"]={"status":"threshold_met"}
    with pytest.raises(ArticleMapError,match="Expected labels"):run_cases([case])
    del case["expected"]
    with pytest.raises(ArticleMapError,match="Duplicate"):run_cases([case,copy.deepcopy(case)])


def test_prepared_inputs_exclude_textual_conclusions_and_hidden_controls():
    dataset,_=fixture()
    assert "controls" not in dataset and not {"pmc8775386:U59","pmc8775386:U63","pmc8775386:U71","pmc7789349:U44"}&set(dataset["evidence"])
    proofs=[p for key,p in dataset["evidence"].items() if key.startswith("pmc7789349:U44:")]
    assert len(proofs)==1 and proofs[0]["text"]=="p>0.05"


class Inputs:
    def __init__(self):self.reads=0
    def read_inputs(self):self.reads+=1;return fixture()[0]


class Controls:
    def __init__(self,store):self.store,self.reads=store,0
    def read_controls(self):
        assert list(self.store.root.glob("*/seal.json"));self.reads+=1
        return json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))


def test_seal_precedes_control_access_immutable_repeat_and_wrong_code_block(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,"create_connection",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No network or model calls")))
    store=FilePredictionStore(tmp_path);inputs=Inputs();controls=Controls(store)
    with pytest.raises(ArticleMapError,match="Seal required"):
        EvaluateEmpiricalInference(controls,store).execute("0"*64,{"code":"1"})
    assert controls.reads==0
    sealed=SealEmpiricalInference(inputs,store).execute({"code":"1"});path=store.path(sealed["run_id"])/"predictions.json";raw=path.read_bytes()
    with pytest.raises(ArticleMapError,match="implementation changed"):
        EvaluateEmpiricalInference(controls,store).execute(sealed["run_id"],{"code":"2"})
    assert controls.reads==0
    result=EvaluateEmpiricalInference(controls,store).execute(sealed["run_id"],{"code":"1"})
    assert result["operator"]["matched"]==22 and result["independent_success"] is False
    assert result["operator"]["new_scientific_predictions"]==0
    assert SealEmpiricalInference(inputs,store).execute({"code":"1"})==sealed and path.read_bytes()==raw


def test_file_adapter_rejects_unbound_provenance(tmp_path):
    dataset,_=fixture();dataset["cases"][0]["effect"]["evidence_ids"]=["unknown"]
    p=tmp_path/"inputs.json";p.write_text(json.dumps(dataset),encoding="utf-8")
    with pytest.raises(ArticleMapError,match="Unknown empirical evidence"):FileEmpiricalInputs(p).read_inputs()


def test_real_source_reconstruction_is_not_labelled_a_novel_prediction():
    dataset,_=fixture();controls=json.loads((PREPARED/"hidden-controls.json").read_text(encoding="utf-8"))
    rows=run_cases(dataset["cases"]);result=score(rows,controls["controls"])
    assert result["matched"]==22 and result["new_scientific_predictions"]==0 and result["independent_success"] is False
