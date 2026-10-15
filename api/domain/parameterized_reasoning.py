"""Связанные числовые параметры и проверяемая статистическая интерпретация."""
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
import re

from domain.article_maps import require, fingerprint

VERSION = 'parameterized-statistical-interpretation-1'
CASE_FIELDS = {'case_id','family','source_binding','context','p','alpha','assumptions','premises'}
CONTEXT = {'analysis_id','exposure','outcome','stratum','model','time','conditions'}
ASSUMPTIONS = {'same_analysis','test_identified','declared_threshold','dimensionless','interpretation_basis'}
RULE = {'version':VERSION,'operator':'compare_reported_p_with_declared_alpha',
        'parameters':['p','alpha'],'guards':sorted(ASSUMPTIONS),
        'channel':'post_result_interpretation','status':'verified_numeric_operation',
        'does_not_infer':['effect_size','effect_direction','causality','absence_of_effect','future_effect']}
RULE_ID = fingerprint(RULE)


@dataclass(frozen=True)
class Interval:
    lower: Decimal
    upper: Decimal
    lower_closed: bool = True
    upper_closed: bool = True

    def validate(self):
        require(self.lower.is_finite() and self.upper.is_finite(), 'Finite probability required')
        require(0 <= self.lower <= self.upper <= 1, 'Probability outside [0,1]')
        require(self.lower != self.upper or self.lower_closed and self.upper_closed, 'Empty interval')

    def below(self, alpha):
        return self.upper < alpha or self.upper == alpha and not self.upper_closed

    def not_below(self, alpha):
        return self.lower >= alpha

    def json(self):
        return {'lower':str(self.lower),'upper':str(self.upper),
                'lower_closed':self.lower_closed,'upper_closed':self.upper_closed}


def number(value):
    require(isinstance(value,str) and bool(re.fullmatch(r'(?:0|1)?\.\d+|0|1',value)), 'Explicit decimal probability required')
    try: result=Decimal(value)
    except InvalidOperation: require(False,'Invalid decimal probability')
    require(result.is_finite() and 0<=result<=1,'Probability outside [0,1]')
    return result


def p_interval(raw):
    require(isinstance(raw,dict) and set(raw)=={'expression','precision'},'Exact P representation required')
    require(isinstance(raw['expression'],str),'P expression must be an explicit string')
    match=re.fullmatch(r'\s*(<=|>=|<|>|=)?\s*((?:0|1)?\.\d+|0|1)\s*',raw['expression'])
    require(match is not None,'Unsupported P expression')
    relation=match[1] or '='; value=number(match[2])
    require(raw['precision'] in {'reported_value','nearest_rounding'},'Explicit P precision policy required')
    if relation!='=':
        require(raw['precision']=='reported_value','An inequality cannot be expanded as rounded equality')
        result=Interval(Decimal(0),value,True,relation=='<=') if relation in {'<','<='} else Interval(value,Decimal(1),relation=='>=',True)
    elif raw['precision']=='nearest_rounding':
        # Границы включены консервативно: способ округления на половине шага неизвестен.
        step=Decimal(1).scaleb(value.as_tuple().exponent)/2
        result=Interval(max(Decimal(0),value-step),min(Decimal(1),value+step))
    else: result=Interval(value,value)
    result.validate(); return result


def interpret(case):
    require(isinstance(case,dict) and set(case)==CASE_FIELDS,'Closed statistical case required; outcome labels are forbidden')
    require(all(isinstance(case[k],str) and case[k] for k in ('case_id','family')),'Case identity required')
    binding=case['source_binding']
    require(set(binding)=={'article_id','run_id','source_sha256','map_sha256'},'Exact source binding required')
    require(all(isinstance(binding[k],str) and binding[k] for k in binding),'Empty source binding')
    require(all(re.fullmatch('[a-f0-9]{64}',binding[k]) for k in ('source_sha256','map_sha256')),'Source digest required')
    context=case['context']; assumptions=case['assumptions']
    require(set(context)==CONTEXT and set(assumptions)==ASSUMPTIONS,'Explicit applicability fields required')
    require(isinstance(case['premises'],list) and len(case['premises'])>=2,'P and criterion premises required')
    require(set(case['alpha'])=={'value','relation'},'Exact criterion required')
    require(case['alpha']['relation']=='<','Only explicitly specified strict P<alpha is supported')
    alpha=number(case['alpha']['value']); require(0<alpha<1,'Nontrivial significance criterion required')
    interval=p_interval(case['p'])
    reasons=[name for name in sorted(ASSUMPTIONS-{'interpretation_basis'}) if assumptions[name] is not True]
    if assumptions['interpretation_basis']!='reported_values': reasons.append('unsupported_interpretation_basis')
    for name in sorted(CONTEXT-{'conditions'}):
        if not isinstance(context[name],str) or not context[name].strip(): reasons.append('unknown_context:'+name)
    if not isinstance(context['conditions'],list) or not context['conditions'] or any(not isinstance(x,str) or not x.strip() for x in context['conditions']):
        reasons.append('unknown_context:conditions')
    if reasons: status='blocked'
    elif interval.below(alpha): status='below_threshold'
    elif interval.not_below(alpha): status='not_below_threshold'
    else: status='indeterminate'; reasons.append('reported_precision_crosses_threshold')
    payload={'case_id':case['case_id'],'status':status,'reasons':reasons,'context':context,
             'parameters':{'p':interval.json(),'alpha':str(alpha),'relation':'<'},
             'operator_id':RULE_ID,'operator':RULE,'source_binding':binding,'premises':case['premises'],
             'interpretation_basis':'reported_values','result_available':status in {'below_threshold','not_below_threshold'},
             'scientific_prediction':False,'model_calls':0}
    return {'inference_id':fingerprint(payload),**payload}
