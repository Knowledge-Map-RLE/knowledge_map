"""Качественные следствия явно типизированных моделей сохраняют составной блок."""
from copy import deepcopy
from decimal import Decimal
from domain.comparison_normalization import normalize
from domain.statistical_primitives import number, statistical_finding, interval_diagnostic, attributes, roles, direction

VERSION='typed-statistical-model-views-1'
MODELS={
    'estimated hazard ratio':{'model':'cox regression','estimand':'hazard ratio for ≥5-point 3mse decline',
        'unit':'dimensionless','null':Decimal(1),'predicate':'reported fitted hazard direction'},
    'estimated cognitive level difference':{'model':'mixed-effects regression','estimand':'midpoint 3mse level difference',
        'unit':'3mse points per sd','null':Decimal(0),'predicate':'reported fitted cognitive level direction'},
    'estimated instantaneous rate difference':{'model':'mixed-effects regression','estimand':'instantaneous 3mse change difference at 3.5 years',
        'unit':'3mse points per centered visit per sd','null':Decimal(0),'predicate':'reported fitted instantaneous rate direction'},
}
FIELDS={'evidence presentation','estimate','ci95 printed','p','alpha','analysis n','printed estimate ci95',
        'model','model number','estimand','exposure increment','transform','adjustment','time basis','baseline mci'}
REQUIRED={'evidence presentation','estimate','p','alpha','analysis n','model','estimand','exposure increment','transform','adjustment','time basis','baseline mci'}


def project_statement(s):
    spec=MODELS.get(s['predicate'])
    if spec is None:return None,'no_typed_model_contract'
    a,r=attributes(s),roles(s)
    if a is None or r is None:return None,'ambiguous_model_attribute_or_role'
    if not REQUIRED<=set(a) or set(a)-FIELDS:return None,'missing_or_unrecognized_model_fields'
    if not {'exposure','outcome','population','adjustment'}<=set(r):return None,'model_axes_missing'
    if any(not isinstance(v,str) for v in r.values()):return None,'unresolved_model_participant'
    if s['negated'] or s['scope']['modality'] not in (None,'reported','as reported'):return None,'model_not_asserted_as_observed'
    if s['scope']['study_group'] is None:return None,'empirical_model_scope_missing'
    if normalize(a['evidence presentation']['value'])!='own result':return None,'independent_observation_not_established'
    if normalize(a['model']['value'])!=spec['model'] or normalize(a['estimand']['value'])!=spec['estimand']:
        return None,'model_or_estimand_mismatch'
    if normalize(a['estimate']['unit'])!=spec['unit']:return None,'model_effect_unit_mismatch'
    if normalize(a['exposure increment']['value'])!='one sd higher baseline biomarker in stated transformation':
        return None,'positive_exposure_increment_not_established'
    if normalize(a['adjustment']['value'])!=r['adjustment'] or normalize(a['baseline mci']['value'])!=r['population']:
        return None,'model_scope_role_mismatch'
    if normalize(a['transform']['value']) not in {'as modeled','log; base unspecified'}:
        return None,'uninterpreted_exposure_transformation'
    point,alpha,n=number(a['estimate']['value']),number(a['alpha']['value']),number(a['analysis n']['value'])
    if point is None:return None,'ambiguous_model_point_estimate'
    if spec['null']==1 and point<=0:return None,'nonpositive_hazard_ratio'
    if alpha is None or not 0<alpha<1 or n is None or n<=0 or n!=n.to_integral_value():
        return None,'invalid_declared_threshold_or_sample'
    if a['alpha']['unit']!='dimensionless':return None,'threshold_unit_not_dimensionless'
    finding=statistical_finding(a['p']['value'],str(alpha))
    if finding=='not_established':return None,'uninterpreted_model_test'
    result=deepcopy(s);result['predicate']=spec['predicate']
    # Условия модели, экспозиции и порога остаются ограничениями сопоставления.
    conditions=list(result['scope']['conditions'])+[
        'statistical model: '+spec['model'], 'effect estimand: '+spec['estimand'],
        'effect unit: '+spec['unit'],'positive increment: '+normalize(a['exposure increment']['value']),
        'exposure transform: '+normalize(a['transform']['value']),
        'model time basis: '+normalize(a['time basis']['value']),
        'conditional strict test of printed p < '+str(alpha)]
    result['scope']['conditions']=sorted(set(conditions))
    result['attributes']=[{'name':'reported fitted direction','value':direction(point,spec['null']),'unit':None},
        {'name':'conditional statistical finding','value':finding,'unit':None},
        {'name':'interpretation','value':'reported fitted association under explicit model; causality not asserted','unit':None}]
    result.pop('attribute_types',None)
    return {'statement':result,'point':str(point),'null':str(spec['null']),
        'model':spec['model'],'estimand':spec['estimand'],'unit':spec['unit'],
        'statistical_finding':finding,'declared_alpha':str(alpha),'analysis_n':str(n),
        'interval_diagnostic':interval_diagnostic(a.get('ci95 printed',{}).get('value'),point),
        'finding_basis':'conditional comparison of printed rounded p and explicit threshold; no new measurement',
        'biological_direction_established':False},None


def project_frame(frame):
    if frame['kind']!='state':return None,'model_frame_is_not_observation'
    parts=[]
    for s in frame['statements']:
        view,error=project_statement(s)
        if view is None:return None,error
        parts.append(view)
    if not parts:return None,'empty_model_frame'
    return {'frame':{**deepcopy(frame),'statements':[p['statement'] for p in parts]},
        'operator':'typed_statistical_models','operator_version':VERSION,'forecast_eligible':True,
        'statements':[{k:v for k,v in p.items() if k!='statement'} for p in parts],
        'reason':'explicit_fitted_direction_and_test_only; full_numeric_parent_retained; no_causal_or_effect_size_prediction'},None
