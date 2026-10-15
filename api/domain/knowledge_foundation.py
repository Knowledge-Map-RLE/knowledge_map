"""Явный фундамент и условные преобразования знаний без модельной генерации."""
from collections import deque
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from domain.article_maps import fingerprint, require
from domain.qualitative_relations import validate_claim, forecast_fold, evaluate_fold

VERSION = 'explicit-foundation-pilot-1'
MODES = ('articles', 'comparison', 'derivation', 'dependencies')
CANONICAL = {'age': 'older_vs_younger', 'sex': 'male_vs_female', 'education': 'less_vs_more'}
OPPOSITE = {'age': 'younger_vs_older', 'sex': 'female_vs_male', 'education': 'more_vs_less'}


def decimal(value):
    require(isinstance(value, str), 'Explicit decimal string required')
    try:
        result = Decimal(value)
    except InvalidOperation:
        require(False, 'Invalid decimal')
    require(result.is_finite(), 'Finite value required')
    return result


def validate_dag(nodes, edges):
    ids = {n['id'] for n in nodes}
    require(len(ids) == len(nodes), 'Duplicate occurrence')
    outgoing = {i: [] for i in ids}; degrees = {i: 0 for i in ids}; seen = set()
    for e in edges:
        require(set(e) == {'source', 'target'}, 'Edges must be untyped')
        a, b = e['source'], e['target']
        require(a in ids and b in ids and a != b, 'Unknown or self reference')
        require((a, b) not in seen, 'Duplicate edge'); seen.add((a, b))
        outgoing[a].append(b); degrees[b] += 1
    pending = deque(sorted(i for i in ids if not degrees[i])); ranks = dict.fromkeys(ids, 0); visited = 0
    while pending:
        a = pending.popleft(); visited += 1
        for b in outgoing[a]:
            ranks[b] = max(ranks[b], ranks[a]+1); degrees[b] -= 1
            if degrees[b] == 0: pending.append(b)
    require(visited == len(ids), 'Visible cycle')
    return ranks


def validate_foundation(f):
    require(set(f) == {'version', 'sources', 'knowledge', 'occurrences', 'edges', 'transitions', 'metadata'}, 'Foundation contract differs')
    require(f['version'] == VERSION and f['metadata']['model_calls'] == 0, 'Foundation version differs')
    knowledge = {b['knowledge_id']: b for b in f['knowledge']}
    require(len(knowledge) == len(f['knowledge']), 'Duplicate foundation knowledge')
    for b in knowledge.values():
        require(set(b) == {'knowledge_id', 'text', 'text_ru', 'kind', 'knowledge_kind', 'frame', 'provenance'}, 'Foundation block fields differ')
        require(b['kind'] == 'state' and b['knowledge_kind'] in {'definition', 'rule', 'limitation'}, 'Invalid foundation kind')
        require(b['text'] and b['text_ru'] and b['provenance'], 'Foundation labels or sources missing')
        require(all(p in f['sources'] for p in b['provenance']), 'Unknown foundation source')
        require(b['frame']['predicate'] == b['knowledge_id'] and isinstance(b['frame']['conditions'], list), 'Rule frame differs')
        require(all(r in knowledge for r in b['frame']['participants']), 'Unknown semantic participant')
    for o in f['occurrences']:
        require(set(o) == {'id', 'knowledge_id'} and o['knowledge_id'] in knowledge, 'Invalid foundation occurrence')
    ranks = validate_dag(f['occurrences'], f['edges'])
    transitions = {(t['source'], t['target']): t for t in f['transitions']}
    require(len(transitions) == len(f['transitions']) and set(transitions) == {(e['source'], e['target']) for e in f['edges']}, 'Unjustified foundation transition')
    require(all(t['reason'] and t['joint_group'] for t in transitions.values()), 'Transition reason missing')
    return ranks


def rules(f, identifiers):
    available = {b['knowledge_id'] for b in f['knowledge']}
    require(set(identifiers) <= available, 'Required foundation rule missing')


