import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    generateEvidenceMap,
    saveEvidenceMap,
    getEvidenceMap,
    deleteEvidenceMap,
    minePatterns,
    matchEvidenceMap,
    type EvidenceMap as EvidenceMapType,
    type EvidenceClaim,
    type EvidenceFinding,
    type MinePattern,
} from '../../../services/api/evidence_map';
import styles from './EvidencePatterns.module.css';

interface EvidencePatternsProps {
    docId: string;
}

interface VerdictStyle {
    color: string;
    bg: string;
    label: string;
}

const VERDICT_STYLES: Record<string, VerdictStyle> = {
    supported: { color: '#166534', bg: '#dcfce7', label: 'Подтверждена' },
    refuted: { color: '#991b1b', bg: '#fee2e2', label: 'Опровергнута' },
    partially_supported: { color: '#92400e', bg: '#fef3c7', label: 'Частично подтверждена' },
    inconclusive: { color: '#374151', bg: '#f3f4f6', label: 'Недостаточно данных' },
};

const NODE_COLORS: Record<string, string> = {
    H: '#7c3aed',
    G: '#2563eb',
    C: '#0891b2',
    E: '#ea580c',
    F: '#16a34a',
    M: '#9333ea',
};

const EDGE_LABELS: Record<string, string> = {
    goal: 'цель',
    tested_by: 'проверяется',
    evidence: 'доказательство',
    measures: 'измеряет',
    requires: 'требует',
};

function nodeKind(label: string): string {
    return label.startsWith('C:') ? 'C' : label.charAt(0);
}

function nodeDisplay(label: string): string {
    if (label.startsWith('C:')) {
        const parts = label.split(':');
        const domain = parts[1] || '';
        return `Утверждение (${domain})`;
    }
    if (label.startsWith('F:')) {
        const parts = label.split(':');
        const [domain, pol, dir, sig] = parts.slice(1, 5);
        const dirText =
            dir === 'up' ? '↑ повышение' : dir === 'down' ? '↓ снижение' : '± без изменений';
        const sigText = sig === 'sig' ? ', значимо' : ', не значимо';
        const polText = pol === 'benefit' ? 'положит.' : pol === 'harm' ? 'отрицат.' : 'нейтр.';
        return `${domain} ${dirText} (${polText}${sigText})`;
    }
    if (label.startsWith('E:')) {
        return `Эксперимент: ${label.slice(2)}`;
    }
    if (label.startsWith('M:')) {
        const parts = label.split(':');
        const flags: Record<string, string> = {
            control: 'Контроль',
            statistics: 'Статистика',
            sample_size: 'Размер выборки',
            p_value: 'p-value',
            hypothesis: 'Гипотеза',
        };
        const ok = parts[2] === 'ok';
        return `${flags[parts[1]] || parts[1]}: ${ok ? 'есть' : 'отсутствует'}`;
    }
    switch (label) {
        case 'H': return 'Гипотеза';
        case 'G': return 'Цель';
        default: return label;
    }
}

