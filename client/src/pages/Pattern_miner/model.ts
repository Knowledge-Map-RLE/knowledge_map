export interface PatternMinerParams {
    minSupport: number;
    minSize: number;
    maxSize: number;
    limit: number;
    predicateMode: 'raw' | 'direction' | 'bucket';
    usefulOnly: boolean;
    statementsPerDocCap: number;
    maxNodes: number;
}

export const DEFAULT_PARAMS: PatternMinerParams = {
    minSupport: 0.3,
    minSize: 2,
    maxSize: 6,
    limit: 200,
    predicateMode: 'raw',
    usefulOnly: true,
    statementsPerDocCap: 140,
    maxNodes: 120,
};

export const PREDICATE_MODES: { value: PatternMinerParams['predicateMode']; label: string }[] = [
    { value: 'raw', label: 'Как есть' },
    { value: 'direction', label: 'Направление (up/down/other)' },
    { value: 'bucket', label: 'Направление + текст' },
];

export const NODE_LABEL_RU: Record<string, string> = {
    concept: 'Концепт',
    literal: 'Литерал',
    statement: 'Утв. (внешнее)',
    other: 'Другое',
    _: '—',
};

/** Упрощённый label узла-утверждения 'ST|pred|st|ot' → 'ST:pred' */
export function labelForNode(label: string): string {
    if (label.startsWith('ST|')) {
        const parts = label.split('|');
        return parts.length >= 2 ? `ST:${parts[1]}` : label;
    }
    return NODE_LABEL_RU[label] ?? label;
}

export const KNOWLEDGE_METHOD_LABEL_RU: Record<string, string> = {
    pattern: 'Паттерн',
    logical: 'Логическая операция',
    syllogism: 'Силлогизм',
    thinking: 'Операция мышления',
};

export const CHECK_STATUS_LABEL_RU: Record<string, { label: string; tone: 'new' | 'exists' | 'conflicts' }> = {
    new: { label: 'новое', tone: 'new' },
    exists: { label: 'есть в базе', tone: 'exists' },
    conflicts: { label: 'противоречит', tone: 'conflicts' },
};