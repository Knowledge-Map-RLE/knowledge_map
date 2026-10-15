"""Административный автономный CLI свободных механистических гипотез."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.mechanistic_opportunities import SealMechanisticOpportunities
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=('domain/mechanistic_opportunities.py','application/mechanistic_opportunities.py',
      'domain/whole_map_forecast.py','domain/whole_map_context.py','domain/whole_map_ablation.py',
      'domain/whole_map_input_audit.py','domain/comparison_normalization.py','domain/development_prediction.py',
      'domain/article_maps.py','application/compare_article_maps.py','infrastructure/free_prediction_snapshots.py',
      'infrastructure/development_prediction_store.py','infrastructure/immutable_files.py',
      'tools/run_free_prediction.py','tools/run_mechanistic_opportunities.py')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sources',required=True);parser.add_argument('--audit',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args();disable_network()
    raw=Path(args.sources).read_bytes();manifest=json.loads(raw);audit=json.loads(Path(args.audit).read_text(encoding='utf8'))
    maps=FileForecastMaps(manifest['sources']);store=FilePredictionStore(args.output);api=Path(__file__).resolve().parents[1]
    implementation={name:sha256((api/name).read_bytes()).hexdigest() for name in CODE}
    result=SealMechanisticOpportunities(maps,store).execute([s['reference'] for s in manifest['sources']],
        {s['reference']['article_id']:s['family'] for s in manifest['sources']},maps.owner,
        {**manifest['metadata'],'source_manifest_sha256':sha256(raw).hexdigest(),
         'source_dates':{s['reference']['article_id']:s['published_on'] for s in manifest['sources']}},implementation,audit)
    folder=store.path(result['run_id'])
    write_immutable(folder/'source-manifest.json',raw);write_immutable(folder/'mechanistic-audit.json',store.encode(audit))
    write_immutable(folder/'reads.json',store.encode({'reads':maps.reads,'network_disabled':True,'model_calls':0,'target_read':False}))
    for name in CODE:write_immutable(folder/'implementation'/name,(api/name).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'blocks':result['canonical_blocks'],'statements':result['statements'],
        'hypotheses':{m:len(v) for m,v in result['candidates'].items()},'scientific_success':False},ensure_ascii=False))


if __name__=='__main__':main()
