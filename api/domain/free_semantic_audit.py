"""Источниковый аудит отличает научный контекст от значений измерений."""
from collections import Counter
import json

from domain.article_maps import fingerprint
from domain.development_prediction import project_sources

VERSION = "free-semantic-audit-1"


def audit(maps):
    normalized, records, _, _ = project_sources(maps)
    eligible = [r for r in records if r["eligible"]]
    inventory, unknown, categories, examples = Counter(), Counter(), Counter(), {}
    for record in records:
        for attr in record["statement"]["attributes"]:
            inventory[(attr["name"],str(attr["unit"]))] += 1
        if record["statement"]["unknown_context"]:
            unknown[record["knowledge"]["article_id"]] += 1
    for i,a in enumerate(eligible):
        for b in eligible[i+1:]:
            x,y=a["occurrence"].atom,b["occurrence"].atom
            if (x.predicate,x.kind,x.negated) != (y.predicate,y.kind,y.negated):continue
            if [r for r,_ in x.roles] != [r for r,_ in y.roles]:continue
            changes=[r for (r,left),(_,right) in zip(x.roles,y.roles) if left!=right]
            if len(changes)!=1:continue
            left,right=json.loads(x.scope),json.loads(y.scope)
            different=[k for k in left if left[k]!=right[k]]
            category = "identical_bundle" if not different else (
                "attributes_only" if different==["attributes"] else
                "context_differs" if left["scope"]!=right["scope"] else "logic_or_status_differs")
            categories[category]+=1
            sample={"predicate":x.predicate,"changed_role":changes[0],
                    "left":{"article_id":a["occurrence"].source_id,"statement_id":a["occurrence"].node_id,
                            "knowledge_id":a["knowledge"]["id"],"text":a["knowledge"]["text"],"scope":left,
                            "provenance":a["occurrence"].provenance},
                    "right":{"article_id":b["occurrence"].source_id,"statement_id":b["occurrence"].node_id,
                            "knowledge_id":b["knowledge"]["id"],"text":b["knowledge"]["text"],"scope":right,
                            "provenance":b["occurrence"].provenance},"differences":different}
            bucket=examples.setdefault(category,[])
            if len(bucket)<12:bucket.append(sample)
    return {"version":VERSION,"source_knowledge_count":len(normalized),"statement_count":len(records),
            "eligible_count":len(eligible),"pair_categories":dict(categories),"examples":examples,
            "attribute_inventory":[{"name":name,"unit":None if unit=="None" else unit,"count":count}
                                   for (name,unit),count in sorted(inventory.items())],
            "unknown_context_by_source":dict(unknown),"model_calls":0,
            "note":"Attribute-only differences are not automatically permission to transfer; numbers may encode scientific restrictions."}
