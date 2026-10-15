"""Аналитическая проекция сохраняет факты и отделяет значения от контекста."""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from dataclasses import asdict, replace

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize
from domain.development_prediction import project_sources, fit_predict, evaluate_sealed
from domain.free_prediction import semantic_key, already_represented, numeric, replaceable

VERSION = "scoped-free-forecast-2"
ADAPTER_VERSION = "source-evidence-projection-2"
LIMITS = {"candidate_limit":20,"max_premises":3,"min_template_families":2,"max_analogy_combinations":100000}
DICTIONARY = {
    "dimensionless_names":["p","p value","reported p","bonferroni p","studywise p","cohens d"],
    "provenance_names":["table","figure"],
    "variable_measurements":["value","mean","sd","p","p value","reported p","bonferroni p","studywise p","cohens d"],
    "protected_roles":["age band","age group","age","study","sample","cohort","phase","period","stratum","country"],
    "nontransferable_predicates":["author interpretation"],
}
DICTIONARY_SHA256 = fingerprint(DICTIONARY)
POLICY = {"question":None,"topic":"Aging and cognitive impairment in five explicitly selected sources",
    "operators":["source_supported_template","context_checked_single_role_analogy"],
    "analogy":"P(a,x), P(b,x), Q(a,y) suggest testing Q(b,y); not deduction",
    "adapter":"Explicit provenance markers remain in an evidence ledger; named dimensionless statistics keep their values",
    "context":"Witnesses require identical scientific scope. The head preserves its own polarity, modality, quantifier and qualifiers",
    "measurements":"Witness measurement values may differ only for named response statistics with the same units. Head numbers are never guessed",
    "guards":"At least two roles; no age/cohort/period replacement; no unknown context; no participant collapse; exclude known facts, contradictions, diagnostic definitions and source-bound author attributions",
    "budget":"20 pooled new candidates sealed before evaluation; no target-guided refill",
    "success":"A novel context-compatible equivalent statement in an independent later source; known target is debugging only"}


def project_evidence(maps):
    """Меняет только отдельную аналитическую копию; исходные графы неизменны."""
    projected, ledger = copy.deepcopy(maps), []
    for m in projected:
        for k in m["graph"]["knowledge"]:
            for s in k["semantic_frame"]["statements"]:
                kept=[]
                for attr in s["qualifiers"]["attributes"]:
                    name=normalize(attr["name"])
                    marker = (re.fullmatch(r"(?:"+name+r"\s*)?(\d+(?:[A-Za-z])?)",str(attr["value"]),re.I)
                        if name in DICTIONARY["provenance_names"] and attr["unit"] is None else None)
                    visible = bool(marker and re.search(r"\b"+name+r"\s*"+re.escape(marker.group(1))+r"\b",k["display_text"],re.I))
                    if visible:
                        ledger.append({"article_id":m["article_id"],"knowledge_id":k["knowledge_id"],"statement_id":s["statement_id"],
                            "kind":"provenance_marker","original":copy.deepcopy(attr),"semantic":None,"provenance":s["provenance"],
                            "reason":"The readable source-grounded knowledge explicitly locates this result in the numbered table/figure"})
                        continue
                    if name in DICTIONARY["dimensionless_names"] and attr["unit"] is None and attr["value"] is not None:
                        old=copy.deepcopy(attr);attr["unit"]="dimensionless"
                        ledger.append({"article_id":m["article_id"],"knowledge_id":k["knowledge_id"],"statement_id":s["statement_id"],
                            "kind":"dimensionless_statistic","original":old,"semantic":copy.deepcopy(attr),"provenance":s["provenance"],
                            "reason":"Unitless named statistic; value and statistical meaning are unchanged"})
                    kept.append(attr)
                s["qualifiers"]["attributes"]=kept
    return projected,ledger


def scalar_number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) or isinstance(value,str) and bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?",value))


