"""CLI фиксирует прогноз с допуском до доступа к удержанным ставкам."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path

from application.incidence_transfer_scope import SealIncidenceScope,EvaluateIncidenceScope
from domain.article_maps import require
from infrastructure.incidence_transfer_scope import FileIncidenceScopeInputs
from infrastructure.empirical_inference_files import FileEmpiricalControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/incidence_transfer_scope.py','domain/cohort_transfer.py','domain/article_maps.py','domain/empirical_inference.py',
      'application/incidence_transfer_scope.py','application/ports/incidence_transfer_scope.py',
      'infrastructure/incidence_transfer_scope.py','infrastructure/cohort_transfer_files.py',
      'infrastructure/empirical_inference_files.py','infrastructure/development_prediction_store.py',
      'infrastructure/immutable_files.py','tools/run_incidence_transfer_scope.py','tools/run_free_prediction.py')


def implementation():
    api=Path(__file__).resolve().parents[1]
    return {name:sha256((api/name).read_bytes()).hexdigest() for name in CODE}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['seal','evaluate']);p.add_argument('--output',required=True)
    p.add_argument('--manifest');p.add_argument('--controls');p.add_argument('--run-id')
    args=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    store=FilePredictionStore(args.output);code=implementation()
    if args.command=='seal':
        require(args.manifest and not args.controls and not args.run_id,'Seal must not receive controls')
        port=FileIncidenceScopeInputs(args.manifest);result=SealIncidenceScope(port,store).execute(code)
        receipt={'stage':'seal','reads':port.reads,'network_disabled':True,'model_calls':0}
        write_immutable(store.path(result['run_id'])/'input-read-receipt.json',store.encode(receipt))
        api=Path(__file__).resolve().parents[1]
        for name in CODE:write_immutable(store.path(result['run_id'])/'implementation'/name,(api/name).read_bytes())
        print(json.dumps({'run_id':result['run_id'],'queries':sum(len(f['predictions']) for f in result['folds']),
            'issued':sum(p['order'] is not None for f in result['folds'] for p in f['predictions'])}))
    else:
        require(args.controls and args.run_id and not args.manifest,'Evaluator requires sealed controls only')
        port=FileEmpiricalControls(args.controls);result=EvaluateIncidenceScope(port,store).execute(args.run_id,code)
        receipt={'stage':'evaluate','reads':port.reads,'network_disabled':True,'model_calls':0}
        write_immutable(store.path(args.run_id)/(result['evaluation_id']+'.receipt.json'),store.encode(receipt))
        print(json.dumps({'evaluation_id':result['evaluation_id'],'modes':{k:{f:v for f,v in m.items() if f!='rows'} for k,m in result['modes'].items()}}))


if __name__=='__main__':main()
