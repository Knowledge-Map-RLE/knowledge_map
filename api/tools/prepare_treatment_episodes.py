"""Разметка клинических эпизодов и просмотренного рисунка Codex, без моделей."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.treatment_episode_context import VERSION,compile_episodes
from infrastructure.treatment_episode_context import load_episode_sources
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

FIGURE_URL='https://cdn.ncbi.nlm.nih.gov/pmc/blobs/ddea/8294390/8420d5cfc6a2/fimmu-12-705485-g007.jpg'


def prepare(root,figure_bytes,xml_bytes):
    functional,frozen,maps,cases=load_episode_sources(root);catalog={m['article_id']:m for m in maps};entries=[]
    assets={'atrosimab_figure7':{'path':'figure7.jpg','sha256':sha256(figure_bytes).hexdigest(),
        'source_url':FIGURE_URL,'figure_id':'f7','xml_asset_id':'atrosimab_xml','width':716,'height':552},
        'atrosimab_xml':{'path':'article.xml','sha256':sha256(xml_bytes).hexdigest(),
            'source_url':'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC8294390/fullTextXML'}}
    for c in cases:
        m=catalog[c['article_id']]
        def quote(uid,text,qid):
            u=next(u for u in m['source']['units']if u['id']==uid);require(u['text'].count(text)==1,'Episode quote must be unique')
            start=u['start']+u['text'].index(text)
            return{'id':qid,'unit_id':uid,'start':start,'end':start+len(text),'text':text,'sha256':sha256(text.encode()).hexdigest()}
        def episode(eid,purpose,anchor,schedule,end,ids):
            return{'id':eid,'purpose':purpose,'anchor':anchor,'unit':'day','schedule':schedule,
                'observation_end':end,'observation_end_origin':'unknown'if end is None else 'source_method_endpoint',
                'evidence_ids':ids,'source_asserted_effect_duration':None}
        cid=c['case_id'];figure=None;reported=None;extra=[]
        if cid=='tros-prophylactic':
            evidence=[quote('U22','hTNFR1 Tg mice were prophylactically treated on day 3 post-immunization (PI), with 200 µg TROS or PBS intraperitoneally (i.p.) injected every two days until 13 days PI','course'),
                quote('U22','The cumulative disease score (c,f) was determined 16 days PI','endpoint'),
                quote('U81','mice were i.p. injected with 150 or 200 µg TROS, diluted in PBS, or with PBS alone every two or three days, respectively.','methods_conflict')]
            episodes=[episode('prophylactic_clinical','clinical_followup','post_immunization',
                {'form':'periodic','first':'3','last':'13','step':'2'},'16',['course','endpoint'])];extra=['K65']
        elif cid=='tros-manifest':
            evidence=[quote('U52','at disease onset in all mice (day 8 post-immunization (PI))','start'),
                quote('U52','In (a,b) the treatment was repeated on day 12 and 16 PI.','clinical_course'),
                quote('U52','In c-e, mice were treated on day 8 and 12 (clinical scores are not shown) and mice were sacrificed at day 16 PI.','tissue_course'),
                quote('U52','clinical scores (scale 0\u20125) (a, right) were assessed until 30 days PI.','endpoint'),
                quote('U51','three treatments with 500 µg TROS every four days (on days 8, 12 and 16 PI) significantly arrested disease progression and limited body weight loss compared to PBS treatment for 30 days PI, which is until 12 days after the last treatment','reported_distance')]
            episodes=[episode('therapeutic_clinical','clinical_followup','post_immunization',
                {'form':'explicit','points':['8','12','16']},'30',['start','clinical_course','endpoint']),
                episode('therapeutic_tissue','tissue_sampling','post_immunization',
                {'form':'explicit','points':['8','12']},'16',['tissue_course'])];reported='12'
        else:
            require(cid=='atrosimab-manifest','Unregistered source case')
            evidence=[quote('U86','Mice were injected i.p. on days 1, 4, 8 and 12 of manifest disease with either 30 mg/kg or 60 mg/kg Atrosimab, or 30 mg/kg FcΔab.','course'),
                quote('U86','Both dosages of Atrosimab led to an immediate and sustained improvement in (A) motor symptoms, reflected by the (B) cumulative EAE score','caption')]
            episodes=[episode('manifest_clinical','clinical_followup','manifest_disease_day',
                {'form':'explicit','points':['1','4','8','12']},None,['course'])]
            figure={'asset_id':'atrosimab_figure7','caption_evidence_id':'caption','panel':'A','axis_label':'days of EAE',
                'confirmed_assessment_day':'18','axis_upper_tick':'20','direction':'lower_reported_group_mean',
                'intervention_labels':['Atrosimab 30 mg/Kg','Atrosimab 60 mg/Kg'],'comparator_label':'FcDeltaab',
                'last_assessment_established':False,'pointwise_significance_inferred':False,'author':'Codex','expert_validated':False,
                'panel_bounds_pixels':{'x':0,'y':0,'width':218,'height':185},
                'interpretation_ru':'На панели A над отмеченным днём 18 видны точки средних двух доз ниже контроля. '
                    'Точные значения не снимались; отметка 20 является границей оси и не объявляется последней измеренной точкой.'}
        entries.append({'case_id':cid,'article_id':m['article_id'],'run_id':m['run_id'],'source_sha256':m['source']['sha256'],
            'participants':{r['role']:r['value']for r in c['method']['frame']['statements'][0]['roles']},
            'additional_parent_ids':extra,'evidence':evidence,'episodes':episodes,'reported_after_last_dose_days':reported,
            'figure_assessment':figure,'dose_frequency_conflict':cid=='tros-prophylactic'})
    audit={'version':VERSION,'author':'Codex','expert_validated':False,'model_calls':0,
        'functional_sha256':fingerprint(functional),'source_sha256':fingerprint(frozen),
        'map_hashes':[fingerprint(m)for m in maps],'entries':entries,'assets':assets,
        'preparation_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    compile_episodes(functional,frozen,maps,cases,audit,{'atrosimab_figure7':figure_bytes,'atrosimab_xml':xml_bytes})
    return audit


def main():
    p=argparse.ArgumentParser()
    for name in ('input-run','figure','xml','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();disable_network();figure=Path(a.figure).read_bytes();xml=Path(a.xml).read_bytes()
    audit=prepare(a.input_run,figure,xml);folder=Path(a.output).resolve()
    write_immutable(folder/'figure7.jpg',figure);write_immutable(folder/'article.xml',xml)
    write_immutable(folder/'audit.json',FilePredictionStore.encode(audit))
    print(json.dumps({'entries':len(audit['entries']),'audit_sha256':fingerprint(audit),'figure_sha256':sha256(figure).hexdigest()}))


if __name__=='__main__':main()