def measurement_profile(atom):
    profile=[]
    for a in json.loads(atom.scope)["attributes"]:
        b=dict(a)
        if a["name"] in DICTIONARY["variable_measurements"] and a["unit"] is not None and scalar_number(a["value"]):
            b["value"]={"measured_response":True}
        profile.append(b)
    return profile


def scientific_context(atom, *, witness=False):
    s=json.loads(atom.scope)["scope"]
    # Модальность P и Q может различаться; Q переносит собственную модальность без усиления.
    return s if witness else {k:s[k] for k in ("time","study_group","conditions")}


def permitted_role(role,term):
    return role not in DICTIONARY["protected_roles"] and replaceable(role,term)


def contextual_analogies(records,families):
    eligible=[r for r in records if r["eligible"]]
    known={semantic_key(r["occurrence"].atom) for r in records}
    counters=Counter();candidates={};samples=[]
    def reject(reason,a,b,q=None):
        counters[reason]+=1
        if len(samples)<20 and q is not None:
            samples.append({"reason":reason,"premises":[{"source_id":r["occurrence"].source_id,"statement_id":r["occurrence"].node_id,
                "knowledge_id":r["knowledge"]["id"],"text":r["knowledge"]["text"],"provenance":r["occurrence"].provenance} for r in (a,b,q)]})
    for i,a in enumerate(eligible):
        x=a["occurrence"].atom
        for b in eligible[i+1:]:
            y=b["occurrence"].atom
            if (x.predicate,x.kind,x.negated)!=(y.predicate,y.kind,y.negated):continue
            if [r for r,_ in x.roles]!=[r for r,_ in y.roles]:continue
            changes=[(r,l,v) for (r,l),(_,v) in zip(x.roles,y.roles) if l!=v]
            if len(changes)!=1:continue
            counters["structural_pairs"]+=1
            role,old,new=changes[0]
            if len(x.roles)<2:reject("unary_generic_predicate",a,b);continue
            if not all(permitted_role(role,t) for t in (old,new)):reject("protected_participant_or_context_role",a,b);continue
            if scientific_context(x,witness=True)!=scientific_context(y,witness=True):reject("scientific_scope_differs",a,b);continue
            if measurement_profile(x)!=measurement_profile(y):reject("measurement_signature_or_constraint_differs",a,b);continue
            counters["compatible_witness_pairs"]+=1
            for first,second in ((a,b),(b,a)):
                xa,ya=first["occurrence"].atom,second["occurrence"].atom
                old,new=next((l,r) for (_,l),(_,r) in zip(xa.roles,ya.roles) if l!=r)
                for q in eligible:
                    z=q["occurrence"].atom
                    if q in (first,second) or z.predicate==xa.predicate:continue
                    roles=[r for r,term in z.roles if term==old]
                    if len(roles)!=1:continue
                    counters["head_combinations"]+=1
                    require(counters["head_combinations"]<=LIMITS["max_analogy_combinations"],"Scoped analogy budget exceeded")
                    if q["knowledge"]["knowledge_kind"]=="definition":reject("diagnostic_definition_not_a_new_forecast",first,second,q);continue
                    if z.predicate in DICTIONARY["nontransferable_predicates"]:reject("source_bound_attribution_not_transferable",first,second,q);continue
                    if scientific_context(z)!=scientific_context(xa):reject("head_context_differs",first,second,q);continue
                    if not permitted_role(roles[0],old):reject("head_role_protected",first,second,q);continue
                    if z.kind!="state" or q["knowledge"]["action_status"] is not None:reject("head_action_not_transferable",first,second,q);continue
                    if numeric(json.loads(z.scope)["attributes"]):reject("head_numeric_prediction_forbidden",first,second,q);continue
                    if normalize(z.predicate) in {"is a","subtype of","characterized by","diagnostic criteria"}:reject("definition_not_transferable",first,second,q);continue
                    atom=replace(z,roles=tuple(sorted((r,new if term==old else term) for r,term in z.roles)))
                    if len({v for _,v in atom.roles})<len({v for _,v in z.roles}):reject("participant_collapse",first,second,q);continue
                    if semantic_key(atom) in known or already_represented(atom,records):reject("already_known",first,second,q);continue
                    if semantic_key(replace(atom,negated=not atom.negated)) in known:reject("explicit_source_contradiction",first,second,q);continue
                    premises=[{"source_id":r["occurrence"].source_id,"node_id":r["occurrence"].node_id,
                        "display_text":r["knowledge"]["text"],"provenance":r["occurrence"].provenance} for r in (first,second,q)]
                    witness={"premises":premises,"replaced_role":roles[0],"from":old,"to":new}
                    item=candidates.setdefault(semantic_key(atom),{"id":atom.key,"atom":asdict(atom),"status":"exploratory_analogy",
                        "operator":"context_checked_single_role_analogy","rule_id":"scoped-analogy-1","support":0,"support_sources":[],
                        "support_families":[],"source_families":[],"premises":premises,"witnesses":[]})
                    item["source_families"]=sorted(set(item["source_families"])|{families[p["source_id"]] for p in premises})
                    item["witnesses"].append(witness)
    return list(candidates.values()),{"counts":dict(counters),"examples":samples}


