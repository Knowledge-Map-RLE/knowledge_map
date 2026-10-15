"""Полный корпус проверяется на прежний доступ; цитирование не является эквивалентностью."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import re

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.forecast_temporal_scope import compare_temporal, infer_assessed_existence

VERSION = 'frozen-forecast-claim-qualification-3'


def citation_occurrences(maps, doi):
    require(isinstance(doi, str) and re.fullmatch(r'10\.\d{4,9}/[^\s]+', doi), 'Explicit external DOI required')
    rows = []
    for m in maps:
        source = m['source']; text = source['text']
        require(sha256(text.encode()).hexdigest() == source['sha256'], 'Novelty corpus source differs')
        for match in re.finditer(re.escape(doi), text, re.IGNORECASE):
            # Подстрока другого DOI не является установленной библиографической ссылкой.
            if match.start() and text[match.start() - 1].isalnum(): continue
            trailing = text[match.end():match.end() + 1]
            if trailing and trailing not in ' \n\r\t).,;]': continue
            if trailing in '.,;' and text[match.end() + 1:match.end() + 2].isalnum(): continue
            rows.append({'article_id': m['article_id'], 'run_id': m['run_id'], 'source_sha256': source['sha256'],
                'start': match.start(), 'end': match.end(), 'text': match.group(),
                'sha256': sha256(match.group().encode()).hexdigest(),
                'section': 'references' if match.start() >= source['content_end'] else 'body',
                'fact_equivalence': False})
    return rows


def qualify(frozen, maps, audit):
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['model_calls'] == 0
            and audit['expert_validated'] is False and audit['forecast_sha256'] == fingerprint(frozen), 'Qualification binding differs')
    require(len(maps) == len({m['article_id'] for m in maps}) == frozen['coverage']['sources'], 'Complete qualification corpus required')
    require([fingerprint(m) for m in maps] == audit['map_hashes'], 'Qualification maps changed')
    inventory = []; total_statements = 0
    for m in maps:
        for k in normalize_map(m):
            total_statements += len(k['statements'])
            inventory.append({'article_id': m['article_id'], 'run_id': m['run_id'], 'knowledge_id': k['id'],
                'statement_count': len(k['statements']), 'unknown_context': any(s['unknown_context'] for s in k['statements']),
                'semantic_sha256': fingerprint({'kind': k['kind'], 'action_status': k['action_status'],
                    'logic': k['logic'], 'statements': k['statements']}),
                'temporal_contexts': [s['scope']['time'] for s in k['statements']]})
    citations = citation_occurrences(maps, audit['external_doi'])
    candidates = {c['id']: c for folds in frozen['modes'].values() for f in folds for c in f['predictions']}
    annotations = {r['prediction_id']: r for r in audit['candidates']}
    require(len(annotations) == len(audit['candidates']) and set(annotations) == set(candidates), 'Every frozen candidate must be qualified')
    map_index = {m['article_id']: m for m in maps}; rows, source_consequences = [], []
    for cid, candidate in sorted(candidates.items()):
        annotation = annotations[cid]
        require(set(annotation) == {'prediction_id', 'known_pattern_evidence', 'outcome_temporal_observations', 'reason_ru'},
                'Unsupported qualification annotation')
        require(annotation['reason_ru'], 'Qualification decision requires a reason')
        known = annotation['known_pattern_evidence']
        for e in known:
            require(set(e) == {'article_id', 'run_id', 'source_sha256', 'unit_id', 'start', 'end', 'text', 'sha256',
                              'relation', 'license_kind', 'intervention_alias'}, 'Known-pattern evidence fields differ')
            require(e['article_id'] in map_index and e['relation'] == 'coarse_direction_already_described', 'Invalid known-pattern claim')
            alias = e['intervention_alias']
            require(e['license_kind'] == 'explicit_therapeutic_activity_eae' and isinstance(alias, str) and len(alias) >= 3,
                    'Known direction requires a registered source interpretation')
            token = re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', re.IGNORECASE)
            require(token.search(e['text']) and token.search(candidate['head']['participants']['intervention'])
                    and 'demonstrated therapeutic activity in the EAE model' in e['text']
                    and candidate['head']['qualitative_direction'] == 'lower_clinical_burden'
                    and candidate['head']['outcome_class'] == 'clinical_eae_burden'
                    and candidate['receiver']['features']['disease_model'] == 'mog35_55_induced_eae',
                    'Source quote does not license this coarse intervention-outcome pattern')
            m = map_index[e['article_id']]; source = m['source']; unit = next((u for u in source['units'] if u['id'] == e['unit_id']), None)
            require(m['run_id'] == e['run_id'] and source['sha256'] == e['source_sha256'] and unit is not None
                    and unit['start'] <= e['start'] < e['end'] <= unit['end'] <= source['content_end']
                    and source['text'][e['start']:e['end']] == e['text']
                    and sha256(e['text'].encode()).hexdigest() == e['sha256'], 'Known-pattern source quote differs')
        direction = {'lower_clinical_burden': 'lower', 'higher_clinical_burden': 'higher'}.get(candidate['head']['qualitative_direction'])
        require(direction is not None, 'Typed temporal outcome direction required')
        # Временной контракт должен существовать в самом неизменяемом прогнозе.
        temporal = compare_temporal(candidate['head'].get('temporal_scope'), annotation['outcome_temporal_observations'], direction)
        # Этот канал читает исходы и выводит следствие источника отдельно от старого прогноза.
        derived = infer_assessed_existence(candidate['receiver'], annotation['outcome_temporal_observations'], direction)
        source_consequences.extend({'receiver_id': candidate['receiver_id'], **c} for c in derived['consequences'])
        rows.append({'prediction_id': cid, 'receiver_id': candidate['receiver_id'],
            'temporal': temporal, 'novelty_status': 'known_coarse_pattern' if known else 'not_established',
            'known_pattern_evidence': deepcopy(known), 'full_fact_equivalence': False,
            'external_source_previously_cited': bool(citations), 'independent_blind_validation': False,
            'new_scientific_knowledge_confirmed': False, 'reason_ru': annotation['reason_ru']})
    return {'version': VERSION, 'forecast_sha256': fingerprint(frozen), 'audit_sha256': fingerprint(audit),
        'inventory': inventory, 'canonical_blocks': len(inventory), 'semantic_statements': total_statements,
        'citation_occurrences': citations, 'candidates': rows, 'source_consequences': source_consequences,
        'status_counts': dict(Counter(r['novelty_status'] for r in rows)),
        'model_calls': 0, 'graph_advantage_demonstrated': False, 'new_scientific_knowledge_confirmed': False,
        'policy_ru': 'Ссылка означает прежний доступ к источнику, а не тождество утверждений. '
            'Отсутствие совпавшего фрагмента не доказывает новизну. Старое заключение не получает '
            'временные условия из уже прочитанного ответа; новый прогноз требует собственного контракта.'}
