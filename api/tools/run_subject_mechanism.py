"""Изолированный CLI: без AI и сети, с неизменяемыми квитанциями."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path
from domain.article_maps import require
from application.subject_mechanism import SealSubjectMechanism, AuditSubjectMechanism
from infrastructure.subject_mechanism import FileMechanismInputs, FileMechanismProfiles
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/subject_mechanism.py','domain/knowledge_foundation.py','domain/article_maps.py',
      'application/subject_mechanism.py','application/ports/subject_mechanism.py',
      'infrastructure/subject_mechanism.py','infrastructure/development_prediction_store.py',
      'infrastructure/immutable_files.py','tools/run_subject_mechanism.py','tools/run_free_prediction.py')

def implementation():
    api=Path(__file__).resolve().parents[1]
    return {n:sha256((api/n).read_bytes()).hexdigest() for n in CODE}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['seal','audit'])
    parser.add_argument('--output',required=True);parser.add_argument('--manifest');parser.add_argument('--profiles');parser.add_argument('--run-id')
    args=parser.parse_args();disable_network();code=implementation();store=FilePredictionStore(args.output)
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
    if args.command=='seal':
        require(args.manifest and not args.profiles and not args.run_id,'Seal accepts only training input')
        port=FileMechanismInputs(args.manifest);result=SealSubjectMechanism(port,store).execute(code)
        api=Path(__file__).resolve().parents[1]
        for n in CODE:write_immutable(store.path(result['run_id'])/'implementation'/n,(api/n).read_bytes())
        logging.info('Mechanism sealed candidates=%d model_calls=0',len(result['generation']['candidates']))
    else:
        require(args.profiles and args.run_id and not args.manifest,'Audit requires sealed run')
        port=FileMechanismProfiles(args.profiles);result=AuditSubjectMechanism(port,store).execute(args.run_id,code)
        logging.info('Applicability audited candidates=%d empirical_release=0',len(result['rows']))
    identifier=result.get('evaluation_id','input')
    write_immutable(store.path(result['run_id'] if args.command=='seal' else args.run_id)/(identifier+'.receipt.json'),
                    store.encode({'reads':port.reads,'network_disabled':True,'model_calls':0}))
    print(json.dumps({k:result[k] for k in ('run_id','evaluation_id') if k in result}))

if __name__=='__main__':main()
