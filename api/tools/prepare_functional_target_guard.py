"""Code-разметка отдельных функциональных утверждений без подмены их связыванием."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.functional_target_guard import VERSION,DOMAIN
from infrastructure.functional_target_guard import load_functional_sources
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-run',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();disable_network();orientation,frozen,maps,cases=load_functional_sources(args.input_run)
    entries=[]
    for m in maps:
        selected=[c for c in cases if c['article_id']==m['article_id']]
        if not selected:continue
        def evidence(kid,uid,text,kind):
            u=next(u for u in m['source']['units']if u['id']==uid);require(u['text'].count(text)==1,'Functional quote must be unique')
            start=u['start']+u['text'].index(text)
            return {'knowledge_id':kid,'kind':kind,'quote':{'unit_id':uid,'start':start,'end':start+len(text),
                'text':text,'sha256':sha256(text.encode()).hexdigest()}}
        agent=next(r['value'] for r in selected[0]['method']['frame']['statements'][0]['roles']if r['role']=='intervention')
        if 'pmc5651799'in m['article_id']:
            alias='TROS';origin='cited_or_prior_report'
            quotes=[evidence('K3','U6','TROS selectively binds to hTNFR1 without cross-reacting with mTNFR1 or TNFR2','binding'),
                evidence('K3','U6','TROS inhibits the TNF/hTNFR1 pathway in vitro, ex vivo and in vivo in partially humanized mice','inhibition'),
                evidence('K5','U66','we generated BAC-transgenic mice expressing hTNFR1 in a mouse TNFR1-knockout background','model_domain')]
            function='Ранее описанное ингибирование TNF/hTNFR1 in vitro, ex vivo и in vivo в частично гуманизированных мышах; цитируемый контекст.'
            model='BAC-трансгенный человеческий TNFR1 на фоне нокаута мышиного TNFR1; исходная конструкция и контекст сохраняются.'
        else:
            alias='Atrosimab';origin='own_report_with_unread_supplement'
            quotes=[evidence('K29','U48','Using ELISA, Atrosimab was observed to bind to human, rhesus, and cynomolgus TNFR1 with similar EC50 values','binding'),
                evidence('K27','U45','All tested Atrosimab batches showed a dose-dependent inhibition of the TNF-induced IL-8 release with IC50 values ranging between 21.9 nM and 34.9 nM without statistically significant differences.','inhibition'),
                evidence('K12','U22','these are humanized transgenic animals, where the endogenous TNFR1 is exchanged for a chimeric TNFR1 composed of the extracellular domains of human TNFR1 fused to the transmembrane and intracellular part of mouse TNFR1.','model_domain'),
                evidence('K27','U45','Altogether, this indicates the high stability of Atrosimab and its suitability for clinical use as a TNFR1 antagonist.','source_antagonist_interpretation')]
            function='Главный текст сообщает ингибирование TNF-индуцированного IL-8 в HT1080 при исследованных условиях хранения; приложение не прочитано.'
            model='huTNFR1-k/i: человеческий внеклеточный домен и мышиные трансмембранный/внутриклеточный участки; не эквивалент полной человеческой конструкции.'
        roles=[{'role':'intervention','value':agent,'reference_kind':'concept'}]
        if alias=='TROS':
            predicate='reported pathway inhibition';roles += [{'role':'ligand','value':'tumor necrosis factor alpha','reference_kind':'concept'},
                {'role':'target','value':'human TNFR1','reference_kind':'concept'},
                {'role':'systems','value':'in vitro; ex vivo; in vivo in partially humanized mice','reference_kind':'concept'}]
        else:
            predicate='reported inhibition of stimulated release';roles += [
                {'role':'stimulus','value':'tumor necrosis factor alpha','reference_kind':'concept'},
                {'role':'outcome','value':'interleukin 8 release','reference_kind':'concept'},
                {'role':'assay population','value':'HT1080 cells','reference_kind':'concept'}]
        frame={'kind':'state','action_status':None,'logic':'single','statements':[{'predicate':predicate,'roles':roles,
            'scope':{'conditions':[x['quote']['text']for x in quotes if x['kind']=='inhibition'],
                'study_group':m['article_id'],'modality':'reported source claim','quantifier':None,
                'time':'reported functional context; no clinical time window inferred'},'negated':False,'attributes':[]}]}
        entries.append({'article_id':m['article_id'],'run_id':m['run_id'],'source_sha256':m['source']['sha256'],
            'case_ids':[c['case_id']for c in selected],'intervention':agent,'agent_alias':alias,'functional_origin':origin,
            'required_target_domain':DOMAIN,'model_target_domain':DOMAIN,'evidence':quotes,
            'functional_context_ru':function,'model_context_ru':model,'functional_frame':frame})
    audit={'version':VERSION,'author':'Codex','expert_validated':False,'model_calls':0,'source_sha256':fingerprint(frozen),
        'map_hashes':[fingerprint(m)for m in maps],'entries':entries,'preparation_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    write_immutable(Path(args.output),FilePredictionStore.encode(audit));print(json.dumps({'entries':len(entries),'sha256':fingerprint(audit)}))


if __name__=='__main__':main()
