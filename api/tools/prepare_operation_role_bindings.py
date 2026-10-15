"""Разметка Codex явно описанных участников без моделей и изменений исходных карт."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.operation_role_bindings import VERSION, project_role_bindings
from domain.comparison_normalization import normalize_map
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_template_barrier_audit import read_within
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    root = Path(args.input_run).resolve()
    source = FilePredictionStore(root.parent).read_seal(root.name)
    manifest = json.loads((root / 'inputs-manifest.json').read_bytes())
    maps = []
    for e in manifest['sources']:
        raw = read_within(root, e['map_path'])
        require(sha256(raw).hexdigest() == e['map_file_sha256'], 'Role source bytes differ')
        maps.append(json.loads(raw))
    catalog = {m['article_id']: m for m in maps}
    views = {tuple(v['key']): {**v, 'key': tuple(v['key']), 'native_key': tuple(v['native_key'])} for v in source['part_views']}

    def find(pmc, kid, predicate=None, method=False):
        found = [v for v in views.values() if ('pmc' + pmc) in v['native_key'][0] and v['native_key'][1] == kid
                 and (predicate is None or v['frame']['statements'][0]['predicate'] == predicate)
                 and (not method or 'method_clause_proof' in v['projection_proof'])]
        require(len(found) == 1, 'Role source part must be unique')
        return found[0]

    def quote(v, uid, text):
        m = catalog[v['native_key'][0]]
        unit = next(u for u in m['source']['units'] if u['id'] == uid)
        require(unit['text'].count(text) == 1, 'Role quote must occur exactly once')
        start = unit['start'] + unit['text'].index(text)
        return {'unit_id': uid, 'start': start, 'end': start + len(text), 'text': text,
                'sha256': sha256(text.encode('utf8')).hexdigest()}

    def add(v, label, additions, renames=(), basis=None):
        m = catalog[v['native_key'][0]]
        entries.append({'part_key': list(v['key']), 'variant': label, 'run_id': v['run_id'],
            'source_sha256': m['source']['sha256'], 'graph_sha256': fingerprint(m['graph']),
            'knowledge_sha256': v['projection_proof']['parent_knowledge_sha256'], 'frame_sha256': fingerprint(v['frame']),
            'add_roles': additions, 'rename_roles': list(renames), 'binding_group': basis,
            'reason_ru': 'Явно описанные участники связаны с операцией по собственному источнику; полные условия и числа сохранены. Требуется экспертная проверка.'})

    def literal(role, value, e):
        return {'role': role, 'value': value, 'source_asserts_role': True, 'evidence': e}

    def copy(role, src, src_role, e, subgroup=False):
        return {'role': role, 'source_asserts_role': True, 'source_asserts_subprotocol_group': subgroup,
            'copy_from': {'part_key': list(src['key']), 'role': src_role, 'frame_sha256': fingerprint(src['frame'])}, 'evidence': e}

    def group(article, body, head):
        return {'premises': [[article, k] for k in body], 'head': [article, head]}

    entries = []
    t9, t28 = find('5651799', 'K9'), find('5651799', 'K28')
    tbasis = group(t9['native_key'][0], ['K28', 'K9'], 'K30')
    measured = quote(t9, 'U22', 'Mice were weighed and clinically scored daily.')
    tgroup = quote(t9, 'U22', 'hTNFR1 Tg mice were prophylactically treated on day 3 post-immunization (PI)')
    rename = {'from': 'model', 'to': 'challenge', 'biological_induced_disease_model': True,
              'evidence': quote(t9, 'U79', 'EAE was induced as follows:')}
    add(t9, 'clinical_measurement_in_reported_treatment_group', [copy('population', t28, 'population', tgroup, True)], [rename], tbasis)
    control = quote(t28, 'U21', 'Mice were injected i.p. every two days with 200 µg TROS or PBS as a control.')
    add(t28, 'explicit_vehicle_comparator', [literal('comparator', 'pbs vehicle control', control)])
    for v in views.values():
        if v['native_key'] == (t9['native_key'][0], 'K30'):
            add(v, 'explicit_vehicle_comparator', [literal('comparator', 'pbs vehicle control', control)], basis=tbasis)

    a20 = find('8294390', 'K20', 'measure clinical course', True)
    original20 = find('8294390', 'K20', 'perform experimental procedure')
    clinical = quote(a20, 'U34', 'Mice were weighed and scored on a daily basis, with disease severity assessed using a scale ranging from 0 to 5')
    add(a20, 'explicit_clinical_score_target', [literal('outcome', 'eae clinical score', clinical)])
    add(a20, 'explicit_body_weight_target', [literal('outcome', 'body weight', clinical)])
    a21 = find('8294390', 'K21', 'administer treatment', True)
    abasis = group(a20['native_key'][0], ['K20', 'K21'], 'K47')
    challenge = quote(a21, 'U86', 'huTNFR1-k/i mice were immunized with MOG35-55 peptide to induce EAE.')
    add(a21, 'explicit_induced_disease_context', [copy('challenge', original20, 'challenge', challenge)], basis=abasis)
    for v in views.values():
        if v['native_key'] == (a20['native_key'][0], 'K47'):
            add(v, 'explicit_induced_disease_context', [copy('challenge', original20, 'challenge', challenge)], basis=abasis)

    audit = {'version': VERSION, 'author': 'Codex', 'model_calls': 0, 'expert_validated': False,
        'input_run_id': source['run_id'], 'input_prediction_sha256': fingerprint(source),
        'author_script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'entries': entries,
        'limitations_ru': ['Роли детально проверены для двух источниковых цепочек; все прочие роли сохраняются и типизируются без угадывания.',
            'Методы TROS задают шкалу 0–6, подпись рисунка 3 указывает 0–5. Полный исходник и старое поле 0–6 сохранены; причина различия не установлена.',
            'Пол, возраст, генотипы, препараты, дозы и отсчёты времени не отождествляются.']}
    groups = []
    for m in maps:
        for k in normalize_map(m):
            groups.extend((tuple((m['article_id'], p) for p in g), (m['article_id'], k['id'])) for g in k['premise_groups'])
    by_parent = {}
    for key, v in views.items(): by_parent.setdefault(v['native_key'], []).append(key)
    _, _, _, summary = project_role_bindings(views, by_parent, set(), maps, groups, audit)
    path = Path(args.output).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    write_immutable(path, FilePredictionStore.encode(audit))
    print(json.dumps({'profiles': len(summary['profiles']), 'added_role_views': summary['added_views'],
        'role_types': summary['native_role_types'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
