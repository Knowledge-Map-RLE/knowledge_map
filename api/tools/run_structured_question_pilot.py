"""Административный опыт с вручную подтверждёнными признаками без модельных вызовов."""
import argparse
import ctypes
import logging
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
from application.question_prediction import AuditResearchSemantics
from domain.article_maps import fingerprint, require
from domain.research_semantics import project_map
from domain.structured_question_context import validate_feature_records, StructuredQualitativeEngine
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.prepared_research_maps import PreparedResearchMaps
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.immutable_files import write_immutable
from infrastructure.structured_question_report import save_structured_review
from tools.run_prepared_question_pilot import read,bundles_from_manifest
from tools.import_codex_article_map import prohibit_generation


def main():
    parser=argparse.ArgumentParser(description='Структурированный контекст на фиксированном корпусе без LLM')
    for name in ('manifest','policy','features','previous_root','output'):
        parser.add_argument('--'+name.replace('_','-'),required=True,type=Path)
    parser.add_argument('--previous-run-id',required=True)
    parser.add_argument('--analysis-scope',required=True,choices=('primary','sensitivity'))
    args=parser.parse_args()
    require(sys.platform=='win32' and bool(ctypes.windll.shell32.IsUserAnAdmin()),'Administrative CLI required')
    prohibit_generation()
    logging.basicConfig(level=logging.INFO)
    manifest=read(args.manifest);policy=read(args.policy)
    bundles=bundles_from_manifest(manifest,args.manifest.parent)
    maps=PreparedResearchMaps(bundles,manifest['owner'],'training')
    refs=[{k:b['map'][k] for k in ('article_id','pipeline_id','run_id')} for b in bundles]
    registry={b['map']['article_id']:b['registry'] for b in bundles}
    annotations={b['map']['article_id']:b['annotation'] for b in bundles}
    previous=FilePredictionStore(args.previous_root).read_seal(args.previous_run_id)
    require(previous and previous['binding']['sources']==refs and previous['binding']['owner']==manifest['owner'],
            'Previous owner or corpus differs')
    expected=[{'article_id':b['map']['article_id'],'graph_sha256':fingerprint(b['map']['graph']),
               'source_sha256':b['map']['source']['sha256']} for b in bundles]
    require(previous['binding']['maps']==expected and previous['binding']['analysis_scope']==args.analysis_scope,
            'Previous source, graph or scope differs')
    claims={(c.evidence.article_id,c.claim_id):c for b in bundles for c in project_map(b['map'],b['registry'],b['annotation'])}
    supporting=[s for b in bundles for s in b['origin'].get('context_revision',{}).get('audit',{}).get('sources',[])]
    profiles=validate_feature_records(read(args.features),claims,{b['map']['article_id']:b['map'] for b in bundles},args.analysis_scope,supporting)
    engine=StructuredQualitativeEngine(profiles)
    for name,path in [('policy.snapshot.json',args.policy),('features.snapshot.json',args.features)]:
        write_immutable(args.output/name,path.read_bytes())
    audit=AuditResearchSemantics(maps,FileResearchArtifacts(args.output/'audits')).execute(
        refs,registry,annotations,manifest['controls'],manifest['owner'])
    require(audit['controls_passed']==audit['control_count'],'Semantic controls failed')
    forecast=SealQualitativeQuestionExperiment(maps,FilePredictionStore(args.output/'runs'),engine).execute(
        refs,registry,annotations,manifest['episodes'],manifest['question'],policy,manifest['owner'],args.analysis_scope)
    folder=args.output/'runs'/forecast['run_id']/'review-v2'
    save_structured_review(folder,forecast,previous,audit)
    receipt={'run_id':forecast['run_id'],'report_folder':folder.as_posix(),'sources':len(bundles),
             'families':len(forecast['retrospective_folds']),'claims':forecast['claim_count'],
             'structured_profiles':len(profiles),'controls_passed':audit['controls_passed'],
             'mode_counts':{m:len(v) for m,v in forecast['modes'].items()},'readiness':forecast['readiness'],
             'model_calls':0,'future_target_read':False,'services_changed':False}
    write_immutable(args.output/'receipt-v2.json',FilePredictionStore.encode(receipt))
    print(FilePredictionStore.encode(receipt).decode('utf-8'))


if __name__=='__main__':main()
