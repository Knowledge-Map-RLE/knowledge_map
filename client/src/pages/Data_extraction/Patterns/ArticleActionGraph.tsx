import React, { useEffect, useState } from 'react';
import { getConfirmedActionGraph } from '../../../services/api';
import type { BlockData, LinkData } from '../../../widgets/KnowledgeMap';
import { computeActionGraphLayout } from './actionGraphLayout';
import Knowledge_mapUI from '../../Knowledge_map';

interface Props {
    docId: string;
}

export function ArticleActionGraph({ docId }: Props) {
    const [blocks, setBlocks] = useState<BlockData[] | null>(null);
    const [links, setLinks] = useState<LinkData[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setLoading(true);
        setError(null);
        setBlocks(null);
        setLinks(null);
        getConfirmedActionGraph(docId)
            .then(resp => {
                const { blocks: b, links: l } = computeActionGraphLayout(resp.nodes, resp.edges);
                setBlocks(b);
                setLinks(l);
            })
            .catch(e => setError(e.message ?? 'Ошибка загрузки графа'))
            .finally(() => setLoading(false));
    }, [docId]);

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280' }}>
                Загрузка графа действий...
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
                Нет подтверждённых связей.<br />
                Подтвердите связи во вкладке «Паттерны», чтобы увидеть граф.
            </div>
        );
    }

    return (
        <div style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
            <Knowledge_mapUI externalBlocks={blocks} externalLinks={links ?? []} embedded />
        </div>
    );
}
