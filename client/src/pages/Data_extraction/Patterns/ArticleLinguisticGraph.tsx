/**
 * ArticleLinguisticGraph — визуализация лингвистического графа одной статьи.
 * Переиспользует shared компоненты из LinguisticGraphRenderer.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Application } from '@pixi/react';
import { Viewport } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import { getDocumentLinguisticGraph } from '../../../services/api';
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
} from '../../Pattern_analysis/components/LinguisticGraphRenderer';
import styles from './ArticleLinguisticGraph.module.css';

export function ArticleLinguisticGraph({ docId }: { docId: string }) {
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [edges, setEdges] = useState<GraphEdge[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [scale, setScale] = useState(1);
    const viewportRef = useRef<ViewportRef>(null);
    const cancelRef = useRef(false);

    const loadGraph = useCallback(async () => {
        cancelRef.current = false;
        setLoading(true);
        setError(null);

        try {
            const resp = await getDocumentLinguisticGraph(docId);

            if (cancelRef.current) return;

            const hasLayout = resp.nodes.some(
                (n) => n.layout_x != null && n.layout_y != null
            );

            let graphNodes: GraphNode[];

            if (hasLayout) {
                graphNodes = resp.nodes.map((n) => ({
                    id: n.uid, x: n.layout_x ?? 0, y: n.layout_y ?? 0,
                    _nodeType: n._type, _data: n,
                }));
                const graphEdges: GraphEdge[] = resp.edges.map((e) => ({
                    source_id: e.src_uid, target_id: e.tgt_uid, _edgeType: e.edge_type, _data: e,
                }));
                linkEdgeNodes(graphEdges, new Map(graphNodes.map((n) => [n.id, n])));
                setNodes(graphNodes);
                setEdges(graphEdges);
                setLoading(false);
            } else {
                const simNodes = resp.nodes.map((n) => ({ id: n.uid, x: 0, y: 0 }));
                const simEdges = resp.edges.map((e) => ({ source_id: e.src_uid, target_id: e.tgt_uid }));
                const iterations = resp.nodes.length > 5000 ? 1200 : resp.nodes.length > 1000 ? 900 : 600;

                const { default: WorkerConstructor } = await import('../../../workers/forceSimulation.worker.ts?worker');
                const worker = new WorkerConstructor();

                worker.onmessage = (e: MessageEvent) => {
                    if (cancelRef.current) { worker.terminate(); return; }
                    const { success, nodes: simulatedNodes, error: workerError } = e.data;
                    if (!success) {
                        setError(`Ошибка симуляции: ${workerError}`);
                        setLoading(false);
                        worker.terminate();
                        return;
                    }
                    const nodeMap = new Map<string, { x: number; y: number }>(
                        simulatedNodes.map((s: { id: string; x: number; y: number }) => [s.id, s])
                    );
                    const gNodes: GraphNode[] = resp.nodes.map((n) => {
                        const pos = nodeMap.get(n.uid)!;
                        return { id: n.uid, x: pos.x, y: pos.y, _nodeType: n._type, _data: n };
                    });
                    const gEdges: GraphEdge[] = resp.edges.map((e) => ({
                        source_id: e.src_uid, target_id: e.tgt_uid, _edgeType: e.edge_type, _data: e,
                    }));
                    linkEdgeNodes(gEdges, new Map(gNodes.map((n) => [n.id, n])));
                    setNodes(gNodes);
                    setEdges(gEdges);
                    setLoading(false);
                    worker.terminate();
                };

                worker.onerror = (err) => {
                    if (cancelRef.current) return;
                    setError(`Ошибка воркера: ${err.message}`);
                    setLoading(false);
                    worker.terminate();
                };

                worker.postMessage({
                    nodes: simNodes, edges: simEdges,
                    config: { iterations, repulsionStrength: -200, linkDistance: 500, initialSpread: 1000, theta: 0.3, damping: 0.5 },
                });
            }
        } catch (err: any) {
            if (cancelRef.current) return;
            setError(err.message || 'Ошибка загрузки графа');
            setLoading(false);
        }
    }, [docId]);

    useEffect(() => { loadGraph(); }, [loadGraph]);

    const nodePositionsRef = useRef<Array<{ id: string; x: number; y: number; _nodeType: string }>>([]);
    useEffect(() => {
        nodePositionsRef.current = nodes.map((n) => ({ id: n.id, x: n.x, y: n.y, _nodeType: n._nodeType }));
    }, [nodes]);

    const visibleIds = useMemo(() => {
        if (nodePositionsRef.current.length === 0) return new Set<string>();
        return computeVisibleSet(nodePositionsRef.current, viewportRef.current);
    }, [nodes.length, scale]);

    const lod = scale >= LOD_FULL ? 'full' : scale >= LOD_NODES ? 'nodes' : 'dots';
    const initialLod = nodes.length > 10000 ? 'nodes' : lod;

    if (loading) {
        return (
            <div className={styles.loading}>
                <div className={styles.spinner}></div>
                <p>Построение лингвистического графа…</p>
            </div>
        );
    }

    if (error) {
        return <div className={styles.error}><p>Ошибка: {error}</p></div>;
    }

    if (nodes.length === 0) {
        return (
            <div className={styles.empty}>
                <p>Граф пуст. Запустите «Анализ действий» во вкладке «Паттерны» для извлечения Action и LexicalUnit узлов из текста статьи.</p>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <Application width={window.innerWidth - 320} height={window.innerHeight - 60} backgroundColor={0xf5f5f5}>
                <Viewport ref={viewportRef}>
                    <ScaleTracker scale={scale} setScale={setScale} viewportRef={viewportRef} />
                    <NodesLayer nodes={nodes} visibleIds={visibleIds} scale={scale} lod={initialLod} />
                    <EdgesLayer edges={edges} visibleIds={visibleIds} scale={scale} lod={initialLod} />
                </Viewport>
            </Application>

            <div className={styles.legend}>
                <div className={styles.legendTitle}>
                    <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: '#2196F3' }}></span>Action</div>
                    <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: '#607D8B' }}></span>LexicalUnit</div>
                    <div className={styles.legendItem}><span className={styles.legendLine} style={{ background: '#8a2be2' }}></span>LEADS_TO</div>
                    <div className={styles.legendItem}><span className={styles.legendLine} style={{ background: '#4CAF50' }}></span>DEPENDS_ON</div>
                    <div className={styles.legendItem}><span className={styles.legendLineDashed} style={{ background: '#FF9800' }}></span>PART_OF</div>
                </div>
                <div className={styles.stats}>Узлов: {nodes.length} · Рёбер: {edges.length}</div>
            </div>
        </div>
    );
}
