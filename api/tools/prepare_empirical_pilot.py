"""Фиксирует подготовленную Codex типизацию числовых фактов пяти источников."""
import argparse
import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from domain.article_maps import digest, fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore
from tools.run_free_prediction import disable_network


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell).strip()); self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row); self.row = None


def table(text):
    parser = TableRows(); parser.feed(text)
    return {row[0]: row[1:] for row in parser.rows if row}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", required=True); p.add_argument("--output", required=True)
    args = p.parse_args(); disable_network()
    config = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    require([e["pmcid"] for e in config["sources"]] == ["pmc5436834", "pmc6416157", "pmc7789349", "pmc8775386", "pmc8918697"], "Pilot source list differs")
    port = FileForecastMaps(config["sources"])
    maps = {}
    for entry in config["sources"]:
        r = entry["reference"]
        maps[entry["pmcid"]] = port.get(r["article_id"], r["pipeline_id"], port.owner, r["run_id"])
    evidence, cases, controls, labels = {}, [], [], {}

    def proof(pmc, uid, excerpt=None):
        key = pmc + ":" + uid + (":"+digest(excerpt)[:12] if excerpt else "")
        if key not in evidence:
            source = maps[pmc]["source"]
            u = next(x for x in source["units"] if x["id"] == uid)
            require(source["text"][u["start"]:u["end"]] == u["text"], "Empirical source fragment differs")
            start, end, text = u["start"], u["end"], u["text"]
            if excerpt is not None:
                require(text.count(excerpt) == 1, "Empirical excerpt must be unambiguous")
                start += text.index(excerpt); end = start+len(excerpt); text = excerpt
            evidence[key] = {"article_id": maps[pmc]["article_id"], "pmcid": pmc, "unit_id": uid,
                "source_sha256": source["sha256"], "offset_encoding": source["offset_encoding"],
                "start": start, "end": end, "text": text, "text_sha256": digest(text)}
        return key

    def unit(pmc, uid):
        return evidence[proof(pmc, uid)]["text"]

    def context(pmc, outcome, group="all"):
        if pmc == "pmc8775386":
            return {"study_id": pmc+":CretanAgingCohort-phaseII", "analysis_id": "multiple-linear-regression:"+outcome,
                "population_id": pmc+":"+group, "design": "cross_sectional", "time": "Phase II cross-sectional measurement",
                "outcome": outcome, "outcome_scale": "reported biomarker regression scale; exact coefficient units unspecified",
                "adjustment": ["age", "sex", "BMI"] + (["MCI diagnosis"] if group == "all" else []),
                "sample_n": {"all":117, "CNI":54, "MCI":63}[group]}
        return {"study_id": pmc+":Chinese-MCI-prevalence-review", "analysis_id": "Table3-meta-regression",
            "population_id": pmc+":included-studies", "design": "meta_regression", "time": "1998-2020 study periods; ecological analysis",
            "outcome": outcome, "outcome_scale": "lnhr as labelled in Table 3; exact coding unspecified",
            "adjustment": ["Age", "Study period", "Diagnostic criteria"], "sample_n": None}

    def add_case(pmc, predictor, predictor_ru, outcome, group, beta, pvalue, ci, alpha, evidence_units,
                 expected, control_uid, source_relation="compatible_statistical_summary", coding="reported_scale_unknown"):
        cid = "E" + str(len(cases)+1).zfill(2)
        ctx = context(pmc, outcome, group)
        refs = [proof(pmc, u) for u in evidence_units]
        method_uid = "U40" if pmc == "pmc8775386" else "U44"
        effect = {"id":cid, "context":ctx, "predictor":predictor, "measure":"unstandardized_linear_coefficient",
            "coefficient":beta, "coefficient_unit":None, "p_value":pvalue, "interval":ci,
            "interval_level":"0.95" if ci is not None else None, "coding":coding, "evidence_ids":refs}
        policy = {"id":"T-"+cid, "context":copy.deepcopy(ctx), "measure":effect["measure"], "alpha":alpha, "comparison":"lt",
            "correction":"Bonferroni_reported_rounded" if pmc == "pmc8775386" else "nominal_reported",
            "evidence_ids":[proof(pmc, method_uid, "p>0.05" if pmc == "pmc7789349" else None)]}
        cases.append({"effect":effect, "policy":policy})
        labels[cid] = {"en":predictor+" → "+outcome+" · "+group, "ru":predictor_ru+" → "+outcome+" · "+group,
                       "kind":"source_numeric_reconstruction"}
        controls.append({"case_id":cid, "expected":expected, "kind":"source_numeric_reconstruction",
            "source_claim_relation":source_relation, "evidence":[proof(pmc, control_uid)],
            "note":"Codex-labelled diagnostic reconstruction; source claims and data may disagree; not a blind scientific forecast"})

    pmc = "pmc8775386"
    # Методы и таблицы служат предпосылками; текстовые заключения остаются в отдельных контролях.
    rows5, rows6 = table(unit(pmc,"U61")), table(unit(pmc,"U65"))
    mapping = [
        ("Night TST > 450 min","Ночной сон >450 минут","plasma TNF-alpha",rows5,"U61","0.017","threshold_not_met",None,"U59","nominal_only_after_adjustment","binary_label_ambiguous"),
        ("Consumption of vegetables","Потребление овощей","plasma TNF-alpha",rows5,"U61","0.017","threshold_met","negative","U59","compatible_statistical_summary","higher_intake"),
        ("Consumption of red meat","Потребление красного мяса","plasma TNF-alpha",rows5,"U61","0.017","abstain",None,"U61","reported_coefficient_interval_inconsistency","higher_intake"),
        ("Physical activity","Физическая активность (кодирование неоднозначно)","plasma IL-6",rows6,"U65","0.025","threshold_met","negative","U63","coding_needs_clarification","binary_label_ambiguous"),
        ("Consumption of vegetables","Потребление овощей","plasma IL-6",rows6,"U65","0.025","threshold_met","negative","U63","compatible_statistical_summary","higher_intake"),
    ]
    for predictor,ru,outcome,rows,uid,alpha,status,direction,control_uid,relation,coding in mapping:
        beta, ci_text, p_text = rows[predictor]
        ci = re.fullmatch(r"\((.+) to (.+)\)",ci_text)
        pv = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s+([12]))?",p_text)
        require(ci is not None and pv is not None,"Unexpected table cell format")
        expected = {"status":status,"direction":direction}
        if status == "abstain":expected["reason"]="coefficient_outside_its_reported_interval"
        add_case(pmc,predictor,ru,outcome,"all",beta,pv.group(1),list(ci.groups()),alpha,
                 ["U24","U27","U29" if coding == "higher_intake" else "U35" if predictor == "Physical activity" else "U32",uid],
                 expected,control_uid,relation,coding)
    for uid,predictor,ru,outcome,alpha,annotation,statuses,coding in [
        ("U62","Night TST >450 min","Ночной сон >450 минут","plasma TNF-alpha","0.017","1",["threshold_not_met","threshold_not_met"],"binary_label_ambiguous"),
        ("U62","Consumption of vegetables","Потребление овощей","plasma TNF-alpha","0.017","2",["threshold_met","threshold_met"],"higher_intake"),
        ("U66","Physical activity","Физическая активность (кодирование неоднозначно)","plasma IL-6","0.025","1",["threshold_not_met","threshold_not_met"],"binary_label_ambiguous"),
        ("U66","Consumption of vegetables","Потребление овощей","plasma IL-6","0.025","2",["threshold_met","threshold_met"],"higher_intake"),
    ]:
        match = re.search(annotation+r" CNI: B = ([−\-\d.]+), p = ([\d.]+); MCI: B = ([−\-\d.]+), p = ([\d.]+)",unit(pmc,uid))
        require(match is not None,"Missing subgroup numeric footnote")
        for i,group in enumerate(("CNI","MCI")):
            beta,pv = match.groups()[i*2:i*2+2]
            # Завершающая точка предложения не является частью числа.
            pv = pv.rstrip(".")
            status = statuses[i]
            relation = "disagrees_with_discussion" if predictor.startswith("Night") and group == "MCI" else "compatible_statistical_summary"
            add_case(pmc,predictor,ru,outcome,group,beta,pv,None,alpha,["U24",uid],
                {"status":status,"direction":"negative" if status=="threshold_met" else None},
                "U71" if relation=="disagrees_with_discussion" else "U59" if outcome=="plasma TNF-alpha" else "U63",relation,coding)

    pmc = "pmc7789349"
    rows = table(unit(pmc,"U46"))
    for name,ru,status,direction in [("Age","Возраст (на уровне исследований)","threshold_not_met",None),
                                  ("Study period","Период исследования","threshold_met","positive"),
                                  ("Diagnostic criteria","Диагностические критерии","threshold_not_met",None)]:
        beta,se,t,pv,lo,hi = rows[name]
        add_case(pmc,name,ru,"reported MCI prevalence meta-regression outcome","included studies",beta,pv,[lo,hi],"0.05",["U46"],
                 {"status":status,"direction":direction},"U44",coding="reported_scale_unknown")

    # Явно искусственные отрицательные контроли с реальными числовыми предпосылками.
    base = copy.deepcopy(cases[1])
    changes = [
        ("other_outcome",lambda c:c["policy"]["context"].update(outcome="plasma IL-6"),"incompatible_context"),
        ("other_group",lambda c:c["policy"]["context"].update(population_id="pmc8775386:MCI",sample_n=63),"incompatible_context"),
        ("other_design",lambda c:c["policy"]["context"].update(design="longitudinal"),"incompatible_context"),
        ("missing_p",lambda c:c["effect"].update(p_value=None),"missing_p_value"),
        ("ratio_not_coefficient",lambda c:c["effect"].update(measure="hazard_ratio"),"unsupported_or_mismatched_measure"),
        ("other_adjustment",lambda c:c["policy"]["context"].update(adjustment=["age","sex"]),"incompatible_context"),
    ]
    for i,(name,change,reason) in enumerate(changes,1):
        case = copy.deepcopy(base);cid="N"+str(i).zfill(2);case["effect"]["id"]=cid;case["policy"]["id"]="T-"+cid;change(case)
        cases.append(case);labels[cid]={"en":"Synthetic negative: "+name,"ru":"Искусственный отрицательный контроль: "+name,"kind":"source_derived_synthetic_negative"}
        controls.append({"case_id":cid,"expected":{"status":"abstain","direction":None,"reason":reason},
            "kind":"source_derived_synthetic_negative","source_claim_relation":"not_a_source_claim","evidence":base["effect"]["evidence_ids"],
            "note":"Context or measurement deliberately corrupted by Codex; do not interpret as a real study finding"})

    bindings=[{k:entry[k] for k in ("reference","pmcid","file_sha256","source_sha256","graph_sha256")} for entry in config["sources"]]
    metadata={"author":"Codex","expert_validated":False,"model_calls":0,"purpose":"Engineering reconstruction of hidden statistical summaries",
        "selection":"All non-intercept Table 5/6 coefficients and their available subgroup footnotes in PMC8775386; all three non-intercept Table 3 meta-regression rows in PMC7789349",
        "selected_source_articles":2,"source_corpus_articles":5,"manual_pilot_not_full_reformalization":True,
        "unknown_coefficient_units_preserved":True,"scientific_prediction_success":False}
    input_ids={key for c in cases for premise in (c["effect"],c["policy"]) for key in premise["evidence_ids"]}
    control_ids={key for c in controls for key in c["evidence"]}
    dataset={"contract_version":1,"metadata":metadata,"source_bindings":bindings,
        "evidence":{key:value for key,value in evidence.items() if key in input_ids},"labels":labels,"cases":cases}
    hidden={"input_sha256":fingerprint(dataset),"author":"Codex","expert_validated":False,"controls":controls,
        "evidence":{key:value for key,value in evidence.items() if key in control_ids}}
    coverage={"source_articles":5,"selected_articles":2,"real_cases":16,"synthetic_negative_cases":6,
        "excluded_intercepts":3,"excluded_articles":[{"pmcid":pmc,"reason":"Not yet typed in this bounded numeric-operator pilot"} for pmc in ("pmc5436834","pmc6416157","pmc8918697")],
        "no_target_access":True,"source_reads":port.reads,"model_calls":0,"inputs_sha256":fingerprint(dataset),"controls_sha256":fingerprint(hidden)}
    output=Path(args.output)
    for name,value in (("inputs.json",dataset),("hidden-controls.json",hidden),("preparation-receipt.json",coverage)):
        write_immutable(output/name,FilePredictionStore.encode(value))
    print(json.dumps({"cases":len(cases),"real_cases":16,"evidence_fragments":len(evidence),"input_sha256":fingerprint(dataset)},ensure_ascii=False))


if __name__ == "__main__":main()
