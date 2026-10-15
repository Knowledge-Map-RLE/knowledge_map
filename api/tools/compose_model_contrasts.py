"""Офлайн-CLI композиции параметров; модели и сеть не вызываются."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.model_contrast_composition import SealModelContrastComposition
from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_semantic_part_forecast import CODE as PART_CODE

CODE = (*PART_CODE, 'domain/model_contrast_composition.py', 'application/model_contrast_composition.py',
        'tools/compose_model_contrasts.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('sources', 'context-audit', 'model-audit', 'origin-audit', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    audit_bytes = {name: Path(getattr(args, name.replace('-', '_'))).read_bytes()
                   for name in ('context-audit', 'model-audit', 'origin-audit')}
    audits = {name: json.loads(value) for name, value in audit_bytes.items()}
    root = Path(__file__).resolve().parents[1]
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    metadata = {**manifest['metadata'], 'model_calls': 0, 'source_manifest_sha256': sha256(raw).hexdigest(),
        'source_dates': {s['reference']['article_id']: s['published_on'] for s in manifest['sources']},
        'input_audit_file_sha256': {name: sha256(value).hexdigest() for name, value in audit_bytes.items()}}
    port = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    result = SealModelContrastComposition(port, store).execute([s['reference'] for s in manifest['sources']],
        {s['reference']['article_id']: s['family'] for s in manifest['sources']}, port.owner, metadata, code,
        audits['context-audit'], audits['model-audit'], audits['origin-audit'])
    folder = store.path(result['run_id']); inputs = []
    write_immutable(folder / 'source-manifest.json', raw)
    for name, value in audit_bytes.items(): write_immutable(folder / (name + '.json'), value)
    for s in manifest['sources']:
        content = Path(s['path']).read_bytes()
        require(sha256(content).hexdigest() == s['file_sha256'], 'Contrast input changed after composition')
        name = 'inputs/maps/' + fingerprint(s['reference']) + '.json'
        write_immutable(folder / name, content)
        entry = {'reference': s['reference'], 'map_path': name, 'map_file_sha256': s['file_sha256']}
        if 'coverage_artifact' in s:
            artifact = s['coverage_artifact']; content = Path(artifact['path']).read_bytes()
            require(sha256(content).hexdigest() == artifact['sha256'], 'Contrast coverage changed after composition')
            name = 'inputs/coverage/' + fingerprint(s['reference']) + '.json'
            write_immutable(folder / name, content)
            entry.update(coverage_path=name, coverage_sha256=artifact['sha256'])
        inputs.append(entry)
    write_immutable(folder / 'inputs-manifest.json', store.encode({'sources': inputs, 'model_calls': 0, 'target_read': False}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'reads': port.reads, 'model_calls': 0,
        'target_read': False, 'network_disabled': True}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'],
        'consequences': len(result['consequences']), 'counts': result['counts'],
        'pair_steps': result['pair_steps']}, ensure_ascii=True))


if __name__ == '__main__': main()
