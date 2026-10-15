"""Изолированный CLI фундаментального опыта; генератор не читает контроль."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path
from domain.article_maps import require
from application.knowledge_foundation import SealFoundationPilot, EvaluateFoundationPilot
from infrastructure.knowledge_foundation import FileFoundationInputs, FileFoundationControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/knowledge_foundation.py', 'domain/qualitative_relations.py', 'domain/article_maps.py',
        'application/knowledge_foundation.py', 'application/ports/knowledge_foundation.py',
        'infrastructure/knowledge_foundation.py', 'infrastructure/development_prediction_store.py',
        'infrastructure/immutable_files.py', 'tools/run_foundation_pilot.py', 'tools/run_free_prediction.py')

def implementation():
    api = Path(__file__).resolve().parents[1]
    return {n: sha256((api/n).read_bytes()).hexdigest() for n in CODE}

def main():
    p = argparse.ArgumentParser(); p.add_argument('command', choices=['seal', 'evaluate'])
    p.add_argument('--output', required=True); p.add_argument('--manifest'); p.add_argument('--controls'); p.add_argument('--run-id')
    args = p.parse_args(); disable_network(); logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    store = FilePredictionStore(args.output); code = implementation()
    if args.command == 'seal':
        require(args.manifest and not args.controls and not args.run_id, 'Seal accepts only training inputs')
        port = FileFoundationInputs(args.manifest); result = SealFoundationPilot(port, store).execute(code)
        api = Path(__file__).resolve().parents[1]
        for n in CODE: write_immutable(store.path(result['run_id'])/'implementation'/n, (api/n).read_bytes())
        write_immutable(store.path(result['run_id'])/'input-read-receipt.json', store.encode({'reads': port.reads, 'network_disabled': True, 'model_calls': 0}))
        logging.info('Foundation sealed: folds=%d blocks=%d', len(result['folds']), len(result['foundation']['knowledge']))
        print(json.dumps({'run_id': result['run_id']}))
    else:
        require(args.controls and args.run_id and not args.manifest, 'Evaluation requires seal and controls')
        port = FileFoundationControls(args.controls); result = EvaluateFoundationPilot(port, store).execute(args.run_id, code)
        write_immutable(store.path(args.run_id)/(result['evaluation_id']+'.receipt.json'), store.encode({'reads': port.reads, 'network_disabled': True, 'model_calls': 0}))
        logging.info('Foundation evaluated: modes=%d independent_success=false', len(result['totals']))
        print(json.dumps({'evaluation_id': result['evaluation_id'], 'totals': result['totals']}))

if __name__ == '__main__': main()
