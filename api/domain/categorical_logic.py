"""Категорические выводы проверяются моделями классов, без скрытого существования."""
from functools import lru_cache
from itertools import combinations, product

from domain.article_maps import fingerprint, require

VERSION = 'categorical-model-entailment-1'
FORMS = ('A', 'E', 'I', 'O')
MAX_TERMS = 3
MAX_PREMISES = 3


def validate(proposition):
    require(isinstance(proposition, dict) and set(proposition) == {'form', 'subject', 'object', 'scope'},
            'Exact categorical proposition required')
    require(proposition['form'] in FORMS, 'Unknown categorical form')
    require(all(isinstance(proposition[k], str) and proposition[k].strip() for k in ('subject', 'object')),
            'Explicit class terms required')
    require(isinstance(proposition['scope'], dict) and bool(proposition['scope']), 'Explicit categorical scope required')
    require(proposition['scope'].get('unknown_context') is not True, 'Unknown categorical context')
    scope = proposition['scope']
    if set(scope) == {'interpretation'}:
        require(isinstance(scope['interpretation'], str) and bool(scope['interpretation'].strip()), 'Abstract interpretation missing')
    else:
        require(set(scope) == {'study_group', 'time', 'conditions', 'modality'}, 'Typed categorical scope required')
        require(scope['modality'] is None and all(scope[k] is None or isinstance(scope[k], str) and scope[k].strip()
                                                for k in ('study_group', 'time')), 'Categorical modality or scope is unknown')
        require(isinstance(scope['conditions'], list) and all(isinstance(v, str) and v.strip() for v in scope['conditions']),
                'Explicit categorical conditions required')
        require(scope['study_group'] is not None or scope['time'] is not None or scope['conditions'], 'Unknown categorical scope')


@lru_cache(maxsize=256)
def worlds(terms):
    # Мир задаёт непустоту каждой из восьми областей трёх классов.
    # Размер области не нужен для A/E/I/O; пустой универсум допускается.
    require(1 <= len(terms) <= MAX_TERMS and len(set(terms)) == len(terms), 'Categorical term budget exceeded')
    count = 1 << len(terms)
    result = []
    for occupied in range(1 << count):
        classes = tuple(sum(1 << region for region in range(count)
                            if occupied & (1 << region) and region & (1 << index))
                        for index in range(len(terms)))
        result.append(classes)
    return tuple(result)


def holds(form, subject, object_):
    if form == 'A': return subject & ~object_ == 0
    if form == 'E': return subject & object_ == 0
    if form == 'I': return subject & object_ != 0
    return subject & ~object_ != 0


@lru_cache(maxsize=2048)
def truth_mask(terms, form, subject, object_):
    a, b = terms.index(subject), terms.index(object_)
    return sum(1 << index for index, world in enumerate(worlds(terms)) if holds(form, world[a], world[b]))


def check(premises, conclusion, existence=()):
    require(1 <= len(premises) <= MAX_PREMISES, 'One to three categorical premises required')
    for proposition in [*premises, conclusion]: validate(proposition)
    require(all(p['scope'] == conclusion['scope'] for p in premises), 'Categorical scopes differ')
    terms = tuple(sorted({p[k] for p in [*premises, conclusion] for k in ('subject', 'object')}))
    require(len(terms) <= MAX_TERMS, 'Categorical term budget exceeded')
    require(len(existence) == len(set(existence)) and set(existence) <= set(terms), 'Unknown or repeated existence condition')
    models = worlds(terms)
    satisfying = (1 << len(models)) - 1
    for p in premises: satisfying &= truth_mask(terms, p['form'], p['subject'], p['object'])
    for term in existence: satisfying &= truth_mask(terms, 'I', term, term)
    counter = satisfying & ~truth_mask(terms, conclusion['form'], conclusion['subject'], conclusion['object'])
    counterexample = None
    if counter:
        index = (counter & -counter).bit_length() - 1
        world = models[index]
        counterexample = {'nonempty_regions': [
            {'inside': [term for j, term in enumerate(terms) if region & (1 << j)],
             'outside': [term for j, term in enumerate(terms) if not region & (1 << j)]}
            for region in range(1 << len(terms)) if any(c & (1 << region) for c in world)]}
        # Область вне всех классов не отражается в их битовых множествах и не нужна контрпримеру.
    result = {'version': VERSION, 'premises': premises, 'conclusion': conclusion,
              'existence_conditions': list(existence), 'terms': list(terms),
              'satisfying_models': satisfying.bit_count(), 'countermodels': counter.bit_count(),
              'entailed': bool(satisfying) and not counter,
              'premises_consistent': bool(satisfying), 'counterexample': counterexample,
              'existential_import': False, 'new_empirical_measurement': False,
              'policy': 'A and E do not assert existence; I and O do. Inconsistent premises do not license publication.'}
    result['id'] = fingerprint(result)
    return result


def census():
    scope = {'interpretation': 'abstract classes; existence never presumed'}
    figures = {1: (('M', 'P'), ('S', 'M')), 2: (('P', 'M'), ('S', 'M')),
               3: (('M', 'P'), ('M', 'S')), 4: (('P', 'M'), ('M', 'S'))}
    result = []
    for figure, axes in figures.items():
        for major, minor, conclusion in product(FORMS, repeat=3):
            premises = [{'form': form, 'subject': subject, 'object': object_, 'scope': scope}
                        for form, (subject, object_) in zip((major, minor), axes)]
            head = {'form': conclusion, 'subject': 'S', 'object': 'P', 'scope': scope}
            proof = check(premises, head)
            minimal = []
            if not proof['entailed']:
                for count in range(1, 4):
                    for exists in combinations(('S', 'M', 'P'), count):
                        if any(set(prior) <= set(exists) for prior in minimal): continue
                        conditional = check(premises, head, exists)
                        if conditional['entailed']: minimal.append(list(exists))
            result.append({'figure': figure, 'mood': major + minor + conclusion,
                           'unconditional': proof['entailed'], 'minimal_existence_conditions': minimal,
                           'counterexample': proof['counterexample']})
    return {'version': VERSION, 'moods_tested': len(result),
            'unconditional': sum(r['unconditional'] for r in result),
            'conditional_only': sum(bool(r['minimal_existence_conditions']) for r in result),
            'rows': result, 'policy': 'Conditional moods are never licensed without their separately established existence premises.'}
