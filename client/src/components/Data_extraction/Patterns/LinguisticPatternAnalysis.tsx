import React, { useState, useEffect } from 'react';
import s from './LinguisticPatternAnalysis.module.css';
import { analyzeDocumentPatterns, getDocumentPatterns, getDocumentSpecificPatterns } from '../../../services/api';
import type { AnnotationTypePatterns, PatternRow } from '../../../services/api';

interface Props {
    docId: string;
}

const GOAL_TYPES: { type: string; color: string }[] = [
    { type: 'Успешная цель',             color: '#4CAF50' },
    { type: 'Не успешная цель',          color: '#F44336' },
    { type: 'Фрагмент ведёт к успеху',   color: '#81C784' },
    { type: 'Фрагмент ведёт к неуспеху', color: '#EF9A9A' },
];

const PATTERN_TYPE_LABELS: Record<string, string> = {
    pos_sequence:  'POS-последовательность',
    dep_bigram:    'Биграмма зависимостей',
    dep_trigram:   'Триграмма зависимостей',
    token_dep_pair: 'Токен + роль',
    head_dep_chain: 'Цепочка управления',
};

// ── PatternTable ──────────────────────────────────────────────────────────

interface PatternTableProps {
    annotationType: string;
    color: string;
    patterns: PatternRow[];
    totalAnnotations: number;
}

function PatternTable({ annotationType, color, patterns, totalAnnotations }: PatternTableProps) {
    const [open, setOpen] = useState(true);

    return (
        <div className={s.section}>
            <div
                className={s.sectionHeader}
                style={{ borderLeft: `4px solid ${color}` }}
                onClick={() => setOpen(o => !o)}
            >
                <div className={s.sectionTitle}>
                    <span className={s.sectionColorDot} style={{ background: color }} />
                    {annotationType}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={s.sectionMeta}>
                        {totalAnnotations} аннот. · {patterns.length} паттернов
                    </span>
                    <span className={s.sectionChevron}>{open ? '▲' : '▼'}</span>
                </div>
            </div>

            {open && (
                <div className={s.tableWrap}>
                    {patterns.length === 0 ? (
                        <div className={s.noPatterns}>Паттерны не найдены</div>
                    ) : (
                        <table className={s.table}>
                            <thead>
                                <tr>
                                    <th>Паттерн</th>
                                    <th>Тип структуры</th>
                                    <th>Частота</th>
                                </tr>
                            </thead>
                            <tbody>
                                {patterns.map((row, i) => (
                                    <tr key={i}>
                                        <td className={s.patternCell}>{row.pattern_str}</td>
                                        <td className={s.typeCell}>
                                            {PATTERN_TYPE_LABELS[row.pattern_type] ?? row.pattern_type}
                                        </td>
                                        <td className={s.freqCell}>{row.frequency}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </div>
    );
}

const SPECIFIC_COLORS: Record<string, string> = {
    'Специфичные: только Успешная цель':             '#4CAF50',
    'Специфичные: только Не успешная цель':          '#F44336',
    'Специфичные: только Фрагмент ведёт к успеху':   '#81C784',
    'Специфичные: только Фрагмент ведёт к неуспеху': '#EF9A9A',
};

// ── LinguisticPatternAnalysis ─────────────────────────────────────────────

export default function LinguisticPatternAnalysis({ docId }: Props) {
    const [isLoading, setIsLoading] = useState(false);
    const [results, setResults] = useState<AnnotationTypePatterns[] | null>(null);
    const [specificResults, setSpecificResults] = useState<AnnotationTypePatterns[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Загружаем сохранённые паттерны при монтировании / смене документа
    useEffect(() => {
        setResults(null);
        setSpecificResults(null);
        setError(null);
        getDocumentPatterns(docId)
            .then(response => {
                const hasPatterns = response.results.some(r => r.patterns.length > 0);
                if (hasPatterns) setResults(response.results);
            })
            .catch(() => {});
        getDocumentSpecificPatterns(docId)
            .then(response => {
                const hasPatterns = response.results.some(r => r.patterns.length > 0);
                if (hasPatterns) setSpecificResults(response.results);
            })
            .catch(() => {});
    }, [docId]);

    const handleAnalyze = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const main = await analyzeDocumentPatterns(docId);
            setResults(main.results);
            const specific = await getDocumentSpecificPatterns(docId);
            setSpecificResults(specific.results);
        } catch (e: any) {
            setError(e.message ?? 'Ошибка анализа паттернов');
        } finally {
            setIsLoading(false);
        }
    };

    // Индекс результатов по типу аннотации для быстрого доступа
    const resultByType = results
        ? Object.fromEntries(results.map(r => [r.annotation_type, r]))
        : null;

    return (
        <div className={s.container}>
            {/* Боковая панель */}
            <div className={s.sidebar}>
                <div className={s.sidebarTitle}>Инструменты</div>
                <button
                    className={s.analyzeButton}
                    onClick={handleAnalyze}
                    disabled={isLoading}
                >
                    {isLoading ? 'Анализ...' : 'Анализ паттернов'}
                </button>
                {isLoading && (
                    <span className={s.statusText}>Выполняется NLP-анализ аннотаций...</span>
                )}
                {error && (
                    <span className={s.errorText}>{error}</span>
                )}
                {results && !isLoading && (
                    <span className={s.statusText}>
                        Найдено паттернов: {results.reduce((s, r) => s + r.patterns.length, 0)}
                    </span>
                )}
            </div>

            {/* position:relative обёртка + absolute прокручиваемый контент */}
            <div className={s.contentWrap}>
            <div className={s.content}>
                {!results && !isLoading && (
                    <div className={s.empty}>
                        Нажмите «Анализ паттернов» для извлечения лингвистических структур из аннотаций
                    </div>
                )}

                {results && GOAL_TYPES.map(({ type, color }) => {
                    const group = resultByType?.[type];
                    return (
                        <PatternTable
                            key={type}
                            annotationType={type}
                            color={color}
                            patterns={group?.patterns ?? []}
                            totalAnnotations={group?.total_annotations ?? 0}
                        />
                    );
                })}

                {specificResults && (
                    <>
                        <div className={s.divider}>Специфичные паттерны (без общих)</div>
                        {specificResults.map(group => (
                            <PatternTable
                                key={group.annotation_type}
                                annotationType={group.annotation_type}
                                color={SPECIFIC_COLORS[group.annotation_type] ?? '#9ca3af'}
                                patterns={group.patterns}
                                totalAnnotations={group.total_annotations}
                            />
                        ))}
                    </>
                )}
            </div>
            </div>
        </div>
    );
}