def forecast(maps,families):
    require(set(families)=={m["article_id"] for m in maps},"Explicit source provenance families required")
    projected,ledger=project_evidence(maps)
    normalized,records,_,_=project_sources(projected)
    kinds={(m["article_id"],k["knowledge_id"]):k["knowledge_kind"] for m in projected for k in m["graph"]["knowledge"]}
    for r in records:r["knowledge"]["knowledge_kind"]=kinds[(r["knowledge"]["article_id"],r["knowledge"]["id"])]
    legacy=fit_predict(projected);pool={};unsupported=0
    for mode in ("semantic","graph"):
        for c in legacy["predictions"][mode]:
            rule=next(rule for rule in legacy["rules"][mode] if rule["id"]==c["rule_id"])
            head_records=[r for r in records if any(r["occurrence"].source_id==e["source_id"] and r["occurrence"].node_id==e["head"] for e in rule["examples"])]
            if c["atom"]["predicate"] in DICTIONARY["nontransferable_predicates"] or any(r["knowledge"]["knowledge_kind"]=="definition" for r in head_records):
                unsupported+=1;continue
            support=sorted({families[s] for s in c["support_sources"]})
            if len(support)<LIMITS["min_template_families"]:unsupported+=1;continue
            pool[c["id"]]={**c,"operator":"source_supported_template","support_families":support,"source_families":support}
    analogies,diagnostics=contextual_analogies(records,families)
    for c in analogies:pool.setdefault(c["id"],c)
    ranked=sorted(pool.values(),key=lambda c:(-len(c["support_families"]),-len(c["source_families"]),len(c["premises"]),c["id"]))
    known=legacy["predictions"]["known_union"]
    return {"predictor_version":VERSION,"adapter_version":ADAPTER_VERSION,"dictionary_sha256":DICTIONARY_SHA256,"policy":POLICY,"limits":LIMITS,
        "predictions":{"free":ranked[:20],"known_union":sorted(known,key=lambda c:c["id"])[:20],
                       "frequency":sorted(known,key=lambda c:(-len({families[p["article_id"]] for p in c["source_occurrences"]}),c["id"]))[:20]},
        "source_knowledge_count":len(normalized),"source_statement_count":len(records),"eligible_statement_count":sum(r["eligible"] for r in records),
        "known_count":len(known),"evidence_ledger":ledger,"diagnostics":{"legacy":legacy["diagnostics"],"analogy":diagnostics,
            "candidate_pool":len(pool),"family_rejected_templates":unsupported},"model_calls":0,"expert_validated":False}


def evaluate(sealed,target,controls):
    projected,ledger=project_evidence([target])
    return {**evaluate_sealed(sealed,projected[0],controls),"target_evidence_ledger":ledger}
