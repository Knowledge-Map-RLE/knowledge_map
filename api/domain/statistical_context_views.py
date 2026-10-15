"""Модельные знаки и области тестов выводятся раздельно, без смены клинического исхода."""
from copy import deepcopy
from domain.comparison_normalization import normalize
from domain.statistical_primitives import number,attributes,roles,direction,statistical_finding

VERSION='audited-statistical-context-views-1'
COEFFICIENT_FIELDS={'evidence presentation','model','analysis n','printed coefficient and ci95',
    'individual p','joint p','joint test scope','adjustment','reference category','source table','estimate','ci95','joint p origin row'}
SLOPE_FIELDS={'evidence presentation','n','proportion','estimate','ci95','p reference','p'}


def project_audited_frame(frame,audit):
    if audit is None:return None,'model_context_not_audited'
    if frame['kind']!='state' or len(frame['statements'])!=len(audit['statements']):return None,'model_context_frame_differs'
    parts=[];transformed=deepcopy(frame)
    for i,(s,context) in enumerate(zip(frame['statements'],audit['statements'])):
        a,r=attributes(s),roles(s)
        if a is None or r is None:return None,'ambiguous_model_fields'
        if s['scope']['study_group'] is None:return None,'model_study_context_missing'
        if s['negated'] or s['scope']['modality'] not in (None,'reported','as reported'):return None,'not_observed_model_result'
        if any(not isinstance(v,str) for v in r.values()):return None,'unresolved_model_roles'
        if normalize(a.get('evidence presentation',{}).get('value'))!='own result':return None,'not_own_result'
        kind=context['kind'];out=transformed['statements'][i]
        constraints=['audited model: '+normalize(context['model']),'effect estimand: '+normalize(context['estimand']),
            'effect unit: '+normalize(context['unit']),'exposure contrast: '+normalize(context['contrast'])]
        if kind=='time_slope':
            if s['predicate']!='estimated cognitive slope' or set(a)!=SLOPE_FIELDS or not {'population','index','outcome','adjustment'}<=set(r):
                return None,'unrecognized_slope_contract'
            if context['model']!='linear regression' or context['unit']!='3MS points/year' or context['threshold'] is not None or context['bounds']:
                return None,'slope_model_or_test_mismatch'
            if normalize(a['estimate']['unit'])!=normalize('3MS points/year') or normalize(a['p reference']['value'])!=normalize(context['reference']):
                return None,'slope_unit_or_reference_mismatch'
            n=number(a['n']['value']);point=number(a['estimate']['value'])
            if point is None or n is None or n<=0 or n!=n.to_integral_value():return None,'invalid_slope_estimate_or_sample'
            out['predicate']='reported fitted within-group time slope direction'
            # Напечатанный p сравнивает группу с референтной, а не наклон с нулём.
            tests={'zero_slope_test':'not reported','between_group_test':'printed p retained in parent; threshold not declared'}
            constraints+=['p-test reference: '+normalize(context['reference']), 'zero-slope test not inferred from between-group p']
        else:
            if s['predicate'] not in {'estimated association','coefficient not reported'} or set(a)-COEFFICIENT_FIELDS or not {'exposure','category','outcome','adjustment'}<=set(r):
                return None,'unrecognized_coefficient_contract'
            required={'model','analysis n','printed coefficient and ci95','individual p','joint p','joint test scope','adjustment','reference category'}
            if not required<=set(a):return None,'missing_coefficient_fields'
            if normalize(a['model']['value'])!=normalize(context['model']) or normalize(a['adjustment']['value'])!=normalize(r['adjustment']):
                return None,'coefficient_model_or_adjustment_mismatch'
            expected_unit='MMSE latent-scale coefficient' if context['model']=='Tobit regression' else 'MMSE points/year'
            if context['unit']!=expected_unit:return None,'coefficient_unit_mismatch'
            if context['model']=='Tobit regression':
                if context['bounds']!=['0','30']:return None,'tobit_bounds_unknown'
                constraints+=['latent Tobit response; observed MMSE is censored at 0 and 30']
            elif context['bounds']:return None,'linear_model_has_unestablished_bounds'
            alpha=number(context['threshold'])
            if alpha is None or not 0<alpha<1:return None,'coefficient_threshold_unknown'
            constraints+=['conditional strict test of printed p < '+str(alpha), 'joint-test scope: '+normalize(a['joint test scope']['value'])]
            n=number(a['analysis n']['value'])
            if n is None or n<=0 or n!=n.to_integral_value():return None,'invalid_model_sample'
            if kind=='reference_coefficient':
                if normalize(a['printed coefficient and ci95']['value'])!='reference' or context['reference'] is None or normalize(context['reference'])!=normalize(r['category']) or 'estimate' in a:
                    return None,'reference_coefficient_not_explicit'
                point=None;fitted='reference_definition_only'
                individual='not reported for reference category'
                out['predicate']='reported model reference category'
            else:
                if 'estimate' not in a or normalize(a['estimate']['unit'])!=normalize(context['unit']):return None,'missing_or_incompatible_estimate'
                point=number(a['estimate']['value'])
                if point is None:return None,'coefficient_not_reported'
                if kind=='category_coefficient':
                    if context['reference'] is None or normalize(a['reference category']['value'])!=normalize(context['reference']) or normalize(r['category'])==normalize(context['reference']):
                        return None,'category_reference_mismatch'
                    constraints+=['reference category: '+normalize(context['reference'])]
                elif kind=='continuous_coefficient':
                    if context['reference'] is not None or normalize(r['category'])!=normalize(r['exposure']):return None,'continuous_exposure_not_established'
                else:return None,'unrecognized_contrast_kind'
                individual=statistical_finding(a['individual p']['value'],str(alpha))
                if individual=='not_established':return None,'individual_test_not_interpreted'
                fitted=direction(point)
                out['predicate']='reported fitted latent response contrast direction' if context['model']=='Tobit regression' else 'reported fitted annual change contrast direction'
            tests={'individual_test':individual,'joint_test':statistical_finding(a['joint p']['value'],str(alpha))}
        if kind=='time_slope':fitted=direction(point)
        out['scope']['conditions']=sorted(set(out['scope']['conditions']+constraints))
        out['attributes']=[{'name':'reported fitted direction','value':fitted,'unit':None},
            *[{'name':k.replace('_',' '),'value':v,'unit':None} for k,v in tests.items()],
            {'name':'interpretation','value':'conditional reported model result; no causal or new empirical assertion','unit':None}]
        out.pop('attribute_types',None)
        parts.append({'point':str(point) if point is not None else None,'direction':fitted,
            'tests':tests,'context':deepcopy(context),'analysis_n':str(n),'biological_causality_asserted':False})
    return {'frame':transformed,'operator':'audited_statistical_context','operator_version':VERSION,
        'forecast_eligible':True,'statements':parts,'model_context_audit':deepcopy(audit),
        'reason':'explicit model contrasts and separate test scopes; full compound numeric parent retained'},None
