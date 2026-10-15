"""Подготавливает полные исключения групп из числовой таблицы сохранённого обзора."""
import argparse
import copy
import html
import json
import re
from pathlib import Path

from domain.article_maps import digest, fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

FAMILIES = {
    "Larrieu 2002": "reported-France-Larrieu",
    "Busse 2003": "possible-overlap-Germany-1997",
    "Luck 2010": "possible-overlap-Germany-1997",
    "Roberts 2012": "reported-Mayo-Roberts",
    "Caracciolo 2008": "reported-Sweden-Caracciolo",
    "Manly 2008": "reported-Manly",
    "Katz 2012": "reported-Einstein-Katz",
}
AGES = [[65,69],[70,74],[75,79],[80,84],[85,None]]


def main():
    p=argparse.ArgumentParser();p.add_argument("--corpus",required=True);p.add_argument("--output",required=True)
    args=p.parse_args();disable_network()
    config=json.loads(Path(args.corpus).read_text(encoding="utf-8"));port=FileForecastMaps(config["sources"]);maps={}
    for entry in config["sources"]:
        ref=entry["reference"];maps[entry["pmcid"]]=port.get(ref["article_id"],ref["pipeline_id"],port.owner,ref["run_id"])
    source=maps["pmc6416157"]["source"];unit=next(u for u in source["units"] if u["id"]=="U53")
    observations, contexts, evidence, metadata_proofs, series, families, labels = [], {}, {}, {}, {}, set(), {}

    def proof(key,start,end):
        text=source["text"][start:end]
        evidence[key]={"article_id":maps["pmc6416157"]["article_id"],"pmcid":"pmc6416157","source_sha256":source["sha256"],
            "unit_id":"U53","offset_encoding":"unicode_codepoints","start":start,"end":end,"text":text,"text_sha256":digest(text)}
        return key

    header=re.search(r"Estimated incidence rate by age, per 1000 person-years \(95% CI\)",unit["text"])
    require(header is not None,"Incidence units missing from table header")
    header_id=proof("T2:incidence-unit",unit["start"]+header.start(),unit["start"]+header.end())
    endpoint=None
    for row_index,row in enumerate(re.finditer(r"<tr>.*?</tr>",unit["text"],re.S)):
        cells=list(re.finditer(r"<td[^>]*>(.*?)</td>",row.group(),re.S))
        if not cells:continue
        values=[" ".join(html.unescape(re.sub(r"<[^>]*>","",c.group(1))).split()) for c in cells]
        if values[0] in {"MCI","aMCI","naMCI"}:endpoint=values[0];continue
        require(endpoint is not None and len(values)==21,"Unexpected cohort table row")
        name=re.match(r"(Larrieu|Busse|Luck|Roberts|Caracciolo|Manly|Katz)\s+(\d{4})",values[0])
        require(name is not None,"Unregistered cohort row")
        study=" ".join(name.groups());family=FAMILIES[study];families.add(family)
        def cell_proof(index):
            c=cells[index];return proof(f"T2:r{row_index}c{index}",unit["start"]+row.start()+c.start(1),unit["start"]+row.start()+c.end(1))
        def known(value):return None if value in {"","NR"} else value
        context={"study_id":study,"family_id":family,"endpoint":endpoint,"measure":"incidence_rate","unit":"per1000personyears","design":"longitudinal",
            "criteria":known(values[8]),"threshold_sd":known(values[9]),"dementia_exclusion":known(values[10]),"norms":known(values[11]),
            "followup_years":values[20].replace("#",""),"followup_kind":"mean" if "#" in values[20] else "maximum",
            "country":known(values[1]),"calendar_period":known(values[2]),
            "attrition_adjustment":"explicitly attrition-adjusted" if study=="Caracciolo 2008" else None,
            "sample_n":known(values[13]),"female_percent":known(values[12]),"education":known(values[16]),"place":known(values[17]),"response_rate":known(values[15])}
        context_key=study+":"+endpoint;contexts[context_key]=context
        meta=[header_id]+[cell_proof(i) for i in (0,1,2,8,9,10,11,12,13,14,15,16,17,18,19,20)]
        metadata_proofs[context_key]=meta;items=[]
        for i,age in enumerate(AGES,3):
            if not values[i]:continue
            match=re.fullmatch(r"([\d.]+) \(([\d.]+), ([\d.]+)\)",values[i])
            require(match is not None,"Unsupported rate cell format")
            cid=f"{study.replace(' ','-')}:{endpoint}:{age[0]}"
            obs={"id":cid,"context":copy.deepcopy(context),"age":age,"value":match.group(1),"interval":list(match.groups()[1:]),"evidence_ids":[cell_proof(i),header_id]}
            observations.append(obs);items.append(obs)
        series[context_key]=items

    require(len(observations)==45 and len(series)==13 and len(families)==6,"Table coverage differs from registered pilot")
    controls={};fold_entries=[];output=Path(args.output)
    for index,family in enumerate(sorted(families),1):
        training=[o for o in observations if o["context"]["family_id"]!=family]
        queries=[];fold_labels={};context_evidence=[]
        for key,items in series.items():
            if contexts[key]["family_id"]!=family:continue
            for left,right in zip(items,items[1:]):
                qid=f"Q:{key.replace(' ','-')}:{left['age'][0]}-{right['age'][0]}"
                q={"id":qid,"context":copy.deepcopy(contexts[key]),"ages":[left["age"],right["age"]],"evidence_ids":metadata_proofs[key]}
                queries.append(q);context_evidence+=q["evidence_ids"]
                fold_labels[qid]={"en":key+f" · {left['age'][0]} → {right['age'][0]} years",
                    "ru":key+f" · возраст {left['age'][0]} → {right['age'][0]} лет"}
                controls[qid]={"values":[left["value"],right["value"]],"intervals":[left["interval"],right["interval"]],
                    "evidence_ids":list(dict.fromkeys(left["evidence_ids"]+right["evidence_ids"])),"family_id":family,
                    "context":copy.deepcopy(contexts[key]),"ages":q["ages"],"label":fold_labels[qid]}
        used=set(context_evidence)|{k for o in training for k in o["evidence_ids"]}
        # Числовые ячейки удержанной группы не попадают даже в журнал входных фрагментов.
        hidden_numeric={key for o in observations if o["context"]["family_id"]==family for key in o["evidence_ids"] if key!=header_id}
        require(not used & hidden_numeric,"Held-out numeric cell leaked into input evidence")
        fold={"fold_id":f"F{index}","withheld_family":family,"training":training,"queries":queries,
            "evidence":{k:evidence[k] for k in sorted(used)},"labels":fold_labels}
        filename=f"fold-{index}.json";write_immutable(output/filename,FilePredictionStore.encode(fold))
        fold_entries.append({"path":filename,"sha256":fingerprint(fold),"withheld_family":family})
    bindings=[{k:e[k] for k in ("reference","pmcid","file_sha256","graph_sha256","source_sha256")} for e in config["sources"]]
    manifest={"contract_version":1,"folds":fold_entries,"source_bindings":bindings,
        "metadata":{"author":"Codex","model_calls":0,"no_target_access":True,"review_pmcid":"pmc6416157",
            "known_sources_retrospective":True,"primary_fulltexts_verified":False,"family_independence_expert_verified":False,
            "selection":"All reported Table 2 age-specific incidence estimates, MCI/aMCI/naMCI; all adjacent pairs; leave entire provenance group out",
            "possible_overlap_group":"Busse 2003 and Luck 2010 grouped conservatively; identity not asserted"}}
    hidden_ids={key for c in controls.values() for key in c["evidence_ids"]}
    hidden={"manifest_sha256":fingerprint(manifest),"controls":controls,"evidence":{k:evidence[k] for k in sorted(hidden_ids)},"author":"Codex","expert_validated":False}
    for name,value in (("inputs-manifest.json",manifest),("hidden-controls.json",hidden),
        ("preparation-receipt.json",{"source_reads":port.reads,"observations":45,"cohort_publications":7,"provenance_groups":6,"series":13,"queries":32,"model_calls":0,"no_target_access":True})):
        write_immutable(output/name,FilePredictionStore.encode(value))
    print(json.dumps({"observations":len(observations),"folds":len(fold_entries),"queries":len(controls),"manifest_sha256":fingerprint(manifest)}))


if __name__=="__main__":main()