const EvidencePatterns: React.FC<EvidencePatternsProps> = ({ docId }) => {
    const [map, setMap] = useState<EvidenceMapType | null>(null);
    const [mapLoading, setMapLoading] = useState(false);
    const [mapError, setMapError] = useState<string | null>(null);

    const [generating, setGenerating] = useState(false);
    const [generateError, setGenerateError] = useState<string | null>(null);

    const [minSupport, setMinSupport] = useState(0.6);
    const [maxSize, setMaxSize] = useState(4);
    const [mineLimit, setMineLimit] = useState(2000);
    const [mining, setMining] = useState(false);
    const [mineError, setMineError] = useState<string | null>(null);
    const [patterns, setPatterns] = useState<MinePattern[]>([]);
    const [corpusSize, setCorpusSize] = useState(0);

    const [matching, setMatching] = useState(false);
    const [matchError, setMatchError] = useState<string | null>(null);
    const [prediction, setPrediction] = useState<{ verdict: string; confidence: number; weighted_histogram: Record<string, number>; matched_count: number; method_flags: Record<string, boolean> } | null>(null);
    const [matched, setMatched] = useState<any[]>([]);

    const [expandedPattern, setExpandedPattern] = useState<string | null>(null);

    const loadMap = useCallback(async () => {
        setMapLoading(true);
        setMapError(null);
        try {
            const res = await getEvidenceMap(docId);
            setMap(res.map || null);
        } catch (e: any) {
            if (e.message && e.message.includes('404')) {
                setMap(null);
            } else {
                setMapError(e.message || String(e));
            }
        } finally {
            setMapLoading(false);
        }
    }, [docId]);

    useEffect(() => {
        loadMap();
    }, [loadMap]);

    const handleGenerate = useCallback(async () => {
        setGenerating(true);
        setGenerateError(null);
        try {
            const res = await generateEvidenceMap(docId);
            if (!res.success || !res.map) {
                throw new Error(res.message || 'Не удалось сгенерировать карту');
            }
            const saved = await saveEvidenceMap(docId, res.map);
            if (!saved.success) throw new Error(saved.message || 'Не удалось сохранить карту');
            setMap({ ...res.map, uid: saved.uid, model_id: res.map.model_id });
        } catch (e: any) {
            setGenerateError(e.message || String(e));
        } finally {
            setGenerating(false);
        }
    }, [docId]);

    const handleSave = useCallback(async () => {
        if (!map) return;
        setMapLoading(true);
        setMapError(null);
        try {
            const res = await saveEvidenceMap(docId, map);
            if (!res.success) throw new Error(res.message || 'Не удалось сохранить');
        } catch (e: any) {
            setMapError(e.message || String(e));
        } finally {
            setMapLoading(false);
        }
    }, [docId, map]);

    const handleDelete = useCallback(async () => {
        setMapLoading(true);
        setMapError(null);
        try {
            await deleteEvidenceMap(docId);
            setMap(null);
        } catch (e: any) {
            setMapError(e.message || String(e));
        } finally {
            setMapLoading(false);
        }
    }, [docId]);

    const handleMine = useCallback(async () => {
        setMining(true);
        setMineError(null);
        setPatterns([]);
        try {
            const res = await minePatterns({
                min_support: minSupport,
                min_size: 2,
                max_size: maxSize,
                limit: mineLimit,
            });
            setPatterns(res.patterns || []);
            setCorpusSize(res.corpus_size || 0);
        } catch (e: any) {
            setMineError(e.message || String(e));
        } finally {
            setMining(false);
        }
    }, [minSupport, maxSize, mineLimit]);

    const handleMatch = useCallback(async () => {
        setMatching(true);
        setMatchError(null);
        setPrediction(null);
        setMatched([]);
        try {
            const res = await matchEvidenceMap(docId, {
                min_support: 1.0,
                min_size: 2,
                max_size: maxSize,
                limit: mineLimit,
            });
            setMatched(res.matched || []);
            setPrediction(res.prediction || null);
        } catch (e: any) {
            setMatchError(e.message || String(e));
        } finally {
            setMatching(false);
        }
    }, [docId, maxSize, mineLimit]);

    const verdictStyle = useMemo(() => {
        const v = map?.verdict || prediction?.verdict || '';
        return VERDICT_STYLES[v] || VERDICT_STYLES.inconclusive;
    }, [map?.verdict, prediction?.verdict]);

    const claims = map?.claims || [];
    const findings = map?.findings || [];
    const graph = map?.graph;

    return (
        <div className={styles.container}>
            <div className={styles.toolbar}>
                <div className={styles.titleBlock}>
                    <div className={styles.title}>Доказательственная карта</div>
                    <div className={styles.subtitle}>
                        LLM-генерация · алгоритмический майнинг частотных подграфов · прогноз исхода
                    </div>
                </div>
                <div className={styles.actions}>
                    <button
                        className={styles.primaryBtn}
                        onClick={handleGenerate}
                        disabled={generating || mapLoading}
                    >
                        {generating ? 'Генерация…' : 'Сгенерировать карту'}
                    </button>
                    {map && (
                        <>
                            <button className={styles.btn} onClick={handleSave} disabled={mapLoading}>
                                Сохранить
                            </button>
                            <button className={styles.dangerBtn} onClick={handleDelete} disabled={mapLoading}>
                                Удалить
                            </button>
                        </>
                    )}
                </div>
            </div>

            {mapError && <div className={styles.error}>{mapError}</div>}
            {generateError && <div className={styles.error}>{generateError}</div>}
            {mineError && <div className={styles.error}>{mineError}</div>}
            {matchError && <div className={styles.error}>{matchError}</div>}

            {!map ? (
                <div className={styles.emptyState}>
                    {mapLoading ? (
                        <div className={styles.spinner} />
                    ) : (
                        <div>
                            <div className={styles.emptyTitle}>Карта ещё не сгенерирована</div>
                            <div className={styles.emptyText}>
                                Нажмите «Сгенерировать карту», чтобы извлечь из статьи гипотезу, цели,
                                утверждения, эксперименты, находки и методологические флаги.
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                <div className={styles.content}>
                    <div className={styles.summaryRow}>
                        <div className={styles.verdictCard} style={{ background: verdictStyle.bg }}>
                            <div className={styles.verdictLabel} style={{ color: verdictStyle.color }}>
                                {prediction ? 'Прогноз исхода' : 'Исход (LLM)'}
                            </div>
                            <div className={styles.verdictValue} style={{ color: verdictStyle.color }}>
                                {prediction ? (VERDICT_STYLES[prediction.verdict] || {}).label || prediction.verdict : verdictStyle.label}
                            </div>
                            {prediction && (
                                <div className={styles.confidence} style={{ color: verdictStyle.color }}>
                                    уверенность {(prediction.confidence * 100).toFixed(1)}%
                                </div>
                            )}
                        </div>

                        <div className={styles.statCard}>
                            <div className={styles.statValue}>{claims.length}</div>
                            <div className={styles.statLabel}>Утверждения</div>
                        </div>
                        <div className={styles.statCard}>
                            <div className={styles.statValue}>{(map.experiments || []).length}</div>
                            <div className={styles.statLabel}>Эксперименты</div>
                        </div>
                        <div className={styles.statCard}>
                            <div className={styles.statValue}>{findings.length}</div>
                            <div className={styles.statLabel}>Находки</div>
                        </div>
                        <div className={styles.statCard}>
                            <div className={styles.statValue}>{graph ? `${graph.nodes.length}/${graph.edges.length}` : '—'}</div>
                            <div className={styles.statLabel}>Узлы/связи</div>
                        </div>
                    </div>

                    <div className={styles.sections}>
                        {map.hypothesis && (
                            <div className={styles.section}>
                                <div className={styles.sectionTitle}>Гипотеза</div>
                                <div className={styles.hypothesisText}>{map.hypothesis}</div>
                            </div>
                        )}

                        {claims.length > 0 && (
                            <div className={styles.section}>
                                <div className={styles.sectionTitle}>Утверждения</div>
                                <table className={styles.table}>
                                    <tbody>
                                        {claims.map((c: EvidenceClaim, i: number) => (
                                            <tr key={i}>
                                                <td className={styles.cellMono}>{c.subject}</td>
                                                <td className={styles.cellPred}>
                                                    {c.negated ? 'не ' : ''}{c.predicate}
                                                </td>
                                                <td className={styles.cellMono}>{c.object}</td>
                                                {c.confidence != null && (
                                                    <td className={styles.cellConf}>{c.confidence}</td>
                                                )}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {findings.length > 0 && (
                            <div className={styles.section}>
                                <div className={styles.sectionTitle}>Находки</div>
                                <table className={styles.table}>
                                    <thead>
                                        <tr>
                                            <th>Параметр</th>
                                            <th>Домен</th>
                                            <th>Направление</th>
                                            <th>Значимость</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {findings.map((f: EvidenceFinding, i: number) => (
                                            <tr key={i}>
                                                <td className={styles.cellMono}>{f.parameter}</td>
                                                <td>{f.domain || '—'}</td>
                                                <td>{f.direction || '—'}</td>
                                                <td>
                                                    {f.significance || '—'}
                                                    {f.p != null ? ` (p=${f.p})` : ''}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {graph && graph.nodes.length > 0 && (
                            <div className={styles.section}>
                                <div className={styles.sectionTitle}>Типизированный граф</div>
                                <div className={styles.graphList}>
                                    {graph.nodes.map((n: any) => {
                                        const kind = nodeKind(n.label || '');
                                        return (
                                            <div className={styles.nodeChip} key={n.id}>
                                                <span
                                                    className={styles.nodeDot}
                                                    style={{ background: NODE_COLORS[kind] || '#6b7280' }}
                                                />
                                                <span className={styles.nodeText}>{nodeDisplay(n.label || '')}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className={styles.edgeList}>
                                    {graph.edges.map((e: any, i: number) => (
                                        <span className={styles.edgeChip} key={i}>
                                            {EDGE_LABELS[e.label] || e.label}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            <div className={styles.miningBlock}>
                <div className={styles.titleBlock}>
                    <div className={styles.title}>Алгоритмический майнинг</div>
                    <div className={styles.subtitle}>
                        Частотные подграфы по корпусу из {corpusSize || '—'} карт (gSpan)
                    </div>
                </div>
                <div className={styles.miningControls}>
                    <label className={styles.controlLabel}>
                        min support
                        <input
                            type="number"
                            min={0}
                            max={1}
                            step={0.1}
                            value={minSupport}
                            onChange={(e) => setMinSupport(parseFloat(e.target.value) || 0)}
                            className={styles.controlInput}
                        />
                    </label>
                    <label className={styles.controlLabel}>
                        max size
                        <input
                            type="number"
                            min={2}
                            max={9}
                            value={maxSize}
                            onChange={(e) => setMaxSize(parseInt(e.target.value) || 4)}
                            className={styles.controlInput}
                        />
                    </label>
                    <label className={styles.controlLabel}>
                        limit
                        <input
                            type="number"
                            min={1}
                            value={mineLimit}
                            onChange={(e) => setMineLimit(parseInt(e.target.value) || 2000)}
                            className={styles.controlInput}
                        />
                    </label>
                    <button className={styles.primaryBtn} onClick={handleMine} disabled={mining}>
                        {mining ? 'Майнинг…' : 'Майнинг паттернов'}
                    </button>
                </div>

                {patterns.length > 0 && (
                    <div className={styles.patternList}>
                        <div className={styles.patternStats}>
                            {patterns.length} паттернов, корпус {corpusSize} карт
                        </div>
                        {patterns.map((p: MinePattern) => {
                            const hist = p.verdict_histogram || {};
                            const entries = Object.entries(hist);
                            const maxV = Math.max(1, ...entries.map(([, c]) => c));
                            return (
                                <div className={styles.patternRow} key={p.id}>
                                    <div className={styles.patternHeader} onClick={() => setExpandedPattern(expandedPattern === p.id ? null : p.id)}>
                                        <span className={styles.patternId}>#{p.id}</span>
                                        <span className={styles.patternSize}>n={p.size}</span>
                                        <span className={styles.patternEdges}>e={p.edges_count}</span>
                                        <span className={styles.patternSupport}>
                                            support {p.support_ratio.toFixed(2)}
                                        </span>
                                        <div className={styles.histBar}>
                                            {entries.map(([v, c]) => (
                                                <div
                                                    key={v}
                                                    className={styles.histSegment}
                                                    title={`${v}: ${c}`}
                                                    style={{
                                                        width: `${(c / maxV) * 30}px`,
                                                        background: (VERDICT_STYLES[v] || {}).color || '#6b7280',
                                                    }}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                    {expandedPattern === p.id && (
                                        <div className={styles.patternDetails}>
                                            <div className={styles.detailNodes}>
                                                {p.nodes.map((n, i) => (
                                                    <span key={i} className={styles.detailNode}>
                                                        <span
                                                            className={styles.nodeDot}
                                                            style={{ background: NODE_COLORS[nodeKind(n)] || '#6b7280' }}
                                                        />
                                                        {n}
                                                    </span>
                                                ))}
                                            </div>
                                            <div className={styles.detailEdges}>
                                                {p.edges.map((e, i) => (
                                                    <span className={styles.detailEdge} key={i}>
                                                        {p.nodes[e[0]]} →[{e[2]}]→ {p.nodes[e[1]]}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className={styles.matchingBlock}>
                <div className={styles.titleBlock}>
                    <div className={styles.title}>Прогноз исхода новой статьи</div>
                    <div className={styles.subtitle}>
                        Матчинг типизированного графа текущей статьи против корпуса паттернов
                    </div>
                </div>
                <div className={styles.miningControls}>
                    <button className={styles.primaryBtn} onClick={handleMatch} disabled={matching}>
                        {matching ? 'Сопоставление…' : 'Сопоставить с корпусом'}
                    </button>
                </div>

                {prediction && (
                    <div className={styles.predictionCard} style={{ borderColor: verdictStyle.color }}>
                        <div className={styles.predictionTitle}>
                            Прогноз: <span style={{ color: verdictStyle.color }}>{VERDICT_STYLES[prediction.verdict]?.label || prediction.verdict}</span>
                        </div>
                        <div className={styles.predictionMeta}>
                            совпадений: {prediction.matched_count} · уверенность: {(prediction.confidence * 100).toFixed(1)}%
                        </div>
                        <div className={styles.methodFlags}>
                            {Object.entries(prediction.method_flags || {}).map(([k, v]) => (
                                <span key={k} className={styles.methodFlag}>
                                    {k}: {v ? '✓' : '✗'}
                                </span>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default EvidencePatterns;
