"""Сигналы неоднозначных участников не заменяют проверку смысла источника."""
from collections import Counter, defaultdict
from copy import deepcopy
import re

from domain.article_maps import fingerprint, require

VERSION = 'native-semantic-participant-audit-1'
GENE_ROLES = {'gene', 'genes'}
SET_ROLES = {'genes', 'targets', 'receptors'}


def audit_participants(maps):
    require(bool(maps) and len({m['article_id'] for m in maps}) == len(maps), 'Explicit distinct maps required')
    flags, coverage, bindings = [], [], []
    total_statements = 0
    for result in maps:
        graph = result['graph']; article = result['article_id']
        require(graph['schema_version'] == 6, 'Participant audit requires schema 6')
        concepts = {c['id']: c for c in graph['concepts']}
        require(len(concepts) == len(graph['concepts']), 'Duplicate native participant')
        source_units = {u['id']: u for u in result['source']['units']}
        knowledge_ids = {k['knowledge_id'] for k in graph['knowledge']}
        require(len(knowledge_ids) == len(graph['knowledge']), 'Duplicate native knowledge')
        usage = defaultdict(list)
        for knowledge in graph['knowledge']:
            coverage.append({'article_id': article, 'knowledge_id': knowledge['knowledge_id'],
                             'knowledge_sha256': fingerprint(knowledge), 'full_parent_retained': True})
            for statement in knowledge['semantic_frame']['statements']:
                total_statements += 1
                for role in statement['roles']:
                    require(bool(role['concept_id']) != bool(role['knowledge_id']), 'Exactly one native participant reference required')
                    if role['knowledge_id'] is not None:
                        require(role['knowledge_id'] in knowledge_ids, 'Unknown native knowledge reference')
                        continue
                    require(role['concept_id'] in concepts, 'Unknown native participant')
                    refs = statement['provenance']['unit_ids']
                    require(bool(refs) and all(uid in source_units for uid in refs), 'Participant evidence missing')
                    entry = {'knowledge_id': knowledge['knowledge_id'], 'statement_id': statement['statement_id'],
                             'role': role['role'], 'source_unit_ids': deepcopy(refs)}
                    usage[role['concept_id']].append(entry)
                    label = concepts[role['concept_id']]['display_text']
                    if role['role'] in SET_ROLES and re.search(r'[,;]|\band\b', label, flags=re.I):
                        flags.append({'article_id': article, 'concept_id': role['concept_id'], 'label': label,
                            'kind': 'participant_set_members_not_explicit', 'locations': [entry],
                            'reason_ru': 'Перечень скрыт в строковом имени участника; принадлежность отдельных элементов не закодирована. Самостоятельное разделение без источниковой проверки запрещено.'})
        for cid, entries in usage.items():
            roles = {e['role'] for e in entries}
            kind = ('gene_protein_identity_needs_review' if roles & GENE_ROLES and 'protein' in roles else
                    'gene_pathway_identity_needs_review' if roles & GENE_ROLES and 'pathway' in roles else None)
            if kind:
                flags.append({'article_id': article, 'concept_id': cid, 'label': concepts[cid]['display_text'],
                    'kind': kind, 'locations': deepcopy(entries),
                    'reason_ru': 'Один родной идентификатор используется для разных семантических ролей. Требуется проверить, не смешаны ли ген, продукт или сигнальный путь; аудит сам не решает тождество.'})
        bindings.append({'article_id': article, 'run_id': result['run_id'], 'graph_sha256': fingerprint(graph),
                         'source_sha256': result['source']['sha256']})
    return {'version': VERSION, 'map_bindings': bindings, 'coverage': coverage, 'canonical_blocks': len(coverage),
        'statement_count': total_statements, 'flags': flags, 'counts': dict(Counter(f['kind'] for f in flags)),
        'model_calls': 0, 'automatic_expansions': 0, 'new_assertions': 0, 'expert_validated': False,
        'semantic_equivalence_established': False, 'scientific_success': False}
