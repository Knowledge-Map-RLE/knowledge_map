"""Проверяет первичные ставки и ограничения их переноса между исследованиями."""
from decimal import Decimal

from domain.article_maps import require
from domain.cohort_transfer import band

VERSION = 'primary-pdf-rate-audit-1'
SEMANTIC_FIELDS = ('phenotype', 'age_basis', 'riskset', 'criteria', 'threshold_sd',
                   'norms', 'estimand', 'followup', 'country')


def normalize_rate(rate):
    require(set(rate) == {'id','source_id','endpoint','age','value','interval',
                         'per_person_years','selection','phenotype','estimand'}, 'Invalid primary rate fields')
    require(rate['endpoint'] in {'MCI','aMCI','naMCI'}, 'Unknown primary outcome')
    require(rate['per_person_years'] in (100,1000), 'Unknown person-time scale')
    require(rate['selection'] in ('repair','additional','alternative'), 'Unknown rate selection')
    band(rate['age'])
    require(len(rate['interval'])==2, 'Missing primary rate interval')
    require(all(isinstance(v,str) for v in [rate['value'],*rate['interval']]), 'Decimal strings required')
    values=[Decimal(v) for v in [rate['value'],*rate['interval']]]
    require(all(v.is_finite() for v in values), 'Nonfinite rate')
    require(0 <= values[1] <= values[0] <= values[2], 'Primary rate outside interval')
    scale=Decimal(1000)/rate['per_person_years']
    result=[format(v*scale,'f') for v in values]
    return {'value':result[0], 'interval':result[1:], 'unit':'per1000personyears'}


def transfer_barriers(left, right):
    """Совпадение общих обозначений не подтверждает одинаковый клинический смысл."""
    barriers={}
    for field in SEMANTIC_FIELDS:
        a,b=left.get(field),right.get(field)
        if a in (None,'unspecified','not_applicable') or b in (None,'unspecified','not_applicable'):
            barriers[field]='unknown'
        elif a != b:
            barriers[field]='different'
    return barriers


def audit_review(rates, legacy, quarantined):
    selected={r['id']:r for r in rates if r['selection']=='repair'}
    require(len(selected)==sum(r['selection']=='repair' for r in rates), 'Duplicate primary rate')
    require(set(selected).isdisjoint(quarantined), 'Quarantined rate entered training')
    require(set(selected)|set(quarantined)==set(legacy), 'Repair changed registered cell composition')
    rows=[]
    for key,old in sorted(legacy.items()):
        if key in quarantined:
            rows.append({'id':key,'status':'quarantined','review':old,'primary':None,'changes':['unverified_primary_incidence']})
            continue
        primary=selected[key];n=normalize_rate(primary);changes=[]
        if Decimal(old['value'])!=Decimal(n['value']):changes.append('point_estimate')
        if list(map(Decimal,old['interval']))!=list(map(Decimal,n['interval'])):changes.append('confidence_interval')
        if old['age']!=primary['age']:changes.append('age_bounds')
        if primary['source_id']=='manly2008':changes.append('phenotype_label')
        rows.append({'id':key,'status':'corrected' if changes else 'numerically_confirmed',
                     'review':old,'primary':primary,'normalized':n,'changes':changes})
    return {'rows':rows,'old_cells':len(legacy),'primary_confirmed_cells':len(selected),
            'quarantined_cells':len(quarantined),
            'change_counts':{k:sum(k in r['changes'] for r in rows) for k in
               ('point_estimate','confidence_interval','age_bounds','phenotype_label')},
            'expert_validated':False}
