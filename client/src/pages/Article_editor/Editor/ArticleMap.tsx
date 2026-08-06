import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, Link } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import { ArticleBlock } from './ArticleBlock';
import { buildArticleMapGraph, collectSubgraph, OUTCOME_COLORS } from './articleMapGraph';
import type { ArticleMapGraph, ArticleMapLink, ArticleMapNode } from './articleMapGraph';
import type { ArticleBlockData } from '../model';

extend({ Container, Graphics, Text });

interface ArticleMapProps {
    blocks: ArticleBlockData[];
}

const DPR = typeof window !== 'undefined' ? Math.max(1, window.devicePixelRatio || 1) : 1;

const LEGEND: Array<{ color: string; label: string }> = [
    { color: '#22c55e', label: 'поддержано' },
    { color: '#f59e0b', label: 'частично' },
    { color: '#ef4444', label: 'опровергнуто' },
    { color: '#9ca3af', label: 'контекст / не определено' },
];

const ArticleMap: React.FC<ArticleMapProps> = ({ blocks }) => {
    const [hoveredId, setHoveredId] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerEl, setContainerEl] = useState<HTMLElement | null>(null);
    const viewportRef = useRef<ViewportRef>(null);
    const containerCbRef = useCallback((el: HTMLDivElement | null) => {
        containerRef.current = el;
        if (el) setContainerEl(el);
    }, []);

    const graph: ArticleMapGraph = useMemo(() => buildArticleMapGraph(blocks), [blocks]);
    const nodes = graph.nodes;
    const links = graph.links;

    const subgraph = useMemo(
        () => (hoveredId ? collectSubgraph(graph, hoveredId) : null),
        [graph, hoveredId],
    );

    const nodeById = useMemo(() => new Map(nodes.map(n => [n.id, n] as const)), [nodes]);

    const linkAppearance = useCallback(
        (link: ArticleMapLink): { color?: number; alpha: number } => {
            if (!subgraph) return { alpha: 1 };
            if (subgraph.links.has(link.id)) {
                const src = nodeById.get(link.source_id);
                const color = src ? OUTCOME_COLORS[src.outcome] : OUTCOME_COLORS.neutral;
                return { color, alpha: 1 };
            }
            return { alpha: 0.15 };
        },
        [subgraph, nodeById],
    );

    useEffect(() => {
        if (nodes.length > 0 && viewportRef.current) {
            const minX = Math.min(...nodes.map(b => b.x));
            const maxX = Math.max(...nodes.map(b => b.x));
            const minY = Math.min(...nodes.map(b => b.y));
            const maxY = Math.max(...nodes.map(b => b.y));
            const cx = (minX + maxX) / 2;
            const cy = (minY + maxY) / 2;
            const timer = setTimeout(() => viewportRef.current?.focusOn(cx, cy), 100);
            return () => clearTimeout(timer);
        }
        return undefined;
    }, [nodes]);

    if (!nodes || nodes.length === 0) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', textAlign: 'center', padding: '2rem' }}>
                Нет структурных блоков для построения карты.<br />
                Добавьте блоки на вкладке «Редактор» и сохраните статью.
            </div>
        );
    }

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
                <div style={{ fontWeight: 600, marginBottom: 6 }}>Наведите на блок</div>
                {LEGEND.map(item => (
                    <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span style={{ width: 10, height: 10, borderRadius: 2, background: item.color, display: 'inline-block' }} />
                        <span>{item.label}</span>
                    </div>
                ))}
                <div style={{ marginTop: 6, borderTop: '1px solid #e5e7eb', paddingTop: 4 }}>
                    <span style={{ fontWeight: 600 }}>Вердикт:</span>{' '}
                    <span style={{ color: graph.studyVerdict.includes('подтвердилась') && !graph.studyVerdict.includes('не') ? '#16a34a' : graph.studyVerdict.includes('не подтвердилась') ? '#dc2626' : '#6b7280' }}>
                        {graph.studyVerdict}
                    </span>
                </div>
            </div>
        </div>
    );
};

export default ArticleMap;
