import { useCallback, useRef, useState } from 'react';
import type { ArticleBlockData } from '../../model';

const COALESCE_MS = 800;

interface HistoryCell {
    past: ArticleBlockData[][];
    future: ArticleBlockData[][];
    lastEditKey: string | null;
    lastEditTime: number;
}

export interface WysiwygHistory {
    commit: (next: ArticleBlockData[], coalesceKey?: string) => void;
    undo: () => void;
    redo: () => void;
    canUndo: boolean;
    canRedo: boolean;
}

interface Args {
    blocks: ArticleBlockData[];
    onApply: (next: ArticleBlockData[]) => void;
}

export function useWysiwygHistory({ blocks, onApply }: Args): WysiwygHistory {
    const cellRef = useRef<HistoryCell>({ past: [], future: [], lastEditKey: null, lastEditTime: 0 });
    const blocksRef = useRef(blocks);
    blocksRef.current = blocks;
    const [version, setVersion] = useState(0);

    const commit = useCallback((next: ArticleBlockData[], coalesceKey?: string) => {
        const cell = cellRef.current;
        const now = Date.now();
        const coalesce = !!coalesceKey
            && cell.lastEditKey === coalesceKey
            && now - cell.lastEditTime < COALESCE_MS;
        if (!coalesce) {
            cell.past = [...cell.past.slice(-99), blocksRef.current];
            cell.future = [];
        }
        cell.lastEditKey = coalesceKey ?? null;
        cell.lastEditTime = now;
        onApply(next);
        setVersion((v) => v + 1);
    }, [onApply]);

    const undo = useCallback(() => {
        const cell = cellRef.current;
        if (cell.past.length === 0) return;
        const snapshot = cell.past[cell.past.length - 1];
        cell.past = cell.past.slice(0, -1);
        cell.future = [...cell.future, blocksRef.current];
        cell.lastEditKey = null;
        onApply(snapshot);
        setVersion((v) => v + 1);
    }, [onApply]);

    const redo = useCallback(() => {
        const cell = cellRef.current;
        if (cell.future.length === 0) return;
        const snapshot = cell.future[cell.future.length - 1];
        cell.future = cell.future.slice(0, -1);
        cell.past = [...cell.past, blocksRef.current];
        cell.lastEditKey = null;
        onApply(snapshot);
        setVersion((v) => v + 1);
    }, [onApply]);

    return {
        commit,
        undo,
        redo,
        canUndo: version >= 0 && cellRef.current.past.length > 0,
        canRedo: version >= 0 && cellRef.current.future.length > 0,
    };
}
