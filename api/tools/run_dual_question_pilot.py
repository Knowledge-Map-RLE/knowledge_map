"""Локальный исследовательский CLI: новые исходы, прежний явный корпус, HTTP генерации запрещён."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
from application.question_prediction import AuditResearchSemantics
from domain.article_maps import fingerprint,require
from domain.dual_question_outcomes import DualOutcomeEngine,validate_transport
from domain.structured_question_context import validate_feature_records
from domain.research_semantics import project_map
from infrastructure.prepared_research_maps import PreparedResearchMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.immutable_files import write_immutable
from infrastructure.dual_question_report import save_dual_review
from tools.run_prepared_question_pilot import read,bundles_from_manifest
from tools.import_codex_article_map import prohibit_generation


def main():
    p=argparse.ArgumentParser(description='Знак оценки и значимость без модельных вызовов')
    for name in ('manifest','policy','features','transport','previous_root','output'):
        p.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    p.add_argument('--previous-run-id',required=True)
    p.add_argument('--analysis-scope',choices=('primary','sensitivity'),required=True)
    args=p.parse_args();prohibit_generation();logging.basicConfig(level=logging.INFO)
    manifest=read(args.manifest);policy=read(args.policy);transport=validate_transport(read(args.transport))
    bundles=bundles_from_manifest(manifest,args.manifest.parent);maps=PreparedResearchMaps(bundles,manifest['owner'],'training')
    refs=[{k:b['map'][k] for k in ('article_id','pipeline_id','run_id')} for b in bundles]
    registry={b['map']['article_id']:b['registry'] for b in bundles};annotations={b['map']['article_id']:b['annotation'] for b in bundles}
    previous=FilePredictionStore(args.previous_root).read_seal(args.previous_run_id)
    expected=[{'article_id':b['map']['article_id'],'source_sha256':b['map']['source']['sha256'],'graph_sha256':fingerprint(b['map']['graph'])} for b in bundles]
    require(previous and previous['binding']['sources']==refs and previous['binding']['maps']==expected
            and previous['binding']['owner']==manifest['owner'] and previous['binding']['analysis_scope']==args.analysis_scope,
            'Previous explicit corpus, owner, map or scope differs')
    claims={(c.evidence.article_id,c.claim_id):c for b in bundles for c in project_map(b['map'],b['registry'],b['annotation'])}
    support=[s for b in bundles for s in b['origin'].get('context_revision',{}).get('audit',{}).get('sources',[])]
    profiles=validate_feature_records(read(args.features),claims,{b['map']['article_id']:b['map'] for b in bundles},args.analysis_scope,support)
    # Политика и входы фиксируются перед обучением; целевые результаты в них не добавляются.
    for name,path in [('policy.snapshot.json',args.policy),('features.snapshot.json',args.features),('transport.snapshot.json',args.transport)]:
        write_immutable(args.output/name,path.read_bytes())
    audit=AuditResearchSemantics(maps,FileResearchArtifacts(args.output/'audits')).execute(refs,registry,annotations,manifest['controls'],manifest['owner'])
    require(audit['controls_passed']==audit['control_count'],'Semantic controls failed')
    forecast=SealQualitativeQuestionExperiment(maps,FilePredictionStore(args.output/'runs'),DualOutcomeEngine(profiles,transport)).execute(
        refs,registry,annotations,manifest['episodes'],manifest['question'],policy,manifest['owner'],args.analysis_scope)
    folder=args.output/'runs'/forecast['run_id']/'review-v2';review=save_dual_review(folder,forecast,audit)
    receipt={'run_id':forecast['run_id'],'report_folder':folder.as_posix(),'summary':review['summary'],'model_calls':0,
             'future_target_read':False,'services_changed':False,'privileged_operations':False}
    write_immutable(args.output/'receipt-v2.json',FilePredictionStore.encode(receipt))
    print(FilePredictionStore.encode(receipt).decode('utf-8'))


if __name__=='__main__':main()
