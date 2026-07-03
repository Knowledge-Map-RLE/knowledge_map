import React, { useEffect, useState } from 'react';
import { getArticleGraph } from '../../../services/api/article_editor';
import type { BlockData, LinkData } from '../../../widgets/KnowledgeMap/types/types';

interface ArticleMapProps {
    docId: string;
}

const SPACING_X = 300;
const SPACING_Y = 120;

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
            x: col * SPACING_X,
            y: row * SPACING_Y,
            layer: col,
            level: 0,
        };
    });

    const links: LinkData[] = edges
        .filter(e => stmtMap.has(e.source_id) && stmtMap.has(e.target_id))
        .map(e => ({
            id: `${e.source_id}-${e.target_id}`,
            source_id: e.source_id,
            target_id: e.target_id,
        }));

    return { blocks, links };
}

const ArticleMap: React.FC<ArticleMapProps> = ({ docId }) => {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [blocks, setBlocks] = useState<BlockData[] | null>(null);
    const [links, setLinks] = useState<LinkData[] | null>(null);

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

    const maxX = Math.max(...blocks.map(b => b.x), 1);
    const maxY = Math.max(...blocks.map(b => b.y), 1);

    return (
        <svg width="100%" height="100%" style={{ background: '#f8fafc' }}>
            <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                    <polygon points="0 0, 10 3.5, 0 7" fill="#6366f1" />
                </marker>
            </defs>
            {links?.map(link => {
                const src = blocks?.find(b => b.id === link.source_id);
                const tgt = blocks?.find(b => b.id === link.target_id);
                if (!src || !tgt) return null;
                return (
                    <line
                        key={link.id}
                        x1={src.x + 100} y1={src.y + 30}
                        x2={tgt.x + 100} y2={tgt.y}
                        stroke="#6366f1" strokeWidth="2"
                        markerEnd="url(#arrowhead)"
                    />
                );
            })}
            {blocks?.map(block => (
                <g key={block.id}>
                    <rect
                        x={block.x} y={block.y}
                        width="200" height="60" rx="8"
                        fill="white" stroke="#6366f1" strokeWidth="2"
                    />
                    <text
                        x={block.x + 100} y={block.y + 20}
                        textAnchor="middle" fill="#059669"
                        fontSize="11" fontWeight="600"
                    >
                        {block.title.split(' → ')[0]?.slice(0, 25)}
                    </text>
                    <text
                        x={block.x + 100} y={block.y + 35}
                        textAnchor="middle" fill="#6366f1"
                        fontSize="10" fontStyle="italic"
                    >
                        {block.title.split(' → ')[1]?.slice(0, 25)}
                    </text>
                    <text
                        x={block.x + 100} y={block.y + 50}
                        textAnchor="middle" fill="#d97706"
                        fontSize="11" fontWeight="600"
                    >
                        {block.title.split(' → ')[2]?.slice(0, 25)}
                    </text>
                </g>
            ))}
        </svg>
    );
};

export default ArticleMap;
