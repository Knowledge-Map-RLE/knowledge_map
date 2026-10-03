import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, Link } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import { fetchJson } from '../../../services/api/http';
import { ARTICLE_BLOCK_WIDTH, ArticleBlock, getArticleBlockHeight } from './ArticleBlock';
import { collectSubgraph } from './articleMapGraph';
import type { ArticleMapGraph, ArticleMapLink, ArticleMapNode } from './articleMapGraph';

extend({ Container, Graphics, Text });

interface ArticleMapProps {
    docId: string;
    enabled: boolean;
}

interface SavedMapGraph {
    schema_version: number;
    nodes: Array<{
        id: string;
        block_type: string;
        order: number;
        rank: number;
        display_text: string;
        is_goal?: boolean;
    }>;
    edges: Array<{ source: string; target: string }>;
}

interface CurrentMap {
    graph: SavedMapGraph | null;
    blocks: unknown[];
    stale?: boolean;
}

const DPR = typeof window !== 'undefined' ? Math.max(1, window.devicePixelRatio || 1) : 1;
const SPACING_X = 300;
const PADDING = 60;
const BLOCK_GAP_Y = 24;

const ArticleMap: React.FC<ArticleMapProps> = ({ docId, enabled }) => {
    const { t, i18n } = useTranslation();
    const locale = i18n.resolvedLanguage === 'ru' ? 'ru' : 'en';
    const [hoveredId, setHoveredId] = useState<string | null>(null);
    const [containerEl, setContainerEl] = useState<HTMLElement | null>(null);
    const viewportRef = useRef<ViewportRef>(null);
    const requestGeneration = useRef(0);
    const [mapResult, setMapResult] = useState<{ docId: string; value: CurrentMap } | null>(null);
    const [loading, setLoading] = useState(true);
    const [building, setBuilding] = useState(false);
    const [error, setError] = useState('');
    const base = `/api/article_editor/articles/${encodeURIComponent(docId)}/pipeline/current-map`;
    const currentMap = mapResult?.docId === docId ? mapResult.value : null;

    const loadMap = useCallback(async () => {
        const requestId = ++requestGeneration.current;
        if (!enabled) {
            setLoading(false);
            setError('');
            setMapResult(null);
            return;
        }
        setLoading(true);
        setError('');
        try {
            const result = await fetchJson<CurrentMap>(`${base}?locale=${locale}`);
            if (requestId === requestGeneration.current) setMapResult({ docId, value: result });
        } catch (cause) {
            if (requestId === requestGeneration.current) {
                setError(cause instanceof Error ? cause.message : String(cause));
            }
        } finally {
            if (requestId === requestGeneration.current) setLoading(false);
        }
    }, [base, docId, enabled, locale]);

    useEffect(() => {
        void loadMap();
    }, [loadMap]);

    const rebuildMap = useCallback(async () => {
        setBuilding(true);
        setError('');
        try {
            const result = await fetchJson<CurrentMap>(`${base}/rebuild?locale=${locale}`, { method: 'POST' });
            setMapResult({ docId, value: result });
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : String(cause));
        } finally {
            setBuilding(false);
        }
    }, [base, docId, locale]);

    const graph: ArticleMapGraph | null = useMemo(() => {
        const saved = currentMap?.graph;
        if (!saved) return null;
        const nextYByRank = new Map<number, number>();
        const ordered = [...saved.nodes].sort((a, b) =>
            a.rank - b.rank || a.order - b.order || a.id.localeCompare(b.id),
        );
        const nodes: ArticleMapNode[] = ordered.map((node) => {
            const label = node.display_text?.trim() || node.block_type;
            const height = getArticleBlockHeight(label, node.is_goal === true);
            const top = nextYByRank.get(node.rank) ?? PADDING;
            const y = top + height / 2;
            nextYByRank.set(node.rank, top + height + BLOCK_GAP_Y);
            return {
                id: node.id,
                title: label,
                text: label,
                x: node.rank * SPACING_X + PADDING + ARTICLE_BLOCK_WIDTH / 2,
                y,
                level: 0,
                layer: node.rank,
                blockType: node.block_type,
                order: node.order,
                label,
                outcome: 'neutral',
                outcomeLabel: '',
                data: {},
                isGoal: node.is_goal === true,
                height,
            };
        });
        const links: ArticleMapLink[] = saved.edges.map((edge) => ({
            id: `${edge.source}::${edge.target}`,
            source_id: edge.source,
            target_id: edge.target,
        }));
        return { nodes, links, studyVerdict: t('articleEditor.map.deterministic', { version: saved.schema_version }) };
    }, [currentMap?.graph, t]);

    const nodes = graph?.nodes ?? [];
    const links = graph?.links ?? [];

    const subgraph = useMemo(
        () => (hoveredId && graph ? collectSubgraph(graph, hoveredId) : null),
        [graph, hoveredId],
    );

    const linkAppearance = useCallback((link: ArticleMapLink): { color?: number; alpha: number } => {
        if (!subgraph) return { color: 0x2563eb, alpha: 0.8 };
        return subgraph.links.has(link.id)
            ? { color: 0x2563eb, alpha: 1 }
            : { color: 0x9ca3af, alpha: 0.12 };
    }, [subgraph]);

    useEffect(() => {
        if (nodes.length === 0 || !viewportRef.current) return;
        const minX = Math.min(...nodes.map(node => node.x));
        const maxX = Math.max(...nodes.map(node => node.x));
        const minY = Math.min(...nodes.map(node => node.y));
        const maxY = Math.max(...nodes.map(node => node.y));
        const timer = window.setTimeout(() => {
            viewportRef.current?.focusOn((minX + maxX) / 2, (minY + maxY) / 2);
        }, 100);
        return () => window.clearTimeout(timer);
    }, [nodes]);

    const containerCbRef = useCallback((element: HTMLDivElement | null) => {
        setContainerEl(element);
    }, []);

    if (!enabled) {
        return <StatusMessage>{t('articleEditor.map.loginRequired')}</StatusMessage>;
    }
    if (loading) return <StatusMessage>{t('articleEditor.map.loading')}</StatusMessage>;
    if (error && !currentMap) {
        return (
            <StatusMessage>
                <div role="alert" style={{ marginBottom: 12 }}>{t('articleEditor.map.loadError', { error })}</div>
                <button type="button" onClick={() => void loadMap()}>{t('articleEditor.map.retry')}</button>
            </StatusMessage>
        );
    }
    if (!graph) {
        const hasBlocks = (currentMap?.blocks.length ?? 0) > 0;
        return (
            <StatusMessage>
                {error && <div role="alert" style={{ marginBottom: 12 }}>{error}</div>}
                <div style={{ marginBottom: 12 }}>
                    {!hasBlocks
                        ? t('articleEditor.map.noRows')
                        : currentMap?.stale
                            ? t('articleEditor.map.stale')
                            : t('articleEditor.map.notBuilt')}
                </div>
                {hasBlocks && (
                    <button type="button" onClick={() => void rebuildMap()} disabled={building}>
                        {building ? t('articleEditor.map.building') : t('articleEditor.map.build')}
                    </button>
                )}
            </StatusMessage>
        );
    }
    if (nodes.length === 0) return <StatusMessage>{t('articleEditor.map.noNodes')}</StatusMessage>;

    return (
        <div ref={containerCbRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
            {containerEl && (
                <Application
                    resizeTo={containerEl}
                    backgroundColor={0xf8fafc}
                    resolution={DPR}
                    antialias
                    autoDensity
                >
                    <Viewport ref={viewportRef}>
                        {links.map(link => {
                            const { color, alpha } = linkAppearance(link);
                            return (
                                <Link
                                    key={link.id}
                                    linkData={link}
                                    blocks={nodes}
                                    isSelected={false}
                                    onClick={() => {}}
                                    color={color}
                                    alpha={alpha}
                                />
                            );
                        })}
                        {nodes.map((node: ArticleMapNode) => (
                            <ArticleBlock
                                key={node.id}
                                blockData={node}
                                hovered={node.id === hoveredId}
                                highlighted={subgraph ? subgraph.nodes.has(node.id) : false}
                                dimmed={hoveredId !== null && subgraph ? !subgraph.nodes.has(node.id) : false}
                                onHover={setHoveredId}
                            />
                        ))}
                    </Viewport>
                </Application>
            )}
            <div
                style={{
                    position: 'absolute', top: 12, right: 12, zIndex: 10, pointerEvents: 'none',
                    background: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb',
                    borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#374151',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.08)', maxWidth: 260,
                }}
            >
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{t('articleEditor.map.title')}</div>
                <div style={{ marginBottom: 6 }}>{t('articleEditor.map.count', { nodes: nodes.length, edges: links.length })}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span style={{ width: 18, height: 3, background: '#2563eb', display: 'inline-block' }} />
                    <span>{t('articleEditor.map.nextStep')}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 10, height: 10, border: '2px solid #ea580c', borderRadius: 2, display: 'inline-block' }} />
                    <span>{t('articleEditor.map.goal')}</span>
                </div>
                <div style={{ marginTop: 6, borderTop: '1px solid #e5e7eb', paddingTop: 4 }}>
                    {graph.studyVerdict}
                    <br />{t('articleEditor.map.hoverHint')}
                </div>
            </div>
            {error && (
                <div role="alert" style={{ position: 'absolute', bottom: 12, left: 12, zIndex: 10, background: '#fff', color: '#b91c1c', padding: 8, borderRadius: 6 }}>
                    {error}
                </div>
            )}
        </div>
    );
};

function StatusMessage({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', textAlign: 'center', padding: '2rem' }}>
            {children}
        </div>
    );
}

export default ArticleMap;