def invert_ratio(value, interval=None):
    q = decimal(value); require(q > 0, 'Positive ratio required')
    with localcontext() as context:
        context.prec = 28
        estimate = str(Decimal(1)/q)
        if interval is None: return estimate, None
        require(isinstance(interval, list) and len(interval) == 2, 'Two interval bounds required')
        low, high = map(decimal, interval)
        require(0 < low <= q <= high, 'Ratio interval differs')
        return estimate, [str(Decimal(1)/high), str(Decimal(1)/low)]


def convert_measure(value, source_measure, source_scale, target_measure, target_scale, f):
    rules(f, ['positive_scale', 'person_time_rate', 'incidence_proportion'])
    require(source_measure == target_measure and source_measure in {'incidence_rate', 'incidence_proportion'}, 'Different measure requires a model; conversion blocked')
    a, b, v = decimal(source_scale), decimal(target_scale), decimal(value)
    require(a > 0 and b > 0 and v >= 0, 'Invalid scale')
    require(source_measure != 'incidence_proportion' or v <= a, 'Proportion out of bounds')
    return str(v*b/a)


def compose_universal(first, second, f):
    """Только универсальная включённость в совпадающем явном контексте."""
    rules(f, ['universal_chain', 'no_existential_import'])
    for premise in (first, second):
        require(set(premise) == {'subject', 'object', 'predicate', 'quantifier', 'context'}, 'Logic premise differs')
        require(premise['predicate'] == 'subset' and premise['quantifier'] == 'all', 'Only universal subset premises allowed')
    require(first['object'] == second['subject'], 'Middle term differs')
    require(first['context'] is not None and first['context'] == second['context'], 'Unknown or different logic context')
    return {**first, 'object': second['object'], 'existence_asserted': False}


def normalize(native, foundation, mode):
    require(mode in MODES and set(native) == {'claim', 'basis'}, 'Native claim fields differ')
    c = deepcopy(native['claim']); validate_claim(c); b = native['basis']
    require(set(b) == {'native_key', 'conceptual_contrast', 'ratio', 'interval', 'linear_increment', 'same_model_context', 'evidence_ids'}, 'Native basis fields differ')
    require(c['contrast'] == b['native_key'] and b['evidence_ids'] == c['provenance'], 'Native contrast or proof differs')
    require(b['conceptual_contrast'] in {CANONICAL[c['factor']], OPPOSITE[c['factor']]}, 'Unknown conceptual contrast')
    if mode == 'articles': return c, None
    rules(foundation, ['contrast_identity', 'unknown_context', 'nondetection', 'association_not_causality'])
    c['contrast'] = b['conceptual_contrast']
    if mode == 'comparison' or c['contrast'] == CANONICAL[c['factor']]: return c, None
    rules(foundation, ['positive_ratio', 'reciprocal_ratio'])
    require(b['same_model_context'] is True, 'Unknown model context; reversal blocked')
    ratio = b['ratio']
    if isinstance(ratio, dict):
        require(set(ratio) == {'numerator', 'denominator'}, 'Explicit paired quantities required')
        numerator, denominator = decimal(ratio['numerator']), decimal(ratio['denominator'])
        require(numerator > 0 and denominator > 0, 'Positive paired quantities required')
        ratio = str(numerator/denominator)
    require(isinstance(ratio, str), 'Explicit native ratio required for reversal')
    used = ['contrast_identity', 'positive_ratio', 'reciprocal_ratio', 'nondetection', 'association_not_causality']
    if b['linear_increment'] is not None:
        require(b['linear_increment'] == {'step': '1', 'unit': 'year_of_schooling', 'model': 'fitted_log_linear'}, 'Unspecified incremental model')
        rules(foundation, ['negative_model_increment']); used.append('negative_model_increment')
    value, interval = invert_ratio(ratio, b['interval']); q = decimal(ratio)
    native_direction = 'higher' if q > 1 else 'lower' if q < 1 else 'equal'
    require(c['result']['direction'] == native_direction, 'Ratio contradicts native direction')
    reversed_direction = 'lower' if q > 1 else 'higher' if q < 1 else 'equal'
    c['contrast'] = CANONICAL[c['factor']]; c['result']['direction'] = reversed_direction
    c['semantic_frame']['statements'][0]['value'] = reversed_direction
    proof = {'id': fingerprint({'claim': native, 'rules': used}), 'source_claim': native['claim']['id'],
             'rules': used, 'premises': {'claim_sha256': fingerprint(native['claim']), 'basis_sha256': fingerprint(b),
                                       'foundation_sha256': fingerprint(foundation)},
             'native_ratio': ratio, 'derived_ratio': value, 'derived_interval': interval,
             'direction': reversed_direction, 'statistical_finding': c['result']['statistical_finding'],
             'status': 'conditional_mathematical_consequence', 'derived_from_rounded_estimate': True,
             'new_empirical_knowledge': False, 'causal': False, 'context': c['context'], 'provenance': c['provenance']}
    if mode == 'dependencies': proof['graph'] = proof_graph(native, foundation, proof)
    return c, proof


