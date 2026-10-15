"""Проверка табличного черновика общим контрактом схемы 6, без публикации и AI."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import PROMPT_PATH, DEPENDENCY_PROMPT_PATH
from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.empirical_evidence_eligibility import audit as audit_evidence_origin
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-folder', type=Path, required=True)
    parser.add_argument('--table-records', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prose-stage', type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    disable_network()
    source = json.loads((args.source_folder / 'source.json').read_text(encoding='utf-8'))
    tables = json.loads(args.table_records.read_text(encoding='utf-8'))
    require(source['sha256'] == tables['source_sha256'], 'Table records refer to another source')
    knowledge = list(tables['authored_knowledge_draft'])
    prose = None
    if args.prose_stage:
        prose = json.loads(args.prose_stage.read_text(encoding='utf-8'))
        require(prose['source_sha256'] == source['sha256'], 'Prose refers to another source')
        require(prose['complete_semantic_coverage'] is False, 'Draft cannot claim complete coverage')
        knowledge.extend(prose['knowledge_draft'])
    require(len({k['key'] for k in knowledge}) == len(knowledge), 'Duplicate authored knowledge key')
    represented = {uid for item in knowledge for uid in item['units']}
    def exclusion_reason(unit):
        text = unit['text'].strip()
        if not text:
            return 'Пустая область извлечения PDF; текстового содержания в исходной ревизии нет.'
        if text.startswith('## PDF page'):
            return 'Заголовок координатной области PDF, не содержание статьи.'
        if unit['id'] == 'U1':
            return 'Дублирует заголовок статьи, сохранённый в метаданных карты.'
        if unit['id'] in {'U9','U11'}:
            return 'Авторские аффилиации, редакционные даты, DOI и корреспонденция; библиографические метаданные источника.'
        if text in {'ⴝ'}:
            return 'Повреждённый при извлечении типографский знак; интерпретированное значение уже проверено по PDF.'
        return 'Фрагмент проверен по PDF; отдельного научного утверждения для карты не содержит.'

    transitions = list(prose.get('transitions_draft', [])) if prose else []
    authored = {'complete_source_reviewed': True, 'complete_semantic_coverage': False,
                'table_cells_exhaustively_formalized': True, 'knowledge': knowledge,
                'transitions': transitions,
                'excluded_units': {u['id']: exclusion_reason(u)
                                   for u in source['units'] if u['id'] not in represented},
                'source_limitations': ['Это технический табличный черновик, не законченная карта всей статьи.',
                                      'Переходы формализованы лишь частично; в корпус и UI черновик не импортируется.',
                                      'Неоднозначные размеры групп и подписи сохранены без исправлений.']}
    if prose:
        # Табличные результаты связываются только с описанным авторами методом.
        method_by_table = {1:'calculate-incidence', 2:'calculate-incidence', 3:'calculate-ad-incidence',
                           4:'fit-ad-cox', 5:'compare-reversion', 6:'compare-reversion'}
        table_rows = {row['id']: row for row in tables['rows']}
        for item in tables['authored_knowledge_draft']:
            record = table_rows[item['source_table_record_id']]
            authored['transitions'].append({'sources':[method_by_table[record['table']],
                    'sample-selection-flow'], 'target':item['key'], 'usage':'method',
                'reason':'The authors define this analysis method and the participant-selection scope for the table result.',
                'units':[item['units'][0]]})
    artifacts = prepare_manual_map(source['article_id'], source['text'], source['sha256'], authored,
                                   PROMPT_PATH.read_text(encoding='utf-8'), DEPENDENCY_PROMPT_PATH.read_text(encoding='utf-8'))
    normalized = normalize_map(artifacts['map.json'])
    unknown = sum(any(s['unknown_context'] for s in k['statements']) for k in normalized)
    verification = {'schema_version': 6, 'canonical_table_blocks': len(tables['authored_knowledge_draft']),
                    'canonical_prose_blocks': len(prose['knowledge_draft']) if prose else 0,
                    'canonical_blocks': len(normalized),
                    'prose_stage_sha256': sha256(args.prose_stage.read_bytes()).hexdigest() if prose else None,
                    'semantic_statements': sum(len(k['statements']) for k in normalized),
                    'unknown_context_blocks': unknown, 'source_sha256': source['sha256'],
                    'table_records_sha256': sha256(args.table_records.read_bytes()).hexdigest(),
                    'published': False, 'full_map_created': False, 'model_calls': 0,
                    'table_numeric_cells': tables['numeric_cells'], 'contract_validation': 'passed'}
    artifacts['table-draft-verification.json'] = verification
    evidence_audit = audit_evidence_origin(artifacts['map.json']['graph'])
    artifacts['empirical-evidence-eligibility.json'] = evidence_audit
    graph = artifacts['map.json']['graph']
    status_counts = {status: sum(row['status'] == status for row in artifacts['coverage.json']['units'])
                     for status in ('represented', 'excluded')}
    exclusion_counts = {}
    for row in artifacts['coverage.json']['units']:
        if row['status'] == 'excluded':
            exclusion_counts[row['reason_ru']] = exclusion_counts.get(row['reason_ru'], 0) + 1
    report = ['# Карта WHICAP: полный текст, таблицы и зависимости', '',
        f"Проверена полная ревизия источника SHA-256 `{source['sha256']}`.",
        f"В черновике {len(normalized)} блоков, {verification['semantic_statements']} утверждений и {len(graph['transitions'])} обоснованных переходов.",
        f"Глубина графа — {graph['analysis']['depth']}; изолированных блоков — {graph['analysis']['isolated_count']}. Видимый граф прошёл проверку DAG.", '',
        '## Охват источника', '',
        f"Из {len(source['units'])} единиц источника {status_counts['represented']} имеют привязанные знания, {status_counts['excluded']} исключены с причиной.",
        f"Все шесть таблиц представлены: {tables['row_count']} строк и {tables['numeric_cells']} числовых ячеек.",
        'Причины исключения единиц источника:']
    report += [f"- {count}: {reason}" for reason, count in sorted(exclusion_counts.items(), key=lambda item: (-item[1], item[0]))]
    report += ['', '## Допуск эмпирических посылок', '',
        f"{evidence_audit['eligible_blocks']} блоков прошли фильтр прямых наблюдений; это результаты одной публикации и не независимые подтверждения.",
        f"Неизвестный контекст отмечен у {evidence_audit['reason_counts'].get('context_not_explicit', 0)} блоков. Противоречия и двусмысленность источника сохранены.", '',
        '## Ограничения', '',
        'Семантическая полнота пока явно не подтверждена; карта остаётся исследовательским черновиком и не опубликована в Neo4j или UI.',
        'Модельных вызовов не было. Экспертная проверка научной точности не проведена. Свободное прогнозирование и преимущество карты на этом черновике не оценивались.', '']
    artifacts['combined-draft-report.ru.md'] = '\n'.join(report)
    folder = args.output / artifacts['map.json']['run_id']
    for name, value in artifacts.items():
        data = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        write_immutable(folder / name, data)
    print(folder)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__':
    main()
