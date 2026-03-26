import React, { useState, useEffect } from 'react';
import s from './LinguisticPatternAnalysis.module.css';
import {
    analyzeDocumentPatterns, getDocumentPatterns, getDocumentSpecificPatterns,
    extractDocumentActions, getPendingEdges, reviewEdge,
} from '../../../services/api';
import type { AnnotationTypePatterns, PatternRow, PendingEdge } from '../../../services/api';

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

const ACTION_CLASS_COLORS: Record<string, string> = {
    action:    '#3b82f6',
    result:    '#22c55e',
    mechanism: '#f97316',
};

export default function LinguisticPatternAnalysis({ docId }: Props) {
    const [isLoading, setIsLoading] = useState(false);
    const [results, setResults] = useState<AnnotationTypePatterns[] | null>(null);
    const [specificResults, setSpecificResults] = useState<AnnotationTypePatterns[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    const [isActionsLoading, setIsActionsLoading] = useState(false);
    const [pendingEdges, setPendingEdges] = useState<PendingEdge[] | null>(null);
    const [actionsError, setActionsError] = useState<string | null>(null);

    // Загружаем сохранённые паттерны при монтировании / смене документа
    useEffect(() => {
        setResults(null);
        setSpecificResults(null);
        setError(null);
        setPendingEdges(null);
        setActionsError(null);
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
        getPendingEdges(docId)
            .then(response => {
                if (response.edges.length > 0) setPendingEdges(response.edges);
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

    const handleExtractActions = async () => {
        setIsActionsLoading(true);
        setActionsError(null);
        try {
            await extractDocumentActions(docId);
            const resp = await getPendingEdges(docId);
            setPendingEdges(resp.edges);
        } catch (e: any) {
            setActionsError(e.message ?? 'Ошибка анализа действий');
        } finally {
            setIsActionsLoading(false);
        }
    };

    const handleReview = async (edge: PendingEdge, decision: 'confirmed' | 'rejected') => {
        // Optimistic update
        setPendingEdges(prev => prev ? prev.filter(e => !(e.src_uid === edge.src_uid && e.tgt_uid === edge.tgt_uid && e.relation_subtype === edge.relation_subtype)) : prev);
        try {
            await reviewEdge(docId, {
                src_uid: edge.src_uid,
                tgt_uid: edge.tgt_uid,
                relation_subtype: edge.relation_subtype,
                decision,
            });
        } catch (e: any) {
            // Rollback on error
            setPendingEdges(prev => prev ? [edge, ...prev] : [edge]);
            setActionsError(e.message ?? 'Ошибка при сохранении решения');
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
                    disabled={isLoading || isActionsLoading}
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
                        Найдено паттернов: {results.reduce((sum, r) => sum + r.patterns.length, 0)}
                    </span>
                )}

                <button
                    className={s.analyzeButton}
                    onClick={handleExtractActions}
                    disabled={isLoading || isActionsLoading}
                    style={{ marginTop: 8 }}
                >
                    {isActionsLoading ? 'Извлечение...' : 'Анализ действий'}
                </button>
                {isActionsLoading && (
                    <span className={s.statusText}>Извлечение действий и цепочек...</span>
                )}
                {actionsError && (
                    <span className={s.errorText}>{actionsError}</span>
                )}
                {pendingEdges && !isActionsLoading && (
                    <span className={s.statusText}>
                        {pendingEdges.length > 0
                            ? `${pendingEdges.length} связей на проверке`
                            : 'Нет связей на проверке'}
                    </span>
                )}
            </div>

            {/* Контент */}
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

                {pendingEdges && pendingEdges.length > 0 && (
                    <>
                        <div className={s.divider}>Действия и цепочки — на проверке</div>
                        {pendingEdges.map((edge, i) => (
                            <div key={`${edge.src_uid}-${edge.tgt_uid}-${edge.relation_subtype}-${i}`} className={s.edgeCard}>
                                <div className={s.edgeRow}>
                                    <span
                                        className={s.edgeClassTag}
                                        style={{ background: ACTION_CLASS_COLORS[edge.src_class] ?? '#6b7280' }}
                                    >
                                        {edge.src_class}
                                    </span>
                                    <span className={s.edgeText}>{edge.src_phrase || edge.src_text}</span>
                                    <span className={s.edgeArrow}>── leads to ──›</span>
                                    <span
                                        className={s.edgeClassTag}
                                        style={{ background: ACTION_CLASS_COLORS[edge.tgt_class] ?? '#6b7280' }}
                                    >
                                        {edge.tgt_class}
                                    </span>
                                    <span className={s.edgeText}>{edge.tgt_phrase || edge.tgt_text}</span>
                                    <span className={s.edgeConf}>conf: {edge.confidence.toFixed(2)}</span>
                                </div>
                                {edge.src_sentence && (
                                    <div className={s.edgeSentence}>«{edge.src_sentence}»</div>
                                )}
                                {edge.evidence.length > 0 && (
                                    <div className={s.edgeEvidence}>маркеры: {edge.evidence.join(', ')}</div>
                                )}
                                <div className={s.edgeActions}>
                                    <button
                                        className={s.confirmButton}
                                        onClick={() => handleReview(edge, 'confirmed')}
                                    >
                                        ✓ Подтвердить
                                    </button>
                                    <button
                                        className={s.rejectButton}
                                        onClick={() => handleReview(edge, 'rejected')}
                                    >
                                        ✗ Отклонить
                                    </button>
                                </div>
                            </div>
                        ))}
                    </>
                )}
            </div>
            </div>
        </div>
    );
}
