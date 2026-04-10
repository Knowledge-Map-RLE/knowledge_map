import json

data = json.load(open('docs/pattern_analysis_report.json', encoding='utf-8'))
s = data['summary']

print('=== SUMMARY ===')
print(f'Всего паттернов: {s["total_patterns_found"]}')
print(f'Категорий: {len(s["pattern_categories"])}')
print()
g = s['graph_summary']
print(f'Actions: {g["total_actions"]:,}')
print(f'LexicalUnit: {g["total_lexical_units"]:,}')
print(f'LEADS_TO: {g["total_leads_to"]:,}')
print(f'DEPENDS_ON: {g["total_depends_on"]:,}')
print()

print('=== TOP-10 УСТОЙЧИВЫХ ===')
for i, p in enumerate(s['most_stable_patterns'][:10], 1):
    print(f'{i}. score={p["stability_score"]:.4f} | docs={p.get("docs",p.get("doc_count"))} | total={p["total"]} | {p["pattern"]}')
print()

print('=== ACTION CLASS DISTRIBUTION ===')
ac = data['patterns']['action_level']['action_class_distribution']
for x in ac[:10]:
    print(f'  class={x["class"]:12s} verb={x["verb"]:12s} cnt={x["cnt"]}')
print()

print('=== RELATION SUBTYPE DISTRIBUTION ===')
rs = data['patterns']['action_level']['relation_subtype_distribution']
for x in rs[:10]:
    print(f'  subtype={x["subtype"]:15s} status={x["status"]:12s} cnt={x["cnt"]:,}')
print()

print('=== TOP ACTION VERBS ===')
av = data['patterns']['action_level']['top_action_verbs']
for x in av[:10]:
    print(f'  verb={x["verb"]:12s} cnt={x["cnt"]:5d} docs={x["doc_count"]}')
print()

print('=== EDGE STATUS ===')
es = data['patterns']['action_level']['edge_status_distribution']
for x in es:
    print(f'  status={x["status"]:12s} cnt={x["cnt"]:,}')
print()

print('=== CROSS-DOC VERB-OBJ ===')
vo = data['patterns']['cross_document']['cross_doc_verb_obj']
for x in vo[:10]:
    print(f'  {x["verb"]:12s} -> {x["obj"]:15s} docs={x["docs"]} total={x["total"]}')
print()

print('=== CONVERGING 3->1 ===')
c3 = data['patterns']['leads_to_chains']['converging_3to1']
for x in c3[:10]:
    target = str(x["target"])[:80]
    print(f'  sources={x["sources_count"]:6d} | target={target}')
print()

print('=== LINGUISTIC PATTERN TYPES ===')
lp = data['patterns']['linguistic_pattern_entity']['pattern_type_distribution']
for x in lp[:10]:
    print(f'  type={x["type"]:20s} annotation={x["annotation"]:25s} cnt={x["cnt"]:,}')
