import React, { useState, useEffect } from 'react';
import s from './LinguisticPatternAnalysis.module.css';
import {
    extractDocumentActions, getPendingEdges, reviewEdge, getDocumentLinguisticGraph, autoReview,
} from '../../../services/api';
import type { PendingEdge, AutoReviewResponse } from '../../../services/api';

interface Props {
    docId: string;
}

const ACTION_CLASS_COLORS: Record<string, string> = {
    action:    '#3b82f6',
    result:    '#22c55e',
    mechanism: '#f97316',
};

const EDGE_TYPE_LABELS: Record<string, string> = {
    LEADS_TO:    'Причинно-следственная',
    DEPENDS_ON:  'Синтаксическая',
    PART_OF:     'Часть действия',
};

// ── Graph stats ──────────────────────────────────────────────────────────

interface GraphStats {
    actionCount: number;
    lexicalUnitCount: number;
    leadsToCount: number;
    dependsOnCount: number;
    partOfCount: number;
}

// ── LinguisticPatternAnalysis ─────────────────────────────────────────────

export default function LinguisticPatternAnalysis({ docId }: Props) {
    const [stats, setStats] = useState<GraphStats | null>(null);
    const [loading, setLoading] = useState(false);

    const [isActionsLoading, setIsActionsLoading] = useState(false);
    const [pendingEdges, setPendingEdges] = useState<PendingEdge[] | null>(null);
    const [actionsError, setActionsError] = useState<string | null>(null);

    const [isAutoReviewLoading, setIsAutoReviewLoading] = useState(false);
    const [autoReviewResult, setAutoReviewResult] = useState<AutoReviewResponse | null>(null);

    // Загружаем статистику графа при монтировании / смене документа
    useEffect(() => {
        setStats(null);
        setPendingEdges(null);
        setActionsError(null);
        setLoading(true);
        getDocumentLinguisticGraph(docId)
            .then(resp => {
                const actionCount = resp.nodes.filter(n => n._type === 'Action').length;
                const luCount = resp.nodes.filter(n => n._type === 'LexicalUnit').length;
                const leadsToCount = resp.edges.filter(e => e.edge_type === 'LEADS_TO').length;
                const dependsOnCount = resp.edges.filter(e => e.edge_type === 'DEPENDS_ON').length;
                const partOfCount = resp.edges.filter(e => e.edge_type === 'PART_OF').length;
                setStats({ actionCount, lexicalUnitCount: luCount, leadsToCount, dependsOnCount, partOfCount });
            })
            .catch(() => {})
            .finally(() => setLoading(false));

        getPendingEdges(docId)
            .then(response => {
                if (response.edges.length > 0) setPendingEdges(response.edges);
            })
            .catch(() => {});
    }, [docId]);

    const handleExtractActions = async () => {
        setIsActionsLoading(true);
        setActionsError(null);
        try {
            const resp = await extractDocumentActions(docId);
            if (resp.pending_count === 0 && resp.actions_count === 0) {
                setActionsError(
                    'Анализ завершён, но действий не найдено. ' +
                    'Возможные причины: документ не содержит markdown, ' +
                    'или NLP-сервис не смог распознать действия в тексте.'
                );
            }
            const edges = await getPendingEdges(docId);
            setPendingEdges(edges.edges);
            // Обновляем статистику после анализа
            getDocumentLinguisticGraph(docId)
                .then(resp => {
                    const actionCount = resp.nodes.filter(n => n._type === 'Action').length;
                    const luCount = resp.nodes.filter(n => n._type === 'LexicalUnit').length;
                    const leadsToCount = resp.edges.filter(e => e.edge_type === 'LEADS_TO').length;
                    const dependsOnCount = resp.edges.filter(e => e.edge_type === 'DEPENDS_ON').length;
                    const partOfCount = resp.edges.filter(e => e.edge_type === 'PART_OF').length;
                    setStats({ actionCount, lexicalUnitCount: luCount, leadsToCount, dependsOnCount, partOfCount });
                })
                .catch(() => {});
        } catch (e: any) {
            const msg = e.message ?? 'Ошибка анализа действий';
            setActionsError(msg);
        } finally {
            setIsActionsLoading(false);
        }
    };

    const handleReview = async (edge: PendingEdge, decision: 'confirmed' | 'rejected') => {
        setPendingEdges(prev => prev ? prev.filter(e => !(e.src_uid === edge.src_uid && e.tgt_uid === edge.tgt_uid && e.relation_subtype === edge.relation_subtype)) : prev);
        try {
            await reviewEdge(docId, {
                src_uid: edge.src_uid,
                tgt_uid: edge.tgt_uid,
                relation_subtype: edge.relation_subtype,
                decision,
            });
        } catch (e: any) {
            setPendingEdges(prev => prev ? [edge, ...prev] : [edge]);
            setActionsError(e.message ?? 'Ошибка при сохранении решения');
        }
    };

    const handleAutoReview = async () => {
        setIsAutoReviewLoading(true);
        setActionsError(null);
        try {
            const result = await autoReview(docId);
            setAutoReviewResult(result);
            // Обновляем pending edges после авто-ревью
            const edges = await getPendingEdges(docId);
            setPendingEdges(edges.edges);
            // Обновляем статистику
            getDocumentLinguisticGraph(docId)
                .then(resp => {
                    const actionCount = resp.nodes.filter(n => n._type === 'Action').length;
                    const luCount = resp.nodes.filter(n => n._type === 'LexicalUnit').length;
                    const leadsToCount = resp.edges.filter(e => e.edge_type === 'LEADS_TO').length;
                    const dependsOnCount = resp.edges.filter(e => e.edge_type === 'DEPENDS_ON').length;
                    const partOfCount = resp.edges.filter(e => e.edge_type === 'PART_OF').length;
                    setStats({ actionCount, lexicalUnitCount: luCount, leadsToCount, dependsOnCount, partOfCount });
                })
                .catch(() => {});
        } catch (e: any) {
            setActionsError(e.message ?? 'Ошибка авто-ревью');
        } finally {
            setIsAutoReviewLoading(false);
        }
    };

    return (
        <div className={s.container}>
            {/* Боковая панель */}
            <div className={s.sidebar}>
                <div className={s.sidebarTitle}>Инструменты</div>
                <button
                    className={s.analyzeButton}
                    onClick={handleExtractActions}
                    disabled={isActionsLoading}
                >
                    {isActionsLoading ? 'Извлечение...' : 'Анализ действий'}
                </button>
                {isActionsLoading && (
                    <span className={s.statusText}>Извлечение действий и цепочек...</span>
                )}
                {actionsError && (
                    <span className={s.errorText}>{actionsError}</span>
                )}
                {stats && !loading && (
                    <div className={s.statusText}>
                        <div>Действий: {stats.actionCount}</div>
                        <div>Лекс. единиц: {stats.lexicalUnitCount}</div>
                        <div>LEADS_TO: {stats.leadsToCount}</div>
                        <div>DEPENDS_ON: {stats.dependsOnCount}</div>
                        <div>PART_OF: {stats.partOfCount}</div>
                    </div>
                )}
                {pendingEdges && !isActionsLoading && (
                    <span className={s.statusText}>
                        {pendingEdges.length > 0
                            ? `${pendingEdges.length} связей на проверке`
                            : 'Нет связей на проверке'}
                    </span>
                )}

                {pendingEdges && pendingEdges.length > 0 && (
                    <button
                        className={s.analyzeButton}
                        onClick={handleAutoReview}
                        disabled={isAutoReviewLoading}
                        style={{ marginTop: 8, background: '#7c3aed' }}
                    >
                        {isAutoReviewLoading ? 'Ревью...' : 'Авто ревью'}
                    </button>
                )}
                {isAutoReviewLoading && (
                    <span className={s.statusText}>Автоматическое ревью связей...</span>
                )}
                {autoReviewResult && !isAutoReviewLoading && (
                    <div className={s.statusText}>
                        <div style={{ color: '#22c55e' }}>✓ Подтверждено: {autoReviewResult.confirmed}</div>
                        <div style={{ color: '#ef4444' }}>✗ Отклонено: {autoReviewResult.rejected}</div>
                    </div>
                )}
            </div>

            {/* Контент */}
            <div className={s.contentWrap}>
            <div className={s.content}>
                {!stats && !loading && (
                    <div className={s.empty}>
                        Граф статьи пуст. Запустите «Анализ действий» для извлечения Action и LexicalUnit узлов из текста документа.
                        <br /><br />
                        <strong>Требование:</strong> документ должен иметь markdown-версию.
                        <br /><br />
                        После анализа граф будет отображён на вкладке «Лингвистический граф».
                    </div>
                )}

                {stats && (
                    <div className={s.section}>
                        <div className={s.sectionHeader} style={{ borderLeft: '4px solid #2196F3' }}>
                            <div className={s.sectionTitle}>
                                <span className={s.sectionColorDot} style={{ background: '#2196F3' }} />
                                Лингвистический граф статьи
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <span className={s.sectionMeta}>
                                    {stats.actionCount + stats.lexicalUnitCount} узлов · {stats.leadsToCount + stats.dependsOnCount + stats.partOfCount} рёбер
                                </span>
                            </div>
                        </div>
                        <div style={{ padding: 16 }}>
                            <table className={s.table}>
                                <thead>
                                    <tr>
                                        <th>Тип узла</th>
                                        <th>Количество</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#3b82f6', marginRight: 8 }} />Action (Действие)</td>
                                        <td className={s.freqCell}>{stats.actionCount}</td>
                                    </tr>
                                    <tr>
                                        <td><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#607D8B', marginRight: 8 }} />LexicalUnit (Лексическая единица)</td>
                                        <td className={s.freqCell}>{stats.lexicalUnitCount}</td>
                                    </tr>
                                </tbody>
                            </table>

                            <table className={s.table} style={{ marginTop: 16 }}>
                                <thead>
                                    <tr>
                                        <th>Тип связи</th>
                                        <th>Количество</th>
                                        <th>Описание</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><span style={{ display: 'inline-block', width: 20, height: 3, background: '#8a2be2', marginRight: 8 }} />LEADS_TO</td>
                                        <td className={s.freqCell}>{stats.leadsToCount}</td>
                                        <td>{EDGE_TYPE_LABELS.LEADS_TO}</td>
                                    </tr>
                                    <tr>
                                        <td><span style={{ display: 'inline-block', width: 20, height: 3, background: '#4CAF50', marginRight: 8 }} />DEPENDS_ON</td>
                                        <td className={s.freqCell}>{stats.dependsOnCount}</td>
                                        <td>{EDGE_TYPE_LABELS.DEPENDS_ON}</td>
                                    </tr>
                                    <tr>
                                        <td><span style={{ display: 'inline-block', width: 20, height: 3, background: '#FF9800', borderStyle: 'dashed', marginRight: 8 }} />PART_OF</td>
                                        <td className={s.freqCell}>{stats.partOfCount}</td>
                                        <td>{EDGE_TYPE_LABELS.PART_OF}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {actionsError && !isActionsLoading && (
                    <div className={s.empty} style={{ color: '#ef4444' }}>
                        <strong>Ошибка анализа действий:</strong> {actionsError}
                    </div>
                )}

                {pendingEdges && pendingEdges.length === 0 && !isActionsLoading && !actionsError && stats && (
                    <div className={s.empty}>
                        Нет связей на проверке. Все рёбра подтверждены или отклонены.
                    </div>
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
