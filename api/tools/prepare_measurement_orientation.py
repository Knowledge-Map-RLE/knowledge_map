"""Codex связывает шкалы и клинические утверждения по полным собственным источникам."""
import argparse
from hashlib import sha256
from pathlib import Path
import json
from domain.article_maps import fingerprint,require
from domain.measurement_orientation import VERSION
from infrastructure.measurement_orientation import load_sources
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore
from tools.run_free_prediction import disable_network


def main():
    parser=argparse.ArgumentParser()
    for f in ('input-run','applicability','output'):parser.add_argument('--'+f,required=True)
    args=parser.parse_args();disable_network();previous,frozen,maps,origins,cases=load_sources(args.input_run,args.applicability)
    catalog={m['article_id']:m for m in maps};entries=[]
    for c in cases:
        m=catalog[c['article_id']]
        def quote(uid,text):
            u=next(u for u in m['source']['units'] if u['id']==uid);require(u['text'].count(text)==1,'Orientation quote must be unique')
            start=u['start']+u['text'].index(text)
            return {'unit_id':uid,'start':start,'end':start+len(text),'text':text,'sha256':sha256(text.encode()).hexdigest()}
        if 'pmc5651799' in c['article_id']:
            order=quote('U79','Paralysis was scored according to a scale as follows: 0, no clinical disease; 1, weakness of tail; 2, complete loss of tail tonicity; 3, partial hind limb paralysis; 4, complete hind limb paralysis; 5, forelimb paralysis or moribund; 6, death.')
            anchors=[{'value':'0','meaning_ru':'Нет клинической болезни.','source_fragment':'0, no clinical disease'},
                {'value':'5','meaning_ru':'Паралич передних конечностей или предсмертное состояние.','source_fragment':'5, forelimb paralysis or moribund'},
                {'value':'6','meaning_ru':'Смерть.','source_fragment':'6, death'}]
            if c['case_id']=='tros-prophylactic':
                bridge=quote('U21','As shown in Fig. 3a,b, mice treated with TROS lost less weight, and TROS significantly suppressed EAE progression compared to PBS.')
                caveat=quote('U22','clinical disease scores (scale 0-5) were assessed (b,e)')
            else:
                bridge=quote('U51','At this time point, the cumulative disease index was significantly lower in TROS treated mice (p < 0.0001) and did not significantly differ from the mean cumulative score of TNFR1−/− mice (p = 0.44)')
                caveat=quote('U52','clinical scores (scale 0\u20125) (a, right) were assessed until 30 days PI')
            caveats=[caveat];issue='Определение включает 6 (смерть), а подпись рисунка указывает 0–5. Количественное согласование не установлено.'
        else:
            order=quote('U34','with disease severity assessed using a scale ranging from 0 to 5: 0, no clinical disease; 0.5, distal paresis of the tail; 1.0, complete paralysis of the tail; 1.5, paresis of tail and mildly impaired righting reflex; 2.0, gait ataxia and severely reduced righting reflex; 2.5, bilateral severe hind limb paresis; 3.0, complete bilateral hind limb paralysis; 3.5, complete bilateral hind limb paralysis and forelimb paresis; 4, hind and fore limb paralysis; 5, moribund state or death.')
            anchors=[{'value':'0','meaning_ru':'Нет клинической болезни.','source_fragment':'0, no clinical disease'},
                {'value':'4','meaning_ru':'Паралич задних и передних конечностей.','source_fragment':'4, hind and fore limb paralysis'},
                {'value':'5','meaning_ru':'Предсмертное состояние или смерть.','source_fragment':'5, moribund state or death'}]
            bridge=quote('U86','Both dosages of Atrosimab led to an immediate and sustained improvement in (A) motor symptoms, reflected by the (B) cumulative EAE score')
            caveats=[];issue='Шкала с половинными шагами до 5 не объявлена эквивалентной шкале TROS.'
        measurement=c['measurement']['frame']['statements'][0];result=c['result']['frame']['statements'][0]
        value=lambda atom:next(r['value'] for r in atom['roles'] if r['role']=='outcome')
        entries.append({'case_id':c['case_id'],'case_sha256':fingerprint(c),'source_sha256':m['source']['sha256'],
            'source_measure':value(measurement),'source_outcome':value(result),
            'property_label':'reported EAE clinical burden','orientation':'higher_is_worse','effect':'improved',
            'anchors':anchors,'order_evidence':[order],'bridge_evidence':[bridge],
            'scale_caveat_evidence':caveats,'scale_caveat_ru':issue,
            'reason_ru':'Числа шкалы упорядочивают описанные состояния. Клиническое улучшение обобщено только '
                'до направления бремени данного опыта. Сырые шкалы, исходы и эффекты не отождествляются. Требуется экспертная проверка.'})
    audit={'version':VERSION,'author':'Codex','expert_validated':False,'model_calls':0,'source_sha256':fingerprint(frozen),
        'map_hashes':[fingerprint(m) for m in maps],'entries':entries,'preparation_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    write_immutable(Path(args.output),FilePredictionStore.encode(audit));print(json.dumps({'entries':len(entries),'sha256':fingerprint(audit)}))


if __name__=='__main__':main()
