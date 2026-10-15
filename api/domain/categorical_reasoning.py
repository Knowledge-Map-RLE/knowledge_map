"""Категорическая логика: перебор моделей и явные условия существования классов."""
from functools import lru_cache
from itertools import product, combinations
from domain.article_maps import require

VERSION='categorical-model-checking-1'
TERMS={'S':1,'P':2,'M':4}
FIGURES={1:(('M','P'),('S','M')),2:(('P','M'),('S','M')),
         3:(('M','P'),('M','S')),4:(('P','M'),('M','S'))}


def holds(mood,subject,predicate,world):
    members=[region for region in range(8) if world & (1<<region)]
    both=any(region & TERMS[subject] and region & TERMS[predicate] for region in members)
    outside=any(region & TERMS[subject] and not region & TERMS[predicate] for region in members)
    return {'A':not outside,'E':not both,'I':both,'O':outside}[mood]


def check(mood,figure,existence=()):
    require(isinstance(mood,str) and len(mood)==3 and set(mood)<={'A','E','I','O'},'Three categorical quantifiers required')
    require(type(figure) is int and figure in FIGURES,'Unknown syllogism figure')
    require(isinstance(existence,tuple) and set(existence)<=set(TERMS) and len(set(existence))==len(existence),'Explicit distinct existence assumptions required')
    counter=_countermodel(mood,figure,existence)
    return {'valid':counter is None,'countermodel':None if counter is None else list(counter),
            'existence':list(existence),'encoding':'region bits M,P,S; present regions contain witnesses'}


@lru_cache(maxsize=4096)
def _countermodel(mood,figure,existence):
    major,minor=FIGURES[figure]
    for world in range(256):
        if any(not any(world & (1<<r) and r & TERMS[t] for r in range(8)) for t in existence): continue
        if holds(mood[0],*major,world) and holds(mood[1],*minor,world) and not holds(mood[2],'S','P',world):
            return tuple(f'{r:03b}' for r in range(8) if world & (1<<r))
    return None


def catalog():
    result=[]
    for figure in FIGURES:
        for letters in product('AEIO',repeat=3):
            mood=''.join(letters)
            if not check(mood,figure,('S','P','M'))['valid']:continue
            sufficient=[]
            for n in range(4):
                for terms in combinations(('S','P','M'),n):
                    if any(set(x)<=set(terms) for x in sufficient):continue
                    if check(mood,figure,terms)['valid']:sufficient.append(list(terms))
            result.append({'id':mood+str(figure),'mood':mood,'figure':figure,
                           'unconditional':check(mood,figure)['valid'],'minimal_existence_sets':sufficient})
    return result


def apply(mood,figure,premises,existence_evidence):
    require(isinstance(premises,list) and len(premises)==2,'Major and minor premises required')
    contexts=[p.get('context') for p in premises]
    if not all(p.get('relation_kind')=='categorical' and p.get('source_binding') for p in premises):
        return {'status':'blocked','reason':'association_or_unproven_premise_is_not_categorical'}
    if not all(isinstance(c,dict) and set(c)=={'population','time','modality'} and all(isinstance(v,str) and v.strip() for v in c.values()) for c in contexts) or contexts[0]!=contexts[1]:
        return {'status':'blocked','reason':'unknown_or_incompatible_context'}
    if contexts[0]['modality']!='asserted':return {'status':'blocked','reason':'modal_syllogism_not_supported'}
    major,minor=FIGURES.get(figure,(None,None))
    require(major is not None and len(mood)==3,'Valid form required')
    require([(p.get('quantifier'),p.get('subject'),p.get('predicate')) for p in premises]==[(mood[0],*major),(mood[1],*minor)],'Premise terms do not bind the selected syllogism')
    require(isinstance(existence_evidence,dict) and set(existence_evidence)<=set(TERMS),'Explicit class witnesses required')
    valid={t:e for t,e in existence_evidence.items() if isinstance(e,dict) and e.get('source_binding') and e.get('context')==contexts[0]}
    proof=check(mood,figure,tuple(sorted(valid)))
    return {'status':'valid_conditional_deduction' if proof['valid'] else 'not_entailed',
            'proof':proof,'unconditional':check(mood,figure)['valid'],
            'version':VERSION,'existence_evidence':valid,'conclusion':{'quantifier':mood[2],'subject':'S','predicate':'P'} if proof['valid'] else None,
            'scientific_fact_validated':False}
