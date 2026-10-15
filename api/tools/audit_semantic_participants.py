"""CLI сохраняет только диагностику участников; карты и выводы не изменяются."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.semantic_participant_audit import SealParticipantAudit
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/semantic_participant_audit.py', 'application/semantic_participant_audit.py',
        'infrastructure/free_prediction_snapshots.py', 'infrastructure/development_prediction_store.py',
        'domain/whole_map_input_audit.py', 'domain/article_maps.py', 'tools/run_free_prediction.py',
        'tools/audit_semantic_participants.py')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--sources', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    port = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    api = Path(__file__).resolve().parents[1]
    code = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    result = SealParticipantAudit(port, store).execute([e['reference'] for e in manifest['sources']], port.owner,
        {**manifest['metadata'], 'source_manifest_sha256': sha256(raw).hexdigest()}, code)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'source-manifest.json', raw)
    write_immutable(folder / 'reads.json', store.encode({'reads': port.reads, 'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    for name in CODE:
        write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    print(json.dumps({'run_id':result['run_id'], 'blocks':result['canonical_blocks'], 'statements':result['statement_count'],
                      'flags':result['counts'], 'automatic_expansions':0, 'model_calls':0}))


if __name__ == '__main__': main()
