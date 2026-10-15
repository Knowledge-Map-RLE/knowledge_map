"""Диагностика устойчивости порядка при изменении определения; не предиктор."""
from decimal import Decimal, InvalidOperation
from itertools import combinations

from domain.article_maps import require

VERSION = 'within-cohort-definition-order-1'


def number(value):
    require(isinstance(value, str), 'Decimal must be an explicit string')
    try:
        result = Decimal(value)
    except InvalidOperation:
        require(False, 'Invalid decimal')
    require(result.is_finite(), 'Nonfinite value')
    return result


def validate_series(series):
    require(set(series)=={'id','source_id','cohort','definition','context','cells','provenance'}, 'Unexpected series fields')
    require(all(isinstance(series[k],str) and series[k] for k in ('id','source_id','cohort','definition')), 'Series identity missing')
    require(isinstance(series['context'],dict) and series['context'], 'Context missing')
    require(series['context'].get('measure')=='incidence_rate' and series['context'].get('unit')=='per1000personyears', 'Incidence unit required')
    require(series['context'].get('age_basis') in {'baseline','attained'}, 'Explicit age basis required')
    require(isinstance(series['provenance'],list) and series['provenance'], 'Series provenance missing')
    require(isinstance(series['cells'],list) and len(series['cells'])>=2, 'At least two age cells required')
    prior = None
    for cell in series['cells']:
        require(set(cell)=={'age','value','interval','cases','person_years','evidence_id'}, 'Unexpected rate fields')
        age = cell['age']
        require(isinstance(age,list) and len(age)==2 and type(age[0]) is int and age[0]>=0, 'Invalid age bounds')
        require(age[1] is None or type(age[1]) is int and age[1]>=age[0], 'Invalid age end')
        if prior is not None:
            require(prior[1] is not None and age[0]>prior[1], 'Overlapping or unordered age cells')
        prior = age
        require(type(cell['cases']) is int and cell['cases']>=0, 'Invalid cases')
        value, py = number(cell['value']), number(cell['person_years'])
        require(value>=0 and py>0, 'Nonpositive denominator or negative rate')
        interval = cell['interval']
        require(isinstance(interval,list) and len(interval)==2, 'Invalid interval')
        low, high = map(number, interval)
        require(0<=low<=value<=high, 'Interval does not contain estimate')
        # Ставки и знаменатели округлены в публикации; допускается половина десятичного разряда.
        require(abs(value-Decimal(cell['cases'])*1000/py)<=Decimal('0.051'), 'Rate differs from cases/person-years')
        require(isinstance(cell['evidence_id'],str) and cell['evidence_id'], 'Rate provenance missing')


def order(first, second):
    a,b = number(first['value']),number(second['value'])
    return 'higher' if b>a else 'lower' if b<a else 'equal'


def compare_definitions(first, second, varied_fields):
    """Сравнение только внутри одной публикации и явно указанных изменений контекста."""
    validate_series(first);validate_series(second)
    require(first['id']!=second['id'], 'Repeated definition')
    require(first['source_id']==second['source_id'] and first['cohort']==second['cohort'], 'Within-source cohort required')
    require(set(first['context'])==set(second['context']), 'Context keys differ')
    require(all(value is not None for value in list(first['context'].values())+list(second['context'].values())), 'Unknown context cannot establish robustness')
    require(isinstance(varied_fields,list) and varied_fields and len(set(varied_fields))==len(varied_fields), 'Explicit varied fields required')
    different = sorted(k for k in first['context'] if first['context'][k]!=second['context'][k])
    require(different==sorted(varied_fields), 'Unregistered context change')
    require(not set(varied_fields)&{'age_basis','measure','unit','population','residence','sex','estimand'}, 'Noncomparable task scope')
    require([c['age'] for c in first['cells']]==[c['age'] for c in second['cells']], 'Different age boundaries')
    rows = []
    for i,j in combinations(range(len(first['cells'])),2):
        one,two = order(first['cells'][i],first['cells'][j]),order(second['cells'][i],second['cells'][j])
        rows.append({'ages':[first['cells'][i]['age'],first['cells'][j]['age']],
                     'adjacent':j==i+1,'orders':{first['id']:one,second['id']:two},
                     'point_order_preserved':one==two,
                     'evidence_ids':[first['cells'][i]['evidence_id'],first['cells'][j]['evidence_id'],
                                     second['cells'][i]['evidence_id'],second['cells'][j]['evidence_id']]})
    return {'version':VERSION,'source_id':first['source_id'],'cohort':first['cohort'],
            'definitions':[first['id'],second['id']],'varied_fields':varied_fields,'rows':rows,
            'independent_cohorts':1,'bridge_activated':False,'equivalence_asserted':False,
            'prediction':False,'statistical_significance_tested':False}


def audit_definition_changes(series, comparisons):
    require(len({s['id'] for s in series})==len(series), 'Duplicate definition identifier')
    by_id = {s['id']:s for s in series}
    for s in series:validate_series(s)
    seen = set();results = []
    for c in comparisons:
        require(set(c)=={'id','first','second','varied_fields'}, 'Unexpected comparison fields')
        require(c['id'] not in seen and c['first'] in by_id and c['second'] in by_id, 'Unknown or duplicate comparison')
        seen.add(c['id'])
        results.append({'id':c['id'],**compare_definitions(by_id[c['first']],by_id[c['second']],c['varied_fields'])})
    return {'version':VERSION,'comparisons':results,'cohorts':sorted({s['cohort'] for s in series}),
            'bridge_activated':False,'new_scientific_predictions':0,'expert_validated':False}
