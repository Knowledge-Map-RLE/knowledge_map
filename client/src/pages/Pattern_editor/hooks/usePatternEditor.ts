import { useCallback, useState } from 'react';
import type { Connection, PatternBlockInstance, Port, CanConnectResult } from '../model';
import { genId, isPortCompatible } from '../model';

export interface PatternGraphPayload {
    nodes: {
        id: string;
        required_type: string;
        text_constraint: string;
        predicate_constraint: string;
    }[];
    edges: {
        source_id: string;
        target_id: string;
        required_edge_type: string;
        predicate_constraint: string;
    }[];
}

export interface UsePatternEditorReturn {
    blocks: PatternBlockInstance[];
    connections: Connection[];
    selectedBlockId: string | null;
    addBlock: (type: PatternBlockInstance['type'], x: number, y: number) => void;
    updateBlockPosition: (id: string, x: number, y: number) => void;
    updateBlockText: (id: string, text: string) => void;
    removeBlock: (id: string) => void;
    connectPorts: (sourcePort: Port, targetPort: Port) => { connected: boolean; reason?: string };
    disconnect: (connectionId: string) => void;
    selectBlock: (id: string | null) => void;
    toGraphPayload: () => PatternGraphPayload;
    reset: () => void;
}

const BLOCK_SIZES: Record<string, { width: number; height: number }> = {
    statement: { width: 180, height: 70 },
    concept: { width: 100, height: 60 },
    literal: { width: 120, height: 80 },
    relation: { width: 130, height: 60 },
    negation: { width: 90, height: 70 },
    context: { width: 140, height: 80 },
};

export function usePatternEditor(): UsePatternEditorReturn {
    const [blocks, setBlocks] = useState<PatternBlockInstance[]>([]);
    const [connections, setConnections] = useState<Connection[]>([]);
    const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

    const addBlock = useCallback((type: PatternBlockInstance['type'], x: number, y: number) => {
        const size = BLOCK_SIZES[type] ?? { width: 140, height: 60 };
        setBlocks((prev) => [
            ...prev,
            {
                id: genId(`block-${type}`),
                type,
                x,
                y,
                width: size.width,
                height: size.height,
                text: '',
            },
        ]);
    }, []);

    const updateBlockPosition = useCallback((id: string, x: number, y: number) => {
        setBlocks((prev) => prev.map((b) => (b.id === id ? { ...b, x, y } : b)));
    }, []);

    const updateBlockText = useCallback((id: string, text: string) => {
        setBlocks((prev) => prev.map((b) => (b.id === id ? { ...b, text } : b)));
    }, []);

    const removeBlock = useCallback((id: string) => {
        setBlocks((prev) => prev.filter((b) => b.id !== id));
        setConnections((prev) =>
            prev.filter((c) => !c.sourcePortId.startsWith(id) && !c.targetPortId.startsWith(id))
        );
    }, []);

    const connectPorts = useCallback(
        (sourcePort: Port, targetPort: Port) => {
            const result = isPortCompatible(sourcePort, targetPort);
            if (!result.compatible) {
                return { connected: false, reason: result.reason };
            }

            const exists = connections.some(
                (c) =>
                    (c.sourcePortId === sourcePort.id && c.targetPortId === targetPort.id) ||
                    (c.sourcePortId === targetPort.id && c.targetPortId === sourcePort.id)
            );
            if (exists) {
                return { connected: false, reason: 'Связь уже существует' };
            }

            setConnections((prev) => [
                ...prev,
                { id: genId('conn'), sourcePortId: sourcePort.id, targetPortId: targetPort.id },
            ]);
            return { connected: true };
        },
        [connections]
    );

    const disconnect = useCallback((connectionId: string) => {
        setConnections((prev) => prev.filter((c) => c.id !== connectionId));
    }, []);

    const selectBlock = useCallback((id: string | null) => {
        setSelectedBlockId(id);
    }, []);

    const toGraphPayload = useCallback(() => {
        const byId = (id: string) => blocks.find((b) => id.startsWith(b.id));
        const isRelation = (b?: PatternBlockInstance) => b?.type === 'relation';

        // «Связь» (relation) переносится с узла на ребро как предикат.
        // Остальные типы: concept/literal/statement — строгий тип; negation/context — тип all (wildcard) + текст.
        const nodes = blocks
            .filter((b) => b.type !== 'relation')
            .map((b) => ({
                id: b.id,
                required_type: b.type === 'concept' || b.type === 'literal' || b.type === 'statement' ? b.type : '',
                text_constraint: b.text || '',
                predicate_constraint: b.predicate || '',
            }));

        const edges = connections
            .map((c) => {
                const src = byId(c.sourcePortId);
                const tgt = byId(c.targetPortId);
                if (!src || !tgt) return null;

                let effectiveSrc = src;
                let effectiveTgt = tgt;
                let predicate = '';

                const feederOf = (rid: string, skipConnectionId: string) => {
                    const feed = connections.find(
                        (c2) => c2.id !== skipConnectionId && c2.targetPortId.startsWith(rid)
                    );
                    return feed ? byId(feed.sourcePortId) : undefined;
                };
                const outletOf = (rid: string, skipConnectionId: string) => {
                    const out = connections.find(
                        (c2) => c2.id !== skipConnectionId && c2.sourcePortId.startsWith(rid)
                    );
                    return out ? byId(out.targetPortId) : undefined;
                };

                if (isRelation(src) && isRelation(tgt)) return null;

                if (isRelation(src)) {
                    const subject = feederOf(src.id, c.id);
                    if (!subject) return null;
                    effectiveSrc = subject;
                    predicate = src.text || '';
                    if (isRelation(tgt)) {
                        const object = outletOf(tgt.id, c.id);
                        if (!object) return null;
                        effectiveTgt = object;
                    } else {
                        effectiveTgt = tgt;
                    }
                } else if (isRelation(tgt)) {
                    const object = outletOf(tgt.id, c.id);
                    if (!object) return null;
                    effectiveTgt = object;
                    predicate = tgt.text || '';
                }

                if (effectiveSrc.id === effectiveTgt.id) return null;

                return {
                    source_id: effectiveSrc.id,
                    target_id: effectiveTgt.id,
                    required_edge_type: 'RELATES_TO',
                    predicate_constraint: predicate,
                };
            })
            .filter((e): e is NonNullable<typeof e> => e !== null)
            // Убираем дубликаты (source,target): оставляем ребро с заполненным предикатом, иначе первое
            .filter((e, i, arr) => {
                const dups = arr
                    .map((o, j) => ({ o, j }))
                    .filter(({ o }) => o.source_id === e.source_id && o.target_id === e.target_id);
                if (dups.length === 1) return true;
                const withPred = dups.find(({ o }) => o.predicate_constraint);
                return withPred ? withPred.j === i : dups[0].j === i;
            });

        return { nodes, edges };
    }, [blocks, connections]);

    const reset = useCallback(() => {
        setBlocks([]);
        setConnections([]);
        setSelectedBlockId(null);
    }, []);

    return {
        blocks,
        connections,
        selectedBlockId,
        addBlock,
        updateBlockPosition,
        updateBlockText,
        removeBlock,
        connectPorts,
        disconnect,
        selectBlock,
        toGraphPayload,
        reset,
    };
}
