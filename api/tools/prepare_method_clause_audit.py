"""Разметка Codex по прочитанным фрагментам; без извлечения моделью или изменения карт."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.method_clause_projection import VERSION, GENERIC, project_method_clauses
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_template_barrier_audit import read_within

# Каждое решение относится к конкретному родителю, а не к словам любой другой статьи.
CLAUSES = {
    '5887909': {
        'K37': [],
        'K38': [('quantify transcripts', 'U11', 'we performed a microarray analysis'),
                ('analyze data', 'U68', 'A core analysis was performed, and networks, canonical pathways, and functional enrichment in diseases and gene function were determined.')],
        'K39': [('prepare intervention', 'U70', 'The peptides were allowed to oligomerize at room temperature (RT) for 2 h'),
                ('administer treatment', 'U70', 'All icv injections were performed within 2 h after oligomerization.')],
        'K40': [('administer treatment', 'U72', 'was injected into the left lateral ventricle.')],
        'K41': [('collect biosample', 'U74', 'CSF was collected by puncturing the cisterna magna membrane using the capillary needles.')],
        'K42': [('measure barrier permeability', 'U76', 'leakage from the blood into the CSF was determined by measuring the fluorescence in the diluted CSF samples')],
        'K43': [('prepare tissue', 'U78', 'Choroid plexus and hippocampus were isolated from brain tissue and snap‐frozen in liquid nitrogen for RNA analysis.')],
        'K44': [('assess histology', 'U80', 'Histological quantification of the plaques in the whole brain was done with the Fiji software')],
        'K45': [('assess ultrastructure', 'U83', 'Grids were viewed with a JEM 1400plus transmission electron microscope')],
        'K46': [('assess ultrastructure', 'U86', 'For serial block‐face imaging')],
        'K47': [('assess histology', 'U88', 'Plaque burden was calculated as the area occupied by the plaques')],
        'K48': [('measure biomarkers', 'U90', 'Both the soluble and insoluble Aβ fractions—extracted from the cortex—were determined with ELISA.')],
        'K49': [('measure cognition', 'U93', 'Cognitive behavior was assessed by the basic protocol for the NOR test')],
        'K50': [('normalize measurements', 'U95', 'Expression levels were normalized to the expression of the two or three most stable housekeeping genes')],
        'K51': [('analyze data', 'U97', 'Statistics were performed using GraphPad Prism 7.0')],
    },
    '8294390': {
        'K5': [('prepare intervention', 'U8', 'Atrosimab was produced by Catalent')],
        'K6': [('assess molecular structure', 'U10', 'Correct assembly under native conditions was visualized by size exclusion chromatography (SEC)')],
        'K7': [('measure physical property', 'U12', 'Temperature-dependent aggregation of Atrosimab was analyzed by dynamic light scattering')],
        'K8': [('measure receptor binding', 'U14', 'Binding of Atrosimab was detected')],
        'K9': [],
        'K10': [('measure receptor binding', 'U18', 'The affinity measurements were performed by SPR technology using a Biacore T200.'),
                 ('analyze data', 'U18', 'The data generated were fitted to a 1:1 binding model.')],
        'K11': [('measure biomarkers', 'U20', 'Flow cytometry acquisition was performed on a FACSCanto II')],
        'K13': [('administer treatment', 'U24', 'Atrosimab and Atrosab were injected at doses of 1.0 mg/kg or 30.0 mg/kg body weight'),
                 ('measure drug levels', 'U24', 'The concentration of Atrosimab in serum samples was determined by an ELISA specific for Atrosimab')],
        'K14': [('measure clinical course', 'U26', 'Body weight was recorded at the indicated time points.'),
                 ('measure biomarkers', 'U26', 'serum samples were analyzed for IL-6')],
        'K15': [('administer treatment', 'U28', 'Mice first received an i.v. injection (100-150 µl) of Atrosimab')],
        'K17': [('administer treatment', 'U78', 'Treatment (s.c.) with saline, the anti-TNF therapeutics Etanercept or Infliximab'),
                 ('measure clinical course', 'U78', 'Arthritis score (A) and weight (B) were documented weekly.')],
        'K18': [('administer treatment', 'U80', 'different doses of Atrosimab by twice weekly s.c. injections.'),
                 ('measure clinical course', 'U80', 'Arthritis score (A) and weight (B) were documented weekly.')],
        'K19': [('induce disease', 'U32', 'Non-alcoholic steatohepatitis (NASH) was induced in male huTNFR1-k/i mice by feeding a high-fat diet'),
                 ('administer treatment', 'U32', 'administration (i.p.) of Atrosab or Atrosimab')],
        'K20': [('induce disease', 'U34', 'female mice (6,7,8 weeks old) were immunized s.c.'),
                 ('measure clinical course', 'U34', 'Mice were weighed and scored on a daily basis')],
        'K21': [('administer treatment', 'U86', 'Mice were injected i.p. on days 1, 4, 8 and 12 of manifest disease')],
        'K22': [('assess histology', 'U36', 'evaluated by light microscopy for histopathological hallmarks of arthritis.')],
        'K23': [('assess histology', 'U38', 'For immunohistological analysis of liver tissue')],
        'K24': [('assess histology', 'U40', 'Spinal cord histopathology was performed')],
    },
}
RETAIN = {
    ('5887909', 'K37'): 'Несколько модельных линий и разные способы их использования: общий предикат не заменяется одной операцией без раздельного связывания групп.',
    ('8294390', 'K9'): 'Антагонистический и агонистический режимы различаются наличием TNF; требуется раздельное связывание областей, а не общий контекст двух режимов.',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    disable_network()
    root = Path(args.input_run).resolve()
    artifact = FilePredictionStore(root.parent).read_seal(root.name)
    ix = json.loads((root / 'inputs-manifest.json').read_bytes())
    maps = []
    for entry in ix['sources']:
        data = read_within(root, entry['map_path'])
        require(sha256(data).hexdigest() == entry['map_file_sha256'], 'Method source bytes differ')
        maps.append(json.loads(data))
    sources = {m['article_id']: m for m in maps}
    entries, seen = [], set()
    for v in artifact['part_views']:
        if v['frame']['kind'] != 'action' or v['frame']['action_status'] != 'performed' or v['projection_proof']['origin']['origin'] != 'primary_method':
            continue
        if v['frame']['statements'][0]['predicate'] not in GENERIC:
            continue
        article, kid = v['native_key']
        pmc = next((p for p in CLAUSES if 'pmc' + p in article), None)
        require(pmc is not None and kid in CLAUSES[pmc], 'Unreviewed generic procedure')
        require((pmc, kid) not in seen, 'Generic parent has multiple clauses; review separately')
        seen.add((pmc, kid))
        m = sources[article]
        units = {u['id']: u for u in m['source']['units']}
        operations = []
        for predicate, uid, quote in CLAUSES[pmc][kid]:
            unit = units[uid]
            require(unit['text'].count(quote) == 1, 'Method quote must occur exactly once in its declared unit')
            start = unit['start'] + unit['text'].index(quote)
            operations.append({'predicate': predicate, 'source_asserts_performed_operation': True,
                'reason_ru': 'Операция явно описана в связанном исходном фрагменте; участники и ограничения полного родителя не удаляются.',
                'evidence': {'unit_id': uid, 'start': start, 'end': start + len(quote), 'text': quote,
                             'sha256': sha256(quote.encode('utf8')).hexdigest()}})
        entries.append({'part_key': v['key'], 'run_id': v['run_id'], 'source_sha256': m['source']['sha256'],
            'graph_sha256': fingerprint(m['graph']), 'knowledge_sha256': v['projection_proof']['parent_knowledge_sha256'],
            'view_frame_sha256': fingerprint(v['frame']),
            'decision': 'source_asserted_clauses' if operations else 'retain_native', 'operations': operations,
            'reason_ru': RETAIN.get((pmc, kid), 'Явно выполненные операции выделены из общего описания; это разметка Codex, требующая экспертной проверки.')})
    require(seen == {(pmc, kid) for pmc, entries in CLAUSES.items() for kid in entries}, 'Method review coverage differs')
    audit = {'version': VERSION, 'author': 'Codex', 'model_calls': 0, 'expert_validated': False,
        'input_run_id': artifact['run_id'], 'input_prediction_sha256': fingerprint(artifact),
        'author_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'entries': entries}
    views = {tuple(v['key']): {**v, 'key': tuple(v['key']), 'native_key': tuple(v['native_key'])} for v in artifact['part_views']}
    by_parent = {}
    for key, v in views.items(): by_parent.setdefault(v['native_key'], []).append(key)
    _, _, _, coverage = project_method_clauses(views, by_parent, set(), maps, audit)
    path = Path(args.output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_immutable(path, FilePredictionStore.encode(audit))
    print(json.dumps({'primary_methods': coverage['primary_methods'], 'generic': coverage['generic_primary_methods'],
        'added_views': coverage['added_views'], 'counts': coverage['counts'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
