"""Аудит запечатанного полного корпуса; модели, сеть и будущие исходы не используются."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.template_barrier_audit import SealTemplateBarrierAudit
from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/template_barrier_audit.py', 'application/template_barrier_audit.py',
        'tools/run_template_barrier_audit.py', 'domain/article_maps.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py')


def read_within(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root), 'Snapshot path escapes input folder')
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    disable_network()
    root = Path(args.input_run).resolve()
    raw = (root / 'predictions.json').read_bytes()
    artifact = FilePredictionStore(root.parent).read_seal(root.name)
    inputs = json.loads((root / 'inputs-manifest.json').read_bytes())
    require(artifact['run_id'] == root.name and artifact['run_id'] == fingerprint(artifact['binding']), 'Input seal differs')
    require(inputs['model_calls'] == 0 and inputs['target_read'] is False, 'Input corpus accessed target or models')
    require([s['reference'] for s in inputs['sources']] == artifact['binding']['references'], 'Input references differ')
    manifest = json.loads((root / 'source-manifest.json').read_bytes())
    entries = []
    require(len(inputs['sources']) == len(manifest['sources']) == len(artifact['binding']['map_hashes']), 'Input map count differs')
    for source, declared in zip(inputs['sources'], manifest['sources']):
        require(source['reference'] == declared['reference'], 'Source manifest identity differs')
        entry = {**declared, 'path': str((root / source['map_path']).resolve())}
        read_within(root, source['map_path'])
        if 'coverage_path' in source:
            read_within(root, source['coverage_path'])
            entry['coverage_artifact'] = {'path': str((root / source['coverage_path']).resolve()), 'sha256': source['coverage_sha256']}
        entries.append(entry)
    port = FileForecastMaps(entries)
    maps = []
    for source, expected in zip(inputs['sources'], artifact['binding']['map_hashes']):
        data = read_within(root, source['map_path'])
        require(sha256(data).hexdigest() == source['map_file_sha256'], 'Input map file differs')
        ref = source['reference']
        m = port.get(ref['article_id'], ref['pipeline_id'], port.owner, ref['run_id'])
        require(fingerprint(m) == expected and m['article_id'] == source['reference']['article_id']
                and m['run_id'] == source['reference']['run_id'], 'Input map identity differs')
        require(m['source']['sha256'] != 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8', 'Approved target is excluded')
        maps.append(m)
    for name, expected in artifact['binding']['implementation'].items():
        require(sha256(read_within(root, 'implementation/' + name)).hexdigest() == expected, 'Input implementation differs')
    by_article = {m['article_id']: m for m in maps}
    for v in artifact['part_views']:
        m = by_article[v['native_key'][0]]
        k = next(k for k in m['graph']['knowledge'] if k['knowledge_id'] == v['native_key'][1])
        require(k == v['projection_proof']['complete_native_knowledge'], 'Native diagnostic source differs')
    code_root = Path(__file__).resolve().parents[1]
    code = {name: sha256((code_root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = SealTemplateBarrierAudit(store).execute(artifact, code)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'input-predictions.json', raw)
    for name in CODE:
        write_immutable(folder / 'implementation' / name, (code_root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'maps': len(maps), 'blocks': result['canonical_blocks'],
        'modes': {mode: {'primary_templates': data['primary_result_templates'],
                        'collisions': {p: v['multi_family_collision_groups'] for p, v in data['policies'].items()}}
                  for mode, data in result['modes'].items()}, 'new_predictions': 0}))


if __name__ == '__main__':
    main()
