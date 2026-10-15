"""Административный CLI: гипотезы и оценка разделены, сеть запрещена."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from domain.article_maps import require
from application.qualitative_relations import SealQualitativeRelations,EvaluateQualitativeRelations
from infrastructure.qualitative_relations import FileQualitativeInputs,FileQualitativeControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/qualitative_relations.py','domain/article_maps.py','application/qualitative_relations.py',
      'application/ports/qualitative_relations.py','infrastructure/qualitative_relations.py',
      'infrastructure/development_prediction_store.py','infrastructure/immutable_files.py','tools/run_qualitative_relations.py','tools/run_free_prediction.py')
def implementation():
    api=Path(__file__).resolve().parents[1];return {n:sha256((api/n).read_bytes()).hexdigest() for n in CODE}
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['seal','evaluate']);p.add_argument('--output',required=True)
    p.add_argument('--manifest');p.add_argument('--controls');p.add_argument('--run-id');args=p.parse_args();disable_network()
    store=FilePredictionStore(args.output);code=implementation()
    if args.command=='seal':
        require(args.manifest and not args.controls and not args.run_id,'Seal must not receive controls')
        port=FileQualitativeInputs(args.manifest);r=SealQualitativeRelations(port,store).execute(code)
        api=Path(__file__).resolve().parents[1]
        for n in CODE:write_immutable(store.path(r['run_id'])/'implementation'/n,(api/n).read_bytes())
        write_immutable(store.path(r['run_id'])/'input-read-receipt.json',store.encode({'reads':port.reads,'network_disabled':True,'model_calls':0}))
        print(json.dumps({'run_id':r['run_id'],'folds':len(r['folds']),'candidates':sum(len(f['predictions']['semantic']) for f in r['folds'])}))
    else:
        require(args.controls and args.run_id and not args.manifest,'Evaluator requires seal and controls')
        port=FileQualitativeControls(args.controls);r=EvaluateQualitativeRelations(port,store).execute(args.run_id,code)
        write_immutable(store.path(args.run_id)/(r['evaluation_id']+'.receipt.json'),store.encode({'reads':port.reads,'network_disabled':True,'model_calls':0}))
        print(json.dumps({'evaluation_id':r['evaluation_id'],'totals':r['totals']}))
if __name__=='__main__':main()
