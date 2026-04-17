/**
 * PatternGraphView — визуализация паттернов как PixiJS-графов.
 *
 * Один паттерн = один граф (Action + LexicalUnit, рёбра LEADS_TO/DEPENDS_ON/PART_OF).
 * Показывает частотность паттерна в корпусе.
 */
import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Application } from '@pixi/react';
import { Viewport } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import {
    getExtractedPatterns,
    getExtractStatus,
    getPatternGraph,
    createPatternsInDb,
    getPatternCreateStatus,
} from '../../../services/api';
import type { PatternData, PatternGraphData, PatternGraphNode, PatternGraphEdge, PatternCreateStatus, ExtractPatternsResponse } from '../../../services/api';
import {
    NodesLayer,
    EdgesLayer,
    ScaleTracker,
    computeVisibleSet,
    linkEdgeNodes,
    type GraphNode,
    type GraphEdge,
    LOD_FULL,
    LOD_NODES,
} from './LinguisticGraphRenderer';
import s from './PatternGraphView.module.css';

export default function PatternGraphView() {
    const [patterns, setPatterns] = useState<PatternData[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Параметры извлечения
    const [maxNodes, setMaxNodes] = useState(100);
    const [maxDepth, setMaxDepth] = useState(5);
    const [limitPerN, setLimitPerN] = useState(50);
    const [minFrequency, setMinFrequency] = useState(1);
    const [mode, setMode] = useState<'all' | 'dependency' | 'action' | 'mixed'>('all');

    // Создание паттернов в БД (фоновая задача)
    const [createStatus, setCreateStatus] = useState<PatternCreateStatus>({
        status: 'idle', progress: 0, message: '',
        total_patterns: 0, saved_patterns: 0,
        error: null, started_at: null, finished_at: null,
    });
    const statusIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Извлечение паттернов (фоновая задача)
    const [extractStatus, setExtractStatus] = useState<ExtractPatternsResponse>({
        status: 'idle', progress: 0, message: '',
        total_patterns: 0, patterns: [],
        error: null, started_at: null, finished_at: null,
        max_nodes_seen: 0, extraction_mode: '', doc_ids: [], success: true,
    });

    const isCreating = createStatus.status === 'running';

    // Poll статуса фоновой задачи
    useEffect(() => {
        if (isCreating) {
            statusIntervalRef.current = setInterval(async () => {
                try {
                    const status = await getPatternCreateStatus();
                    setCreateStatus(status);
                    if (status.status === 'done' || status.status === 'error') {
                        if (statusIntervalRef.current) clearInterval(statusIntervalRef.current);
                    }
                } catch {
                    // ignore polling errors
                }
            }, 1000);
        }
        return () => {
            if (statusIntervalRef.current) clearInterval(statusIntervalRef.current);
        };
    }, [isCreating]);

    // Выбранный паттерн
    const [selectedPattern, setSelectedPattern] = useState<PatternGraphData | null>(null);
    const [graphLoading, setGraphLoading] = useState(false);

    // Для рендеринга графа
    const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
    const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
    const [scale, setScale] = useState(1);
    const [containerSize, setContainerSize] = useState({ width: window.innerWidth, height: 500 });
    const containerRef = useRef<HTMLDivElement>(null);
    const viewportRef = useRef<ViewportRef>(null);

    // Track container size
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const ro = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                if (width > 0 && height > 0) {
                    setContainerSize({ width, height });
                }
            }
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    const extractIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const isExtracting = extractStatus.status === 'running';

    // Poll статуса извлечения
    useEffect(() => {
        if (isExtracting) {
            extractIntervalRef.current = setInterval(async () => {
                try {
                    const status = await getExtractStatus();
                    setExtractStatus(status);
                    if (status.status === 'done' || status.status === 'error') {
                        if (extractIntervalRef.current) clearInterval(extractIntervalRef.current);
                        setLoading(false);
                    }
                } catch {
                    // ignore polling errors
                }
            }, 1000);
        }
        return () => {
            if (extractIntervalRef.current) clearInterval(extractIntervalRef.current);
        };
    }, [isExtracting]);

    const runExtraction = async () => {
        setLoading(true);
        setError(null);
        setSelectedPattern(null);
        setGraphNodes([]);
        setGraphEdges([]);
        setExtractStatus({
            status: 'idle', progress: 0, message: '',
            total_patterns: 0, patterns: [],
            error: null, started_at: null, finished_at: null,
            max_nodes_seen: 0, extraction_mode: '', doc_ids: [], success: true,
        });
        try {
            // Запускаем фоновое извлечение
            await getExtractedPatterns({
                maxNodes,
                maxDepth,
                limitPerN,
                minFrequency,
                mode,
            });
            // Polling запустится автоматически через useEffect
            setExtractStatus(prev => ({ ...prev, status: 'running', progress: 0, message: 'Запуск...' }));
        } catch (err: any) {
            setError(err.message || 'Ошибка извлечения паттернов');
            setLoading(false);
            setExtractStatus(prev => ({ ...prev, status: 'error', error: err.message }));
        }
    };

    // Обработка завершения извлечения — загружаем паттерны
    useEffect(() => {
        if (extractStatus.status === 'done' && extractStatus.patterns && extractStatus.patterns.length > 0) {
            setPatterns(extractStatus.patterns);
        }
    }, [extractStatus.status, extractStatus.patterns]);

    const selectPattern = useCallback(async (pattern: PatternData) => {
        setGraphLoading(true);
        setSelectedPattern(null);
        setGraphNodes([]);
        setGraphEdges([]);
        try {
            const graph = await getPatternGraph(pattern.uid);
            setSelectedPattern(graph);
            setGraphData(graph);
        } catch {
            // Если паттерн не сохранён в БД, строим граф из canon_nodes/canon_edges
            const graph = buildGraphFromPattern(pattern);
            setSelectedPattern(graph);
            setGraphData(graph);
        } finally {
            setGraphLoading(false);
        }
    }, []);

    const setGraphData = (graph: PatternGraphData) => {
        const nodeMap = new Map<string, GraphNode>();
        for (const n of graph.nodes) {
            const nodeType = n._type === 'Action' ? 'Action' : 'LexicalUnit' as const;
            const gn: GraphNode = {
                id: n.uid,
                x: n.layout_x ?? 0,
                y: n.layout_y ?? 0,
                _nodeType: nodeType,
                _data: {
                    uid: n.uid,
                    _type: nodeType,
                    verb: n.verb,
                    text: n.text,
                    lemma: n.lemma,
                    pos: n.pos,
                    action_class: n.action_class,
                    doc_id: n.doc_id,
                    layout_x: n.layout_x,
                    layout_y: n.layout_y,
                } as any,
            };
            nodeMap.set(n.uid, gn);
        }

        const ge: GraphEdge[] = graph.edges.map((e) => ({
            source_id: e.src_uid,
            target_id: e.tgt_uid,
            _edgeType: e.edge_type,
            _data: e as any,
        }));

        linkEdgeNodes(ge, nodeMap);
        setGraphNodes(Array.from(nodeMap.values()));
        setGraphEdges(ge);
    };

    const handleSave = async () => {
        if (isCreating) return;
        setCreateStatus({
            status: 'idle', progress: 0, message: '',
            total_patterns: 0, saved_patterns: 0,
            error: null, started_at: null, finished_at: null,
        });
        setError(null);
        try {
            await createPatternsInDb({
                maxNodes,
                maxDepth,
                limitPerN,
                minFrequency,
                mode,
            });
            // Polling запустится автоматически через useEffect
            setCreateStatus(prev => ({ ...prev, status: 'running', progress: 0, message: 'Запуск...' }));
        } catch (err: any) {
            setError(err.message || 'Ошибка создания паттернов');
            setCreateStatus(prev => ({ ...prev, status: 'error', error: err.message }));
        }
    };

    const handleResetStatus = () => {
        setCreateStatus({
            status: 'idle', progress: 0, message: '',
            total_patterns: 0, saved_patterns: 0,
            error: null, started_at: null, finished_at: null,
        });
    };

    const visibleNodes = useMemo(
        () => computeVisibleSet(graphNodes, viewportRef.current),
        [graphNodes, scale],
    );

    if (loading && !isExtracting) {
        return (
            <div className={s.loading}>
                <div className={s.spinner} />
                <p>Запуск извлечения паттернов...</p>
            </div>
        );
    }

    if (error) {
        return <div className={s.error}><p>Ошибка: {error}</p></div>;
    }

    return (
        <div className={s.container}>
            {/* Controls */}
            <div className={s.controls}>
                <div className={s.controlGroup}>
                    <label htmlFor="maxNodes">Макс. узлов (1-200):</label>
                    <input
                        id="maxNodes"
                        type="number"
                        min={1}
                        max={200}
                        value={maxNodes}
                        onChange={(e) => setMaxNodes(Math.max(1, Math.min(200, parseInt(e.target.value) || 100)))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.controlGroup}>
                    <label htmlFor="maxDepth">Глубина n-gram (1-10):</label>
                    <input
                        id="maxDepth"
                        type="number"
                        min={1}
                        max={10}
                        value={maxDepth}
                        onChange={(e) => setMaxDepth(Math.max(1, Math.min(10, parseInt(e.target.value) || 5)))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.controlGroup}>
                    <label htmlFor="limitPerN">Лимит на N:</label>
                    <input
                        id="limitPerN"
                        type="number"
                        min={10}
                        max={200}
                        value={limitPerN}
                        onChange={(e) => setLimitPerN(Math.max(10, Math.min(200, parseInt(e.target.value) || 50)))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.controlGroup}>
                    <label htmlFor="minFreq">Мин. частота:</label>
                    <input
                        id="minFreq"
                        type="number"
                        min={1}
                        value={minFrequency}
                        onChange={(e) => setMinFrequency(Math.max(1, parseInt(e.target.value) || 1))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.modeToggle}>
                    {(['all', 'dependency', 'action', 'mixed'] as const).map((m) => (
                        <button
                            key={m}
                            className={`${s.modeBtn} ${mode === m ? s.active : ''}`}
                            onClick={() => setMode(m)}
                        >
                            {m === 'all' ? 'Все' : m === 'dependency' ? 'Зависимости' : m === 'action' ? 'Действия' : 'Смешанные'}
                        </button>
                    ))}
                </div>
                <button
                    onClick={runExtraction}
                    disabled={loading || isExtracting || isCreating}
                    className={s.analyzeButton}
                >
                    {isExtracting ? 'Извлечение...' : loading ? 'Запуск...' : 'Анализировать'}
                </button>
                <button
                    onClick={handleSave}
                    disabled={isCreating || isExtracting}
                    className={s.createButton}
                >
                    {isCreating ? 'Создание...' : 'Создать паттерны в БД'}
                </button>
                {(createStatus.status === 'done' || createStatus.status === 'error') && (
                    <button
                        onClick={handleResetStatus}
                        className={s.resetButton}
                    >
                        Сбросить
                    </button>
                )}
            </div>

            {/* Progress bar: extraction */}
            {(isExtracting || extractStatus.status === 'done' || extractStatus.status === 'error') && (
                <div className={s.progressSection}>
                    <div className={s.progressHeader}>
                        <span className={`${s.progressStatus} ${s[`status_${extractStatus.status}`]}`}>
                            {extractStatus.status === 'running' && '⏳ '}
                            {extractStatus.status === 'done' && '✅ '}
                            {extractStatus.status === 'error' && '❌ '}
                            {extractStatus.message}
                        </span>
                        {extractStatus.status === 'running' && (
                            <span className={s.progressPercent}>{extractStatus.progress}%</span>
                        )}
                    </div>
                    <div className={s.progressBar}>
                        <div
                            className={s.progressFill}
                            style={{ width: `${extractStatus.progress}%` }}
                        />
                    </div>
                    {extractStatus.total_patterns > 0 && (
                        <div className={s.progressDetails}>
                            <span>Найдено паттернов: {extractStatus.total_patterns}</span>
                        </div>
                    )}
                </div>
            )}

            {/* Progress bar: creation */}
            {(isCreating || createStatus.status === 'done' || createStatus.status === 'error') && (
                <div className={s.progressSection}>
                    <div className={s.progressHeader}>
                        <span className={`${s.progressStatus} ${s[`status_${createStatus.status}`]}`}>
                            {createStatus.status === 'running' && '⏳ '}
                            {createStatus.status === 'done' && '✅ '}
                            {createStatus.status === 'error' && '❌ '}
                            {createStatus.message}
                        </span>
                        {createStatus.status === 'running' && (
                            <span className={s.progressPercent}>{createStatus.progress}%</span>
                        )}
                    </div>
                    <div className={s.progressBar}>
                        <div
                            className={s.progressFill}
                            style={{ width: `${createStatus.progress}%` }}
                        />
                    </div>
                    {(createStatus.total_patterns > 0 || createStatus.saved_patterns > 0) && (
                        <div className={s.progressDetails}>
                            {createStatus.total_patterns > 0 && (
                                <span>Найдено: {createStatus.total_patterns}</span>
                            )}
                            {createStatus.saved_patterns > 0 && (
                                <span>Сохранено: {createStatus.saved_patterns}</span>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Results */}
            {patterns.length === 0 && !loading && !isExtracting && !error && (
                <div className={s.empty}>
                    <p>Нажмите «Анализировать» для извлечения паттернов из графа знаний.</p>
                    <p className={s.hint}>Паттерны включают dependency n-grams, цепочки LEADS_TO и смешанные графы Action+LexicalUnit.</p>
                </div>
            )}

            {patterns.length > 0 && (
                <div className={s.results}>
                    {/* Sidebar: pattern list */}
                    <div className={s.sidebar}>
                        <h3 className={s.sidebarTitle}>
                            Паттерны ({patterns.length})
                        </h3>
                        <div className={s.patternList}>
                            {patterns.map((p, i) => (
                                <div
                                    key={p.uid || i}
                                    className={`${s.patternCard} ${selectedPattern?.uid === p.uid ? s.selected : ''}`}
                                    onClick={() => selectPattern(p)}
                                >
                                    <div className={s.patternCardHeader}>
                                        <span className={s.patternName}>{p.name || `Паттерн #${i + 1}`}</span>
                                        <span className={`${s.sizeBadge} ${s[`size_${p.size_category}`]}`}>
                                            {p.size_category || '?'}
                                        </span>
                                    </div>
                                    <div className={s.patternCardMeta}>
                                        <span className={s.frequency}>
                                            Частота: <strong>{p.frequency}</strong>
                                        </span>
                                        {p.stability !== undefined && p.stability > 0 && (
                                            <span className={s.stability}>
                                                Стаб.: {p.stability.toFixed(2)}
                                            </span>
                                        )}
                                        {p.doc_count !== undefined && p.doc_count > 0 && (
                                            <span className={s.docs}>
                                                {p.doc_count} док.
                                            </span>
                                        )}
                                    </div>
                                    <div className={s.patternCardStats}>
                                        {p.node_count} узлов · {p.edge_count} рёбер
                                    </div>
                                    {p.description && (
                                        <div className={s.patternCardDesc} title={p.description}>
                                            {p.description}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Main: graph view */}
                    <div className={s.main}>
                        {graphLoading && (
                            <div className={s.graphLoading}>
                                <div className={s.spinner} />
                                <p>Загрузка графа паттерна...</p>
                            </div>
                        )}

                        {!graphLoading && selectedPattern && graphNodes.length > 0 && (
                            <div className={s.graphView}>
                                <div className={s.graphHeader}>
                                    <h3 className={s.graphTitle}>{selectedPattern.name}</h3>
                                    <div className={s.graphMeta}>
                                        <span className={s.frequencyBadge}>
                                            Частотность: <strong>{selectedPattern.frequency}</strong> в корпусе
                                        </span>
                                    </div>
                                </div>
                                <div className={s.graphCanvas} ref={containerRef}>
                                    <Application
                                        width={containerSize.width}
                                        height={containerSize.height}
                                        backgroundColor={0x0a0e17}
                                    >
                                        <Viewport ref={viewportRef}>
                                            <ScaleTracker
                                                scale={scale}
                                                setScale={setScale}
                                                viewportRef={viewportRef}
                                            />
                                            {scale < LOD_NODES
                                                ? null
                                                : <NodesLayer
                                                    nodes={graphNodes}
                                                    visibleIds={visibleNodes}
                                                    scale={scale}
                                                    lod="full"
                                                />
                                            }
                                            <EdgesLayer
                                                edges={graphEdges}
                                                visibleIds={visibleNodes}
                                                scale={scale}
                                                lod="full"
                                            />
                                        </Viewport>
                                    </Application>
                                </div>
                            </div>
                        )}

                        {!graphLoading && selectedPattern && graphNodes.length === 0 && (
                            <div className={s.graphPlaceholder}>
                                <p>Граф паттерна пуст</p>
                            </div>
                        )}

                        {!graphLoading && !selectedPattern && (
                            <div className={s.graphPlaceholder}>
                                <p>Выберите паттерн из списка слева</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

/**
 * Строит PatternGraphData из PatternData (когда паттерн не сохранён в БД).
 */
function buildGraphFromPattern(pattern: PatternData): PatternGraphData {
    const nodes: PatternGraphNode[] = (pattern.canon_nodes || []).map((n) => ({
        uid: n.node_id,
        _type: n.node_type === 'Action' ? 'Action' : 'LexicalUnit',
        verb: n.node_type === 'Action' ? n.text : undefined,
        text: n.text,
        lemma: n.lemma,
        pos: n.pos,
        action_class: n.action_class,
        role: n.role,
        doc_id: n.doc_id,
        layout_x: null,
        layout_y: null,
    }));

    const edges: PatternGraphEdge[] = (pattern.canon_edges || []).map((e) => ({
        src_uid: e.source_id,
        tgt_uid: e.target_id,
        edge_type: e.edge_type,
        relation_subtype: e.relation_subtype,
        confidence: e.confidence,
    }));

    // Простая раскладка: круг
    const n = nodes.length;
    const radius = Math.max(50, n * 30);
    nodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2;
        node.layout_x = radius * Math.cos(angle);
        node.layout_y = radius * Math.sin(angle);
    });

    return {
        uid: pattern.uid,
        name: pattern.name,
        frequency: pattern.frequency,
        stability: pattern.stability,
        doc_count: pattern.doc_count,
        size_category: pattern.size_category,
        rendered_text: '',
        nodes,
        edges,
    };
}