def proof_graph(native, foundation, proof):
    nodes = [{'id': 'source:'+native['claim']['id'], 'knowledge_id': native['claim']['knowledge_id'], 'role': 'source'}]
    nodes += [{'id': 'rule:'+r, 'knowledge_id': r, 'role': 'foundation'} for r in proof['rules']]
    nodes += [{'id': 'condition:'+native['claim']['id'], 'knowledge_id': 'condition:'+proof['id'], 'role': 'condition'},
              {'id': 'result:'+proof['id'], 'knowledge_id': 'derived:'+proof['id'], 'role': 'result'}]
    target = nodes[-1]['id']; edges = [{'source': n['id'], 'target': target} for n in nodes[:-1]]
    graph = {'nodes': nodes, 'edges': edges, 'joint_premises': [n['id'] for n in nodes[:-1]],
             'condition': {'same_model_context': native['basis']['same_model_context'], 'linear_increment': native['basis']['linear_increment']},
             'ranks': validate_dag(nodes, edges)}
    validate_proof_graph(native, foundation, proof, graph)
    return graph


def validate_proof_graph(native, foundation, proof, graph):
    require(proof['premises'] == {'claim_sha256': fingerprint(native['claim']), 'basis_sha256': fingerprint(native['basis']), 'foundation_sha256': fingerprint(foundation)}, 'Proof binding changed')
    required = {'source:'+native['claim']['id'], 'condition:'+native['claim']['id']} | {'rule:'+r for r in proof['rules']}
    target = 'result:'+proof['id']
    require({n['id'] for n in graph['nodes']} == required | {target}, 'Proof nodes changed')
    require(set(graph['joint_premises']) == required and len(graph['joint_premises']) == len(required), 'Joint premises changed')
    require({(e['source'], e['target']) for e in graph['edges']} == {(n, target) for n in required}, 'Missing or spurious proof dependency')
    require(graph['condition'] == {'same_model_context': native['basis']['same_model_context'], 'linear_increment': native['basis']['linear_increment']}, 'Model condition changed')
    validate_dag(graph['nodes'], graph['edges'])


def forecast_native_fold(fold, foundation):
    require(set(fold) == {'fold_id', 'withheld_family', 'training'}, 'Native fold fields differ')
    validate_foundation(foundation); modes = {}; proofs = {}
    for mode in MODES:
        projected = []; proofs[mode] = []
        for native in fold['training']:
            c, p = normalize(native, foundation, mode); projected.append(c)
            if p: proofs[mode].append(p)
        modes[mode] = forecast_fold({**fold, 'training': projected})
    return {'fold_id': fold['fold_id'], 'withheld_family': fold['withheld_family'], 'modes': modes, 'proofs': proofs}


def evaluate_native_fold(fold, controls, foundation):
    rows = {}
    for mode in MODES:
        projected = [normalize(n, foundation, mode)[0] for n in controls]
        rows[mode] = evaluate_fold(fold['modes'][mode], projected)['modes']['semantic']
    return {'fold_id': fold['fold_id'], 'modes': rows}
