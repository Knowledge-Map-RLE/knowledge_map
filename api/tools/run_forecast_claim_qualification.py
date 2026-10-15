"""Офлайн-CLI квалифицирует все кандидаты сохранённого прогона на полном корпусе."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path

from application.forecast_claim_qualification import SealForecastClaimQualification
from infrastructure.forecast_claim_qualification import FileClaimQualificationInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/forecast_temporal_scope.py', 'domain/forecast_claim_qualification.py',
    'application/forecast_claim_qualification.py', 'infrastructure/forecast_claim_qualification.py',
    'tools/prepare_forecast_claim_qualification.py', 'tools/run_forecast_claim_qualification.py',
    'domain/article_maps.py', 'domain/comparison_normalization.py',
    'infrastructure/sealed_forecast_corpus.py', 'infrastructure/free_prediction_snapshots.py',
    'infrastructure/external_operation_inputs.py', 'infrastructure/development_prediction_store.py',
    'infrastructure/immutable_files.py', 'tools/run_free_prediction.py')


def main():
    parser = argparse.ArgumentParser()
    for field in ('forecast', 'audit', 'output'): parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network(); logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    root = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    inputs = FileClaimQualificationInputs(args.forecast, args.audit); store = FilePredictionStore(args.output)
    result = SealForecastClaimQualification(inputs, store).execute(implementation); folder = store.path(result['run_id'])
    write_immutable(folder / 'audit.json', Path(args.audit).read_bytes())
    write_immutable(folder / 'input-corpus.json', store.encode({'forecast': str(inputs.root), 'model_calls': 0}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'canonical_blocks': result['canonical_blocks'],
        'semantic_statements': result['semantic_statements'], 'citations': len(result['citation_occurrences']),
        'status_counts': result['status_counts'], 'scientific_confirmations': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
