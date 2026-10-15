"""Фиксация свободного прогноза до открытия ранее не разобранной статьи."""
import argparse,json,logging
from pathlib import Path
from hashlib import sha256
from application.frozen_transfer import FreezeTransfer
from infrastructure.frozen_transfer import FileTransferInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/frozen_transfer.py','domain/knowledge_foundation.py','domain/qualitative_relations.py','domain/article_maps.py',
      'application/frozen_transfer.py','application/ports/frozen_transfer.py','infrastructure/frozen_transfer.py',
      'infrastructure/development_prediction_store.py','infrastructure/immutable_files.py','tools/freeze_qualitative_transfer.py','tools/run_free_prediction.py')

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    disable_network();api=Path(__file__).resolve().parents[1];code={n:sha256((api/n).read_bytes()).hexdigest() for n in CODE}
    port=FileTransferInputs(a.manifest);store=FilePredictionStore(a.output);r=FreezeTransfer(port,store).execute(code)
    for n in CODE:write_immutable(store.path(r['run_id'])/'implementation'/n,(api/n).read_bytes())
    write_immutable(store.path(r['run_id'])/'reads.json',store.encode({'reads':port.reads,'network_disabled':True,'target_access':False,'model_calls':0}))
    logging.basicConfig(level=logging.INFO);logging.info('Frozen qualitative transfer candidates=%d',len(r['generation']['forecast']['predictions']['semantic']))
    print(json.dumps({'run_id':r['run_id'],'mode_counts':{m:len(c) for m,c in r['generation']['forecast']['predictions'].items()}}))

if __name__=='__main__':main()
