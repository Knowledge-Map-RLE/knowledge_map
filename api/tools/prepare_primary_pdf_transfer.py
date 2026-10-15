"""CLI первичного корпуса; общие предиктор и оценщик запускаются раздельно."""
import argparse
import json

from application.primary_pdf_transfer import prepare_primary_transfer
from infrastructure.primary_pdf_transfer import load_primary_inputs,save_preparation
from tools.run_free_prediction import disable_network


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--legacy-manifest',required=True)
    args=p.parse_args();disable_network()
    annotation,evidence,legacy,bindings,identities,_=load_primary_inputs(args.root,args.legacy_manifest)
    result=prepare_primary_transfer(annotation,evidence,legacy,bindings)
    save_preparation(args.root,result,identities,evidence)
    print(json.dumps({**{k:v for k,v in result['audit'].items() if k!='rows'},'queries':result['query_count'],
                      'folds':len(result['folds']),'model_calls':0}))


if __name__=='__main__':main()
