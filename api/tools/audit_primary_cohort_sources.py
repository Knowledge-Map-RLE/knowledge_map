"""Аудит семи первичных ссылок; будущий контроль читается только как метаданные."""
import argparse
import json
import logging
import re
from hashlib import sha256
from pathlib import Path

from application.primary_cohort_sources import AuditPrimarySources
from domain.article_maps import digest, fingerprint, require
from domain.primary_cohort_sources import CONTROL_QUERY, TRAINING_QUERY, VERSION
from infrastructure.primary_cohort_sources import EuropePmcPrimarySources,FilePrimarySourceStore,CachedPrimarySources,convert_primary_xml,CONVERSION_VERSION
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore

REFERENCES=((35,"larrieu2002"),(32,"busse2003"),(12,"luck2010"),(6,"roberts2012"),(33,"caracciolo2008"),(36,"manly2008"),(34,"katz2012"))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--corpus",required=True);parser.add_argument("--output",required=True)
    parser.add_argument("--reuse-audit")
    args=parser.parse_args();logging.basicConfig(level=logging.INFO);output=Path(args.output).resolve()
    corpus=json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    entry=next(e for e in corpus["sources"] if e["pmcid"]=="pmc6416157")
    port=FileForecastMaps([entry]);ref=entry["reference"]
    m=port.get(ref["article_id"],ref["pipeline_id"],port.owner,ref["run_id"]);source=m["source"]
    entries=[]
    for number,identifier in REFERENCES:
        match=re.search(r"(?m)^"+str(number)+r"\. [^\n]+",source["text"])
        require(match is not None,"Registered review reference missing")
        identifier_match=re.search(r"doi: (10\.[^\s]+)\.$",match.group())
        require(identifier_match is not None,"Exact DOI absent from review reference")
        entries.append({"id":identifier,"doi":identifier_match.group(1).lower(),"role":"training_candidate",
                        "review_reference":number,"reference_proof":{"article_id":m["article_id"],"source_sha256":source["sha256"],
                        "offset_encoding":"unicode_codepoints","start":match.start(),"end":match.end(),"text":match.group(),"text_sha256":digest(match.group())}})
    registry={"version":VERSION,"training_entries":entries,"source_binding":{k:entry[k] for k in ("reference","pmcid","file_sha256","source_sha256","graph_sha256")},
              "conversion_version":CONVERSION_VERSION,
              "acquisition_policy":"Request JATS only for records explicitly flagged Open Access; other routes not used automatically",
              "control_search":{"query":CONTROL_QUERY,"result_type":"lite","abstracts_allowed":False,"fulltext_allowed":False,
                                "status":"Metadata screen only; selection and prior-exposure audit pending"},"model_calls":0}
    write_immutable(output/"registry.json",FilePredictionStore.encode(registry))
    provider=CachedPrimarySources(args.reuse_audit) if args.reuse_audit else EuropePmcPrimarySources()
    if args.reuse_audit:require(provider.registry["source_binding"]==registry["source_binding"],"Verified cache belongs to another source revision")
    store=FilePrimarySourceStore(output/"sources")
    results=AuditPrimarySources(provider,store,convert_primary_xml).execute(entries)
    additional_path=output/"additional-training-metadata.json"
    if additional_path.exists():additional=json.loads(additional_path.read_text(encoding="utf-8"))
    else:
        candidates=provider.training_candidates()
        filtered=[r for r in candidates if r["doi"] not in {e["doi"] for e in entries} and r["is_open_access"] and r["pmcid"] and
                  not any(word in r["title"].lower() for word in ("review","meta-analysis","protocol"))]
        additional={"query":TRAINING_QUERY,"candidates":candidates,"selected":filtered[:3],
                    "selection":"First three by publication date then DOI; exclude review/meta-analysis/protocol in title; selection before fulltext access",
                    "qualification":"Training candidates pending primary design, cohort and endpoint audit; not approved training inputs"}
        write_immutable(additional_path,FilePredictionStore.encode(additional))
    more_entries=[{"id":"additional-"+r["pmcid"].lower(),"doi":r["doi"],"role":"training_candidate","selection_sha256":fingerprint(additional)} for r in additional["selected"]]
    additional_results=AuditPrimarySources(provider,store,convert_primary_xml).execute(more_entries)
    controls_path=output/"control-metadata.json"
    if controls_path.exists():controls=json.loads(controls_path.read_text(encoding="utf-8"))
    else:
        controls={"query":CONTROL_QUERY,"candidates":provider.control_candidates(),"abstracts_read":False,"fulltexts_read":False,
                  "readiness":False,"note":"Metadata candidates are not final independent holdouts"}
        write_immutable(controls_path,FilePredictionStore.encode(controls))
    files=("domain/primary_cohort_sources.py","application/ports/primary_cohort_sources.py","application/primary_cohort_sources.py",
           "infrastructure/primary_cohort_sources.py","infrastructure/public_article_text.py","tools/audit_primary_cohort_sources.py")
    api=Path(__file__).resolve().parents[1]
    audit={"version":VERSION,"registry_sha256":fingerprint(registry),"sources":results,"additional_sources":additional_results,
           "conversion_version":CONVERSION_VERSION,"reused_original_audit":fingerprint(provider.audit) if args.reuse_audit else None,
           "additional_metadata_sha256":fingerprint(additional),"control_metadata_sha256":fingerprint(controls),
           "control_candidates":len(controls["candidates"]),"model_calls":0,"target_fulltexts_read":False,
           "new_scientific_predictions":0,"expert_validated":False,"implementation":{n:sha256((api/n).read_bytes()).hexdigest() for n in files}}
    write_immutable(output/"audit.json",FilePredictionStore.encode(audit))
    for name in files:write_immutable(output/"implementation"/name,(api/name).read_bytes())
    receipt_path=output/"http-receipt.json"
    if not receipt_path.exists():write_immutable(receipt_path,FilePredictionStore.encode({"requests":provider.requests,"model_calls":0,"control_fulltexts_read":False}))
    print(json.dumps({"audit":str(output/"audit.json"),"fulltexts":sum(r["status"]=="training_fulltext_saved" for r in results+additional_results),
                      "unavailable_on_selected_route":[r["metadata"]["doi"] for r in results if r["status"]!="training_fulltext_saved"],
                      "control_metadata_candidates":len(controls["candidates"])},ensure_ascii=False))


if __name__=="__main__":main()
