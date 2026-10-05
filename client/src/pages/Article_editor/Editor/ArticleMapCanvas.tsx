import React, { useState, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, Link } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import type { SavedArticleMap } from '../../../services/api/article_maps';
import { ArticleBlock } from './ArticleBlock';
import { adaptSavedArticleMap } from './articleMapAdapter';
import { collectSubgraph } from './articleMapGraph';
import type { ArticleMapLink, ArticleMapNode } from './articleMapGraph';

extend({ Container, Graphics, Text });

interface ArticleMapProps {
    result: SavedArticleMap;
}

const DPR = typeof window !== 'undefined' ? Math.max(1, window.devicePixelRatio || 1) : 1;

const ArticleMapCanvas: React.FC<ArticleMapProps> = ({ result }) => {
    const { t, i18n } = useTranslation();
    const [hoveredId, setHoveredId] = useState<string | null>(null);
    const [containerEl, setContainerEl] = useState<HTMLElement | null>(null);
    const centeredGraph = useRef<object | null>(null);

    const projection = useMemo(() => {
        try { return { graph: adaptSavedArticleMap(result, t), error: '' }; }
        catch (cause) { return { graph: null, error: cause instanceof Error ? cause.message : String(cause) }; }
    }, [result, t, i18n.resolvedLanguage]);
    const graph = projection.graph;

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

    const viewportCbRef = useCallback((viewport: ViewportRef | null) => {
        if (!viewport?.containerRef || nodes.length === 0 || centeredGraph.current === graph) return;
        const screen = viewport.getScreenSize?.();
        if (!screen || screen.width <= 0 || screen.height <= 0) return;
        const minX = Math.min(...nodes.map(node => node.x));
        const maxX = Math.max(...nodes.map(node => node.x));
        const minY = Math.min(...nodes.map(node => node.y));
        const maxY = Math.max(...nodes.map(node => node.y));
        // Ref приходит после готовности Pixi, без гонки с фиксированным таймером.
        viewport.focusOn((minX + maxX) / 2, (minY + maxY) / 2);
        centeredGraph.current = graph;
    }, [graph, nodes]);

    const containerCbRef = useCallback((element: HTMLDivElement | null) => {
        setContainerEl(element);
    }, []);

    if (projection.error) return <div role="alert"><StatusMessage>{projection.error}</StatusMessage></div>;
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
                    <Viewport ref={viewportCbRef}>
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

export default ArticleMapCanvas;
