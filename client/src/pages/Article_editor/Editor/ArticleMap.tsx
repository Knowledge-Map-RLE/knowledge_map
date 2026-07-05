import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, Link } from '../../../widgets/KnowledgeMap';
import type { ViewportRef, BlockData, LinkData } from '../../../widgets/KnowledgeMap';
import { BLOCK_WIDTH } from '../../../widgets/KnowledgeMap/constants';
import { ArticleBlock } from './ArticleBlock';
import { getArticleGraph } from '../../../services/api/article_editor';

extend({ Container, Graphics, Text });

interface ArticleMapProps {
    docId: string;
}

const SPACING_X = 300;
const SPACING_Y = 120;
const PADDING = 60;

function computeTopoLayout(
    statements: { uid: string; subject_text: string; predicate: string; object_text: string }[],
    edges: { source_id: string; target_id: string }[]
): { blocks: BlockData[]; links: LinkData[] } {
    if (statements.length === 0) return { blocks: [], links: [] };

    const ids = statements.map(s => s.uid);
    const inDegree: Record<string, number> = {};
    const outNeighbors: Record<string, string[]> = {};
    for (const id of ids) {
        inDegree[id] = 0;
        outNeighbors[id] = [];
    }
    for (const e of edges) {
        if (inDegree[e.target_id] !== undefined && inDegree[e.source_id] !== undefined) {
            outNeighbors[e.source_id].push(e.target_id);
            inDegree[e.target_id] += 1;
        }
    }

    const column: Record<string, number> = {};
    const queue: string[] = [];
    for (const id of ids) {
        if (inDegree[id] === 0) {
            queue.push(id);
            column[id] = 0;
        }
    }

    const remaining = { ...inDegree };
    while (queue.length > 0) {
        const cur = queue.shift()!;
        for (const nb of outNeighbors[cur]) {
            column[nb] = Math.max(column[nb] ?? 0, (column[cur] ?? 0) + 1);
            remaining[nb] -= 1;
            if (remaining[nb] === 0) queue.push(nb);
        }
    }

    for (const id of ids) {
        if (column[id] === undefined) column[id] = 0;
    }

    const rowInColumn: Record<string, number> = {};
    const colCount: Record<number, number> = {};
    for (const id of ids) {
        const col = column[id] ?? 0;
        rowInColumn[id] = colCount[col] ?? 0;
        colCount[col] = (colCount[col] ?? 0) + 1;
    }

    const stmtMap = new Map(statements.map(s => [s.uid, s]));
    const blocks: BlockData[] = statements.map(s => {
        const col = column[s.uid] ?? 0;
        const row = rowInColumn[s.uid] ?? 0;
        return {
            id: s.uid,
            title: `${s.subject_text} → ${s.predicate} → ${s.object_text}`,
            x: col * SPACING_X + PADDING + BLOCK_WIDTH / 2,
            y: row * SPACING_Y + PADDING + 37.5,
            layer: col,
            level: 0,
        };
    });

    const linkMap = new Map<string, LinkData>();
    for (const e of edges) {
        if (!stmtMap.has(e.source_id) || !stmtMap.has(e.target_id)) continue;
        const id = `${e.source_id}-${e.target_id}`;
        if (!linkMap.has(id)) {
            linkMap.set(id, { id, source_id: e.source_id, target_id: e.target_id });
        }
    }
    const links = [...linkMap.values()];

    return { blocks, links };
}

const ArticleMap: React.FC<ArticleMapProps> = ({ docId }) => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [blocks, setBlocks] = useState<BlockData[] | null>(null);
    const [links, setLinks] = useState<LinkData[] | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerEl, setContainerEl] = useState<HTMLElement | null>(null);
    const viewportRef = useRef<ViewportRef>(null);
    const containerCbRef = useCallback((el: HTMLDivElement | null) => {
        containerRef.current = el;
        if (el) setContainerEl(el);
    }, []);

    useEffect(() => {
        setLoading(true);
        setError(null);
        getArticleGraph(docId)
            .then(data => {
                const { blocks: b, links: l } = computeTopoLayout(data.statements || [], data.edges || []);
                setBlocks(b);
                setLinks(l);
            })
            .catch(e => setError(e.message ?? 'Failed to load graph'))
            .finally(() => setLoading(false));
    }, [docId]);

    useEffect(() => {
        if (blocks && blocks.length > 0 && viewportRef.current) {
            const minX = Math.min(...blocks.map(b => b.x));
            const maxX = Math.max(...blocks.map(b => b.x));
            const minY = Math.min(...blocks.map(b => b.y));
            const maxY = Math.max(...blocks.map(b => b.y));
            const cx = (minX + maxX) / 2;
            const cy = (minY + maxY) / 2;
            setTimeout(() => viewportRef.current?.focusOn(cx, cy), 100);
        }
    }, [blocks]);

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280' }}>
                Загрузка графа...
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#ef4444' }}>
                Ошибка: {error}
            </div>
        );
    }

    if (!blocks || blocks.length === 0) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', textAlign: 'center', padding: '2rem' }}>
                Нет утверждений для построения графа.<br />
                Добавьте текст на вкладке «Редактор» и сохраните утверждения.
            </div>
        );
    }

    return (
        <div ref={containerCbRef} style={{ width: '100%', height: '100%' }}>
            {containerEl && (
                <Application resizeTo={containerEl} backgroundColor={0xf8fafc}>
                    <Viewport ref={viewportRef}>
                        {links.map(link => (
                            <Link
                                key={link.id}
                                linkData={link}
                                blocks={blocks}
                                isSelected={false}
                                onClick={() => {}}
                            />
                        ))}
                        {blocks.map(block => (
                            <ArticleBlock key={block.id} blockData={block} />
                        ))}
                    </Viewport>
                </Application>
            )}
        </div>
    );
};

export default ArticleMap;
