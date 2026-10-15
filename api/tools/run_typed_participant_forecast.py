"""CLI повторяет весь корпус с двумя политиками, без моделей и будущего оценщика."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.typed_participant_forecast import SealTypedParticipantForecast
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_semantic_part_forecast import CODE as UPSTREAM_CODE

CODE = tuple(sorted(set(UPSTREAM_CODE) | {'domain/typed_participant_forecast.py', 'application/typed_participant_forecast.py',
    'tools/run_typed_participant_forecast.py', 'domain/article_maps.py', 'domain/comparison_normalization.py',
    'domain/evidence_origin_audit.py', 'domain/whole_map_forecast.py', 'domain/semantic_part_forecast.py',
    'domain/whole_map_ablation.py', 'domain/protocol_parameter_transfer.py', 'domain/forecast_attribute_kinds.py',
    'infrastructure/sealed_forecast_corpus.py', 'infrastructure/free_prediction_snapshots.py',
    'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
    'application/ports/development_prediction.py', 'tools/run_free_prediction.py'}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-run', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network(); logging.basicConfig(level=logging.INFO)
    corpus, store = SealedForecastCorpus(args.input_run), FilePredictionStore(args.output)
    root = Path(__file__).resolve().parents[1]
    implementation = {f: sha256((root / f).read_bytes()).hexdigest() for f in CODE}
    result = SealTypedParticipantForecast(corpus, store).execute(implementation)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'input-corpus.json', store.encode({'snapshot': str(corpus.root)}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'], 'parts': result['licensed_parts'],
        'digit_roles': len(result['digit_participants']), 'policies': {p: {m: {'hypotheses': len(v['predictions']),
        'rules': len(v.get('rules', []))} for m, v in modes.items()} for p, modes in result['policies'].items()}}))


if __name__ == '__main__': main()
