"""CLI лицензированного селективного переноса без сети и AI-клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.selective_perturbation import SealSelectivePerturbation
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/selective_perturbation.py', 'application/selective_perturbation.py',
        'domain/article_maps.py', 'domain/semantic_operator_graph.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
        'tools/run_free_prediction.py', 'tools/run_selective_perturbation.py')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--semantic-run', required=True)
    parser.add_argument('--licenses', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    semantic_folder = Path(args.semantic_run); source = FilePredictionStore(semantic_folder.parent).read_seal(semantic_folder.name)
    audit = json.loads(Path(args.licenses).read_bytes()); api = Path(__file__).resolve().parents[1]
    code = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output); result = SealSelectivePerturbation(store).execute(source, audit, code)
    folder = store.path(result['run_id']); write_immutable(folder / 'licenses.json', store.encode(audit))
    for name in CODE: write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'canonical_blocks': result['canonical_blocks'],
                     'statements': result['statement_count'], 'candidates': {k: len(v) for k, v in result['candidates'].items()},
                     'scientific_success': False, 'graph_advantage_demonstrated': False}))


if __name__ == '__main__': main()
