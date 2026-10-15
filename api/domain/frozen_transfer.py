"""Фиксация свободных качественных гипотез с отдельными базовыми режимами."""
from domain.article_maps import require
from domain.knowledge_foundation import normalize
from domain.qualitative_relations import forecast_fold

VERSION='frozen-qualitative-transfer-1'

def generate_transfer(data):
    p=data['protocol'];require(p['model_calls']==0 and p['target_access'] is False and p['question'] is None,'Source-only policy differs')
    records=data['annotation']['records'];claims=[];proofs=[]
    for native in records:
        claim,proof=normalize(native,data['foundation'],'dependencies');claims.append(claim)
        if proof:proofs.append(proof)
    result=forecast_fold({'fold_id':'unselected-independent-control','withheld_family':'__unseen__','training':claims})
    for mode,candidates in result['predictions'].items():
        for c in candidates:
            c['expected_effect_size']=None;c['confirmed']=False
            c['support_semantics']={'kind':'empirical_replication','minimum_independent_cohorts':2 if mode=='semantic' else None,
                                    'logical_entailment':False,'all_premises_jointly_required':False}
    return {'version':VERSION,'training_claims':claims,'normalization_proofs':proofs,'forecast':result,
            'training_families':sorted({c['family_id'] for c in claims}),
            'confirmed_new_scientific_knowledge':0,'scientific_success':False,
            'status':'frozen_before_target_selection','target_chosen':False,
            'graph_advantage_demonstrated':False,
            'baseline_note':'All three modes use the same normalized semantics; semantic hypotheses also occur in known-union and frequency baselines.'}
