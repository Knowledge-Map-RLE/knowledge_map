"""Источниковая разметка трёх режимов двух опытов; исходные эффекты не меняются."""
import argparse
from hashlib import sha256
from pathlib import Path
import json

from domain.article_maps import fingerprint, require
from domain.operation_applicability import VERSION, analyze
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def prepare(root):
    forecast, maps, origin = SealedForecastCorpus(root).load()
    catalog = {m['article_id']: m for m in maps}
    def select(pmc, kid, predicate, role=None):
        candidates = [v for v in forecast['part_views'] if ('pmc'+pmc) in v['native_key'][0]
                      and v['native_key'][1] == kid and v['frame']['statements'][0]['predicate'] == predicate
                      and (role is None or any(r['role'] == role[0] and r['value'] == role[1] for r in v['frame']['statements'][0]['roles']))]
        # Предпочитается явное источниковое дополнение; исходный вариант сохраняется в прогнозе.
        extended = [v for v in candidates if 'role_binding_proof' in v['projection_proof']]
        if extended: candidates = extended
        require(len(candidates) == 1, f'Applicability view must be unique: {pmc}/{kid}/{predicate}, found {len(candidates)}')
        return candidates[0]
    def quote(article, uid, text):
        m = catalog[article]; unit = next(u for u in m['source']['units'] if u['id'] == uid)
        require(unit['text'].count(text) == 1, 'Applicability quote must occur once')
        start = unit['start'] + unit['text'].index(text)
        return {'unit_id': uid, 'start': start, 'end': start+len(text), 'text': text,
                'sha256': sha256(text.encode()).hexdigest(), 'source_asserts_feature': True}
    cases = []
    configs = [
        ('5651799','tros-prophylactic','K28','K30','prophylactic','U22',
         'hTNFR1 Tg mice were prophylactically treated on day 3 post-immunization (PI)',
         'Mice were weighed and clinically scored daily.'),
        ('5651799','tros-manifest','K48','K49','manifest_disease','U52',
         'hTNFR1 Tg mice with ongoing EAE were divided in balanced groups and therapeutically treated with 500 µg TROS or PBS',
         'Mice were weighed and clinically scored daily.'),
        ('8294390','atrosimab-manifest','K21','K47','manifest_disease','U86',
         'Mice were injected i.p. on days 1, 4, 8 and 12 of manifest disease',
         'Mean clinical score (A) and cumulative disease score (B)'),
    ]
    for pmc, cid, mid, rid, phase, uid, phase_text, measured_text in configs:
        atros = pmc == '8294390'
        method = select(pmc, mid, 'administer treatment')
        measurement = select(pmc, 'K20' if atros else 'K9', 'measure clinical course', ('outcome','eae clinical score'))
        result = select(pmc, rid, 'improved after intervention' if atros else 'reduced after intervention', ('outcome',
            'eae motor symptoms and cumulative clinical score' if atros else 'eae clinical progression'))
        article = method['native_key'][0]; m = catalog[article]
        if atros:
            species = quote(article,'U34','female mice (6,7,8 weeks old) were immunized s.c.')
            disease = quote(article,'U86','huTNFR1-k/i mice were immunized with MOG35-55 peptide to induce EAE.')
            target = quote(article,'U22','the endogenous TNFR1 is exchanged for a chimeric TNFR1 composed of the extracellular domains of human TNFR1 fused to the transmembrane and intracellular part of mouse TNFR1')
            action = [quote(article,'U89','novel monovalent TNFR1 antagonist Atrosimab'),
                      quote(article,'U48','As expected, Atrosimab did not bind to human or mouse TNFR2.')]
            route = quote(article,'U86','Mice were injected i.p.')
            measurement_e = quote(article,'U34','Mice were weighed and scored on a daily basis, with disease severity assessed using a scale ranging from 0 to 5')
            basis = ['K20','K21','K47','K12','K29','K3']
        else:
            species = quote(article,'U75','males for EAE experiments')
            disease = quote(article,uid,'hTNFR1 transgenic (Tg) and TNFR1−/− mice were immunized with MOG35-55-peptide and pertussis toxin to induce EAE.')
            target = quote(article,'U10','we generated human TNFRSF1A transgenic (hTNFR1 Tg) mice in a mouse TNFR1 KO-background')
            action = [quote(article,'U6','TROS that binds and inhibits human TNFR1 (hTNFR1)'),
                      quote(article,'U6','TROS selectively binds to hTNFR1 without cross-reacting with mTNFR1 or TNFR2')]
            route = quote(article,uid,'intraperitoneally (i.p.)')
            measurement_e = quote(article,uid,measured_text)
            basis = ['K9',mid,rid,'K3','K5']
        features = {'species':'mouse','disease_model':'mog35_55_induced_eae','target':'human_tnfr1_extracellular_binding',
                    'intervention_action':'selective_tnfr1_inhibition','route':'intraperitoneal','phase':phase,
                    'measurement_kind':'ordinal_eae_clinical_score'}
        evidence = {'species':[species], 'disease_model':[disease], 'target':[target], 'intervention_action':action,
                    'route':[route], 'phase':[quote(article,uid,phase_text)], 'measurement_kind':[measurement_e]}
        direction = quote(article,'U85','Atrosimab at a dose of 30 and 60 mg/kg ameliorated EAE motor disease compared to treatment with Fc∆ab') if atros else (
            quote(article,'U21','TROS significantly suppressed EAE progression compared to PBS') if phase == 'prophylactic' else
            quote(article,'U51','significantly arrested disease progression and limited body weight loss compared to PBS treatment'))
        cases.append({'id':cid, 'method':method['key'], 'measurement':measurement['key'], 'result':result['key'],
            'basis':[[article,k] for k in basis], 'features':features, 'feature_evidence':evidence,
            'outcome_class':'clinical_eae_burden', 'qualitative_direction':'lower_clinical_burden', 'direction_evidence':[direction],
            'source_sha256':m['source']['sha256'], 'graph_sha256':fingerprint(m['graph']),
            'reason_ru':'Режим и предметные признаки указаны по источнику; полные шкалы, дозы, генотипы, контролы и результаты сохранены. Класс клинического проявления не означает эквивалентность показателей.'})
    audit = {'version':VERSION, 'author':'Codex', 'model_calls':0, 'expert_validated':False,
             'input_run_id':forecast['run_id'], 'input_sha256':fingerprint(forecast), 'cases':cases,
             'author_script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    analyze(forecast,maps,origin,audit)
    return audit


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input-run',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();disable_network();audit=prepare(a.input_run)
    path=Path(a.output).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    write_immutable(path,FilePredictionStore.encode(audit));print(json.dumps({'cases':len(audit['cases']),'model_calls':0}))


if __name__ == '__main__': main()
