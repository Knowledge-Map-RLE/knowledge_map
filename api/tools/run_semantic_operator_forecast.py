"""CLI экспериментального переноса с явным каталогом и раздельными стадиями."""
import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from time import perf_counter

from application.semantic_operator_forecast import SealOperatorForecast, EvaluateOperatorForecast
from infrastructure.prepared_operator_corpus import PreparedOperatorCorpus
from infrastructure.development_prediction_store import FilePredictionStore


def main():
    parser = argparse.ArgumentParser(description='Offline source-bound semantic operator forecast')
    parser.add_argument('stage', choices=['seal', 'evaluate'])
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--sources', nargs='+')
    parser.add_argument('--application')
    parser.add_argument('--as-of')
    parser.add_argument('--heldout-family', action='append', dest='heldout')
    parser.add_argument('--protocol', type=Path)
    parser.add_argument('--run-id')
    args = parser.parse_args()
    def no_network(event, values):
        if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.bind'):
            raise RuntimeError('Network forbidden in semantic operator CLI')
    sys.addaudithook(no_network)
    logging.basicConfig(level=logging.INFO)
    started = perf_counter()
    corpus = PreparedOperatorCorpus(json.loads(args.catalog.read_text(encoding='utf-8')))
    store = FilePredictionStore(args.store)
    if args.stage == 'seal':
        if not all([args.sources, args.application, args.as_of, args.heldout, args.protocol]):
            parser.error('seal requires sources, application, as-of, heldout-family and protocol')
        protocol_sha256 = hashlib.sha256(args.protocol.read_bytes()).hexdigest()
        result = SealOperatorForecast(corpus, store).execute(args.sources, args.application, args.as_of, args.heldout, protocol_sha256)
        output = {'run_id': result['run_id'], 'learned_operators': len(result['learned']['rules']),
                  'predictions': {k: len(v['predictions']) for k, v in result['forecasts'].items()}, 'model_calls': 0}
    else:
        if not args.run_id: parser.error('evaluate requires run-id')
        result = EvaluateOperatorForecast(corpus, store).execute(args.run_id)
        output = {'run_id': args.run_id, 'evaluation_id': result['evaluation_id'], 'scientific_success': False, 'model_calls': 0}
    logging.info('semantic_operator_cli stage=%s duration_seconds=%.3f', args.stage, perf_counter()-started)
    print(json.dumps(output))


if __name__ == '__main__': main()
