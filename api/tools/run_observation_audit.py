"""Изолированный аудит источников: без сети, моделей и общей Neo4j."""
import argparse
import json
import logging
from pathlib import Path
from hashlib import sha256
from application.observation_identifiability import AuditObservationData
from infrastructure.observation_identifiability import FileObservationInputs,FileObservationAuditStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/observation_identifiability.py','domain/article_maps.py','application/observation_identifiability.py',
      'application/ports/observation_identifiability.py','infrastructure/observation_identifiability.py',
      'infrastructure/immutable_files.py','tools/run_observation_audit.py','tools/run_free_prediction.py')

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    disable_network();logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
    api=Path(__file__).resolve().parents[1];code={n:sha256((api/n).read_bytes()).hexdigest() for n in CODE}
    port=FileObservationInputs(args.manifest);store=FileObservationAuditStore(args.output)
    result=AuditObservationData(port,store).execute(code)
    for n in CODE:write_immutable(store.path(result['run_id'])/'implementation'/n,(api/n).read_bytes())
    write_immutable(store.path(result['run_id'])/'read-receipt.json',store.encode({'reads':port.reads,'network_disabled':True,'model_calls':0}))
    logging.info('Observation audit sources=%d empirical_predictions=0',len(result['audit']['sources']))
    print(json.dumps({'run_id':result['run_id']}))

if __name__=='__main__':main()
