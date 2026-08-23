import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { ArticleBlockData, BlockDataValue, KnowledgeStatement } from '../../model';
import { getBlockTypeDef } from '../blockTypes';
import {
    duplicateBlock,
    insertBlock,
    moveBlock,
    removeBlocks,
    setBlockField,
    setBlockType,
    sortBlocks,
} from './blockOps';
import { buildBlockTree, buildRefIndex } from './resolveTree';
import { filterSlashCommands, type SlashCommand } from './slashCommands';
import { useWysiwygHistory } from './useWysiwygHistory';
import { WysiwygApiContext, type UuidRef, type WysiwygApi, type FieldKeyInfo } from './WysiwygContext';
import LineRow from './LineRow';
import SlashMenu from './SlashMenu';
import {
    focusFieldEl,
    queryFieldEl,
    queryLineFieldEls,
} from './focusNav';
import { useRequireAuth } from '../../../../shared/hooks/useRequireAuth';
import styles from '../../Article_editor.module.css';

interface WysiwygEditorProps {
    blocks: ArticleBlockData[];
    statements: KnowledgeStatement[];
    articleUuid?: string;
    onApply: (next: ArticleBlockData[]) => void;
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

interface SlashState {
    lineId: string;
    fieldKey: string;
    query: string;
    top: number;
    left: number;
}

interface PendingFocus {
    lineId: string;
    fieldKey?: string;
    ordinal?: number;
}

const RECENT_KEY = 'wy-recent-types';
const UIDS_KEY = 'wy-show-uids';

function loadRecent(): number[] {
    try {
        const raw = localStorage.getItem(RECENT_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw) as unknown;
        return Array.isArray(parsed) ? parsed.map(Number).filter(Number.isFinite) : [];
    } catch {
        return [];
    }
}

// Разделитель между строками: при наведении показывает линию с кнопкой «+»
// для вставки новой строки в этом месте. Абсолютное позиционирование не
// меняет высоту строк и расстояния между ними.
const InsertDivider: React.FC<{ onInsert: () => void }> = ({ onInsert }) => {
    const [hover, setHover] = useState(false);
    return (
        <div
            className={styles.wyInsertZone}
            data-wy-insert=""
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}
        >
            {hover && (
                <>
                    <span className={styles.wyInsertLine} aria-hidden="true" />
                    <button
                        type="button"
                        className={styles.wyInsertBtn}
                        title="Добавить новую строку"
                        onClick={onInsert}
                    >
                        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
                            <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                        </svg>
                    </button>
                </>
            )}
        </div>
    );
};

const WysiwygEditor: React.FC<WysiwygEditorProps> = ({
    blocks,
    statements,
    articleUuid,
    onApply,
    onUploadImage,
}) => {
    const requireAuth = useRequireAuth();
    const lines = useMemo(() => sortBlocks(blocks), [blocks]);
    const tree = useMemo(() => buildBlockTree(lines), [lines]);
    const availableRefs = useMemo<UuidRef[]>(() => {
        const index = buildRefIndex(lines, tree);
        const refs: UuidRef[] = [];
        for (const entry of index.values()) {
            refs.push({ id: entry.id, label: entry.label, chainText: entry.chainText, blockType: entry.blockType });
        }
        if (articleUuid && !index.has(articleUuid)) {
            refs.unshift({ id: articleUuid, label: articleUuid, chainText: articleUuid });
        }
        for (const s of statements) {
            if (!s.id || index.has(s.id)) continue;
            refs.push({
                id: s.id,
                label: s.subject_text ? `${s.subject_text} → ${s.predicate} → ${s.object_text}` : s.id,
                chainText: s.subject_text ? `${s.subject_text} → ${s.predicate} → ${s.object_text}` : s.id,
            });
        }
        return refs;
    }, [lines, tree, statements, articleUuid]);

    const { commit, undo, redo, canUndo, canRedo } = useWysiwygHistory({ blocks, onApply });

    const [slash, setSlash] = useState<SlashState | null>(null);
    const [selectedSlashIdx, setSelectedSlashIdx] = useState(0);
    const [recentTypes, setRecentTypes] = useState<number[]>(loadRecent);
    const [showUids, setShowUids] = useState<boolean>(() => localStorage.getItem(UIDS_KEY) === '1');
    const [focusedLineId, setFocusedLineId] = useState<string | null>(null);
    const [highlightLineId, setHighlightLineId] = useState<string | null>(null);
    const [draggingId, setDraggingId] = useState<string | null>(null);
    const [dropTarget, setDropTarget] = useState<{ id: string; side: 'before' | 'after' } | null>(null);

    const dragIdRef = useRef<string | null>(null);
    const pendingFocusRef = useRef<PendingFocus | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const highlightTimerRef = useRef<number | null>(null);
    const linesRef = useRef(lines);
    linesRef.current = lines;
    const slashRef = useRef<SlashState | null>(null);
    slashRef.current = slash;

    const virtualizer = useVirtualizer({
        count: lines.length,
        getScrollElement: () => scrollRef.current,
        estimateSize: () => 34,
        overscan: 12,
        getItemKey: (i) => lines[i].instanceId,
    });
    const virtualItems = virtualizer.getVirtualItems();

    const slashItems = useMemo(
        () => filterSlashCommands(slash?.query ?? '', recentTypes),
        [slash?.query, recentTypes],
    );

    useEffect(() => {
        setSelectedSlashIdx(0);
    }, [slash?.lineId, slash?.fieldKey]);

    useEffect(() => () => {
        if (highlightTimerRef.current !== null) window.clearTimeout(highlightTimerRef.current);
    }, []);

    const flushPendingFocus = useCallback((attempt = 0) => {
        const pending = pendingFocusRef.current;
        const rootEl = scrollRef.current;
        if (!pending || !rootEl) return;
        let el: HTMLElement | null = null;
        if (pending.fieldKey) el = queryFieldEl(rootEl, pending.lineId, pending.fieldKey);
        if (!el) {
            const fieldEls = queryLineFieldEls(rootEl, pending.lineId);
            if (fieldEls.length > 0) {
                const ordinal = Math.min(pending.ordinal ?? 0, fieldEls.length - 1);
                el = fieldEls[Math.max(0, ordinal)];
            }
        }
        if (el && focusFieldEl(el)) {
            pendingFocusRef.current = null;
            return;
        }
        if (attempt < 10) {
            requestAnimationFrame(() => flushPendingFocus(attempt + 1));
        }
    }, []);

    const requestFocus = useCallback((lineId: string, fieldKey?: string, ordinal?: number) => {
        pendingFocusRef.current = { lineId, fieldKey, ordinal };
        const idx = linesRef.current.findIndex((b) => b.instanceId === lineId);
        if (idx >= 0 && scrollRef.current) {
            virtualizer.scrollToIndex(idx, { align: 'auto' });
        }
        requestAnimationFrame(() => flushPendingFocus());
    }, [virtualizer, flushPendingFocus]);

    useEffect(() => {
        if (pendingFocusRef.current) flushPendingFocus();
    }, [virtualItems, flushPendingFocus]);

    const insertBelow = useCallback((anchorLineId: string, typeNumber?: number): void => {
        if (!requireAuth()) return;
        const currentLines = linesRef.current;
        const anchorIndex = anchorLineId
            ? currentLines.findIndex((b) => b.instanceId === anchorLineId)
            : -1;
        const afterIndex = anchorIndex >= 0 ? anchorIndex : currentLines.length - 1;
        const anchorType = currentLines[afterIndex]?.blockType;
        const anchorDef = anchorType !== undefined ? getBlockTypeDef(anchorType) : undefined;
        const newType = typeNumber ?? (anchorDef?.canAddMultiple ? anchorDef.typeNumber : 4);
        const { next, instanceId } = insertBlock(currentLines, { afterIndex, blockType: newType });
        commit(next);
        requestFocus(instanceId);
    }, [requireAuth, commit, requestFocus]);

    // Вставка новой строки по абсолютной позиции в списке. Используется
    // hover-разделителями между строками и клавишами A/B в command mode.
    const insertAtIndex = useCallback((index: number): void => {
        if (!requireAuth()) return;
        const currentLines = linesRef.current;
        const at = Math.max(0, Math.min(index, currentLines.length));
        const neighbour = currentLines[at] ?? currentLines[at - 1];
        const def = neighbour ? getBlockTypeDef(neighbour.blockType) : undefined;
        const newType = def?.canAddMultiple ? def.typeNumber : 4;
        const { next, instanceId } = insertBlock(currentLines, { afterIndex: at - 1, blockType: newType });
        commit(next);
        requestFocus(instanceId);
    }, [requireAuth, commit, requestFocus]);

    // Создаёт новую дочернюю строку прямо из uuid-list поля родителя:
    // вставляется после последнего ребёнка этого списка и сразу попадает
    // в список (отступ под родителем выводится автоматически из ссылки).
    const appendChildLine = useCallback((parentLineId: string, fieldKey: string) => {
        if (!requireAuth()) return;
        const currentLines = linesRef.current;
        const parentIdx = currentLines.findIndex((b) => b.instanceId === parentLineId);
        if (parentIdx < 0) return;
        const parentDef = getBlockTypeDef(currentLines[parentIdx].blockType);
        const fieldDef = parentDef?.fields.find((f) => f.key === fieldKey);
        const allowed = fieldDef?.uuidRefBlockTypes ?? [];
        const childType = allowed.length > 0 ? allowed[0] : 4;

        let ids: string[] = [];
        try {
            const parsed = JSON.parse(String(currentLines[parentIdx].data[fieldKey] ?? '')) as unknown;
            if (Array.isArray(parsed)) ids = parsed.map(String).filter(Boolean);
        } catch { /* пустой список */ }

        let afterIndex = parentIdx;
        for (let i = 0; i < currentLines.length; i++) {
            if (ids.includes(currentLines[i].instanceId)) afterIndex = Math.max(afterIndex, i);
        }

        const { next: withChild, instanceId } = insertBlock(currentLines, {
            afterIndex,
            blockType: childType,
        });
        commit(setBlockField(withChild, parentLineId, fieldKey, JSON.stringify([...ids, instanceId])));
        setFocusedLineId(instanceId);
        requestFocus(instanceId);
    }, [requireAuth, commit, requestFocus]);

    const removeLineById = useCallback((lineId: string) => {
        if (!requireAuth()) return;
        const currentLines = linesRef.current;
        const idx = currentLines.findIndex((b) => b.instanceId === lineId);
        const prev = idx > 0 ? currentLines[idx - 1] : null;
        commit(removeBlocks(currentLines, [lineId]));
        if (prev) requestFocus(prev.instanceId, undefined, 999);
    }, [requireAuth, commit, requestFocus]);

    const duplicateLineById = useCallback((lineId: string) => {
        if (!requireAuth()) return;
        const { next, instanceId } = duplicateBlock(linesRef.current, lineId);
        commit(next);
        requestFocus(instanceId);
    }, [requireAuth, commit, requestFocus]);

    const moveLineByDelta = useCallback((lineId: string, delta: -1 | 1) => {
        if (!requireAuth()) return;
        const currentLines = linesRef.current;
        const idx = currentLines.findIndex((b) => b.instanceId === lineId);
        if (idx < 0) return;
        const target = idx + delta;
        if (target < 0 || target >= currentLines.length) return;
        commit(moveBlock(currentLines, idx, target));
        requestFocus(lineId);
    }, [requireAuth, commit, requestFocus]);

    const jumpToLine = useCallback((lineId: string) => {
        const idx = linesRef.current.findIndex((b) => b.instanceId === lineId);
        if (idx < 0 || !scrollRef.current) return;
        virtualizer.scrollToIndex(idx, { align: 'center' });
        setHighlightLineId(lineId);
        if (highlightTimerRef.current !== null) window.clearTimeout(highlightTimerRef.current);
        highlightTimerRef.current = window.setTimeout(() => setHighlightLineId(null), 1400);
    }, [virtualizer]);

    const isLineEmpty = useCallback((lineId: string): boolean => {
        const b = linesRef.current.find((x) => x.instanceId === lineId);
        if (!b) return true;
        return Object.values(b.data).every((v) =>
            v === '' || v === false || v === null || v === undefined,
        );
    }, []);

    const applySlashCommand = useCallback((cmd: SlashCommand) => {
        const anchor = slashRef.current;
        if (!anchor) return;
        setSlash(null);

        const nextRecent = [cmd.typeNumber, ...recentTypes.filter((t) => t !== cmd.typeNumber)].slice(0, 8);
        setRecentTypes(nextRecent);
        try {
            localStorage.setItem(RECENT_KEY, JSON.stringify(nextRecent));
        } catch { /* storage unavailable */ }

        if (anchor.fieldKey === '__append__') {
            insertBelow('', cmd.typeNumber);
            return;
        }
        const convertInPlace = anchor.fieldKey === '__type__' || isLineEmpty(anchor.lineId);
        if (convertInPlace) {
            const currentLines = linesRef.current;
            let next = setBlockType(currentLines, anchor.lineId, cmd.typeNumber);
            if (anchor.fieldKey !== '__type__') {
                next = setBlockField(next, anchor.lineId, anchor.fieldKey, '');
            }
            commit(next);
            requestFocus(anchor.lineId);
        } else {
            insertBelow(anchor.lineId, cmd.typeNumber);
        }
    }, [recentTypes, isLineEmpty, commit, requestFocus, insertBelow]);

    const navigateFields = useCallback((lineId: string, fieldKey: string, dir: -1 | 1) => {
        const rootEl = scrollRef.current;
        if (!rootEl) return;
        const els = queryLineFieldEls(rootEl, lineId);
        const currentIdx = els.findIndex((el) => el.getAttribute('data-wy-field') === fieldKey);
        const nextIdx = currentIdx + dir;
        if (currentIdx >= 0 && nextIdx >= 0 && nextIdx < els.length) {
            focusFieldEl(els[nextIdx]);
            return;
        }
        const blockIdx = linesRef.current.findIndex((b) => b.instanceId === lineId);
        const targetIdx = blockIdx + dir;
        if (targetIdx < 0 || targetIdx >= linesRef.current.length) return;
        requestFocus(linesRef.current[targetIdx].instanceId, undefined, dir === 1 ? 0 : 999);
    }, [requestFocus]);

    const navigateLines = useCallback((lineId: string, fieldKey: string, dir: -1 | 1) => {
        const rootEl = scrollRef.current;
        if (!rootEl) return;
        const els = queryLineFieldEls(rootEl, lineId);
        const ordinal = els.findIndex((el) => el.getAttribute('data-wy-field') === fieldKey);
        const blockIdx = linesRef.current.findIndex((b) => b.instanceId === lineId);
        const targetIdx = blockIdx + dir;
        if (targetIdx < 0 || targetIdx >= linesRef.current.length) return;
        requestFocus(linesRef.current[targetIdx].instanceId, fieldKey, ordinal >= 0 ? ordinal : 0);
    }, [requestFocus]);

    const toggleUids = useCallback(() => {
        setShowUids((v) => {
            try { localStorage.setItem(UIDS_KEY, v ? '0' : '1'); } catch { /* ignore */ }
            return !v;
        });
    }, []);

    const fieldKeyDown = useCallback((e: React.KeyboardEvent<HTMLElement>, info: FieldKeyInfo) => {
        const mod = e.ctrlKey || e.metaKey;

        if (mod && e.shiftKey && (e.key === 'U' || e.key === 'u')) {
            e.preventDefault();
            toggleUids();
            return;
        }
        if (mod && !e.shiftKey && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            undo();
            return;
        }
        if ((mod && e.key.toLowerCase() === 'y') || (mod && e.shiftKey && e.key.toLowerCase() === 'z')) {
            e.preventDefault();
            redo();
            return;
        }
        if (mod && e.key.toLowerCase() === 'd') {
            e.preventDefault();
            duplicateLineById(info.lineId);
            return;
        }
        if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
            e.preventDefault();
            moveLineByDelta(info.lineId, e.key === 'ArrowUp' ? -1 : 1);
            return;
        }
        if (e.key === 'Escape') {
            (e.target as HTMLElement).blur();
            return;
        }
        if (e.key === 'Tab') {
            e.preventDefault();
            navigateFields(info.lineId, info.fieldKey, e.shiftKey ? -1 : 1);
            return;
        }
        if (e.key === 'Enter') {
            if (info.multiline && !mod) return;
            e.preventDefault();
            insertBelow(info.lineId);
            return;
        }
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            const target = e.target as HTMLTextAreaElement | HTMLInputElement;
            if (info.multiline) {
                const pos = target.selectionStart ?? 0;
                const firstBreak = target.value.indexOf('\n');
                const lastBreak = target.value.lastIndexOf('\n');
                if (e.key === 'ArrowUp' && pos > (firstBreak === -1 ? target.value.length + 1 : firstBreak + 1)) return;
                if (e.key === 'ArrowDown' && lastBreak !== -1 && pos < lastBreak) return;
            }
            e.preventDefault();
            navigateLines(info.lineId, info.fieldKey, e.key === 'ArrowDown' ? 1 : -1);
            return;
        }
        if (e.key === 'Backspace' && !mod && !e.altKey) {
            const target = e.target as HTMLInputElement | HTMLTextAreaElement;
            if (target.value !== '') return;
            const rootEl = scrollRef.current;
            if (!rootEl) return;
            const els = queryLineFieldEls(rootEl, info.lineId);
            if (els.length > 0 && els[0].getAttribute('data-wy-field') === info.fieldKey) {
                e.preventDefault();
                removeLineById(info.lineId);
            }
        }
    }, [toggleUids, undo, redo, duplicateLineById, moveLineByDelta, navigateFields, navigateLines, insertBelow, removeLineById]);

    useEffect(() => {
        if (!slash) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                e.stopPropagation();
                setSelectedSlashIdx((i) => Math.min(i + 1, Math.max(slashItems.length - 1, 0)));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                e.stopPropagation();
                setSelectedSlashIdx((i) => Math.max(i - 1, 0));
            } else if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                e.stopPropagation();
                const cmd = slashItems[selectedSlashIdx];
                if (cmd) applySlashCommand(cmd);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                setSlash(null);
            } else if (e.key === 'Backspace') {
                e.preventDefault();
                e.stopPropagation();
                setSlash((prev) => (prev && prev.query.length > 0 ? { ...prev, query: prev.query.slice(0, -1) } : prev));
            } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                e.stopPropagation();
                setSlash((prev) => (prev ? { ...prev, query: prev.query + e.key } : prev));
            }
        };
        const onMouseDown = (e: MouseEvent) => {
            const t = e.target as Element;
            if (!t.closest(`.${styles.wySlashMenu}`)) setSlash(null);
        };
        document.addEventListener('keydown', onKeyDown, true);
        document.addEventListener('mousedown', onMouseDown, true);
        return () => {
            document.removeEventListener('keydown', onKeyDown, true);
            document.removeEventListener('mousedown', onMouseDown, true);
        };
    }, [slash, slashItems, selectedSlashIdx, applySlashCommand]);

    const apiRef = useRef<WysiwygApi>({} as WysiwygApi);
    apiRef.current.setField = useCallback((lineId: string, fieldKey: string, value: BlockDataValue) => {
        if (!requireAuth()) return;
        commit(setBlockField(linesRef.current, lineId, fieldKey, value), `${lineId}:${fieldKey}`);
    }, [requireAuth, commit]);
    apiRef.current.requestFocus = requestFocus;
    apiRef.current.insertBelow = insertBelow;
    apiRef.current.removeLine = removeLineById;
    apiRef.current.duplicateLine = duplicateLineById;
    apiRef.current.moveLine = moveLineByDelta;
    apiRef.current.jumpToLine = jumpToLine;
    apiRef.current.openSlashMenu = useCallback(({ lineId, fieldKey, rect }: { lineId: string; fieldKey: string; rect: DOMRect | null }) => {
        setSlash({
            lineId,
            fieldKey,
            query: '',
            top: rect ? rect.bottom + 4 : 200,
            left: rect ? rect.left : 200,
        });
    }, []);
    apiRef.current.fieldKeyDown = fieldKeyDown;
    apiRef.current.appendChildLine = appendChildLine;
    apiRef.current.beginFieldEdit = useCallback((lineId: string) => {
        setFocusedLineId(lineId);
    }, []);
    apiRef.current.refs = availableRefs;
    apiRef.current.showUids = showUids;
    apiRef.current.onUploadImage = onUploadImage;

    const breadcrumbChain = useMemo(() => {
        if (!focusedLineId) return [] as Array<{ id: string; label: string }>;
        const chain = tree.chainOf.get(focusedLineId);
        if (!chain) return [];
        const labels = new Map(availableRefs.map((r) => [r.id, r.label]));
        return chain.map((id) => ({ id, label: labels.get(id) ?? id }));
    }, [focusedLineId, tree, availableRefs]);

    const handleDragOverLine = useCallback((e: React.DragEvent, instanceId: string) => {
        if (!dragIdRef.current || dragIdRef.current === instanceId) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const rect = e.currentTarget.getBoundingClientRect();
        const side: 'before' | 'after' = e.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
        setDropTarget((prev) => (prev && prev.id === instanceId && prev.side === side ? prev : { id: instanceId, side }));
    }, []);

    const handleDropLine = useCallback((e: React.DragEvent, instanceId: string) => {
        e.preventDefault();
        const fromId = dragIdRef.current;
        dragIdRef.current = null;
        setDraggingId(null);
        setDropTarget(null);
        if (!fromId || fromId === instanceId) return;
        const side: 'before' | 'after' =
            dropTarget && dropTarget.id === instanceId ? dropTarget.side : 'before';
        const currentLines = linesRef.current;
        const fromIdx = currentLines.findIndex((b) => b.instanceId === fromId);
        let toIdx = currentLines.findIndex((b) => b.instanceId === instanceId);
        if (fromIdx < 0 || toIdx < 0) return;
        if (side === 'after') toIdx += 1;
        const adjusted = fromIdx < toIdx ? toIdx - 1 : toIdx;
        if (adjusted !== fromIdx) commit(moveBlock(currentLines, fromIdx, adjusted));
    }, [dropTarget, commit]);

    const promptRowOpenSlash = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        setSlash({ lineId: '__append__', fieldKey: '__append__', query: '', top: rect.top - 4, left: rect.left });
    }, []);

    // Command mode как в Jupyter-нотбуках VSCode: когда фокус не в поле ввода,
    // клавиша A вставляет строку над текущей, B — под текущей. Текущей считается
    // последняя сфокусированная строка; без неё A/B работают с началом/концом.
    useEffect(() => {
        if (slash || draggingId) return;
        const onKeyDown = (e: KeyboardEvent): void => {
            if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
            const key = e.key.toLowerCase();
            if (key !== 'a' && key !== 'b') return;
            const target = e.target as HTMLElement | null;
            if (target instanceof HTMLInputElement
                || target instanceof HTMLTextAreaElement
                || target?.isContentEditable) return;
            e.preventDefault();
            e.stopPropagation();
            const currentLines = linesRef.current;
            const focusIdx = focusedLineId
                ? currentLines.findIndex((b) => b.instanceId === focusedLineId)
                : -1;
            if (key === 'b') {
                insertAtIndex(focusIdx >= 0 ? focusIdx + 1 : currentLines.length);
            } else {
                insertAtIndex(focusIdx >= 0 ? focusIdx : 0);
            }
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [slash, draggingId, focusedLineId, insertAtIndex]);

    return (
        <WysiwygApiContext.Provider value={apiRef.current}>
            <div className={styles.wyRoot}>
                <div className={styles.wyToolbar}>
                    <div className={styles.wyBreadcrumbs}>
                        {breadcrumbChain.length > 1 && breadcrumbChain.map((seg, i) => (
                            <React.Fragment key={seg.id}>
                                {i > 0 && <span className={styles.wyBreadcrumbSep}>→</span>}
                                <button
                                    type="button"
                                    className={`${styles.wyBreadcrumbBtn} ${seg.id === focusedLineId ? styles.wyBreadcrumbActive : ''}`}
                                    onClick={() => jumpToLine(seg.id)}
                                    title={`Перейти\nUUID: ${seg.id}`}
                                >
                                    {seg.label}
                                </button>
                            </React.Fragment>
                        ))}
                    </div>
                    <div className={styles.wyToolbarActions}>
                        <button
                            type="button"
                            className={styles.wyToolbarBtn}
                            onClick={undo}
                            disabled={!canUndo}
                            title="Отменить (Ctrl+Z)"
                        >
                            ↶
                        </button>
                        <button
                            type="button"
                            className={styles.wyToolbarBtn}
                            onClick={redo}
                            disabled={!canRedo}
                            title="Повторить (Ctrl+Y)"
                        >
                            ↷
                        </button>
                        <button
                            type="button"
                            className={`${styles.wyToolbarBtn} ${showUids ? styles.wyToolbarBtnOn : ''}`}
                            onClick={toggleUids}
                            title="Показать UUID всех утверждений (Ctrl+Shift+U)"
                        >
                            #
                        </button>
                    </div>
                </div>
                <div className={styles.wyScroller} ref={scrollRef} tabIndex={-1}>
                    <div className={styles.wyDoc}>
                        {lines.length === 0 ? (
                            <div className={styles.wyEmptyState}>
                                <p>Структурных строк пока нет.</p>
                                <button type="button" className={styles.wyPromptBtn} onClick={promptRowOpenSlash}>
                                    Нажмите <b>/</b> или щёлкните здесь, чтобы добавить первую строку
                                </button>
                            </div>
                        ) : (
                            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
                                {virtualItems.map((vi) => {
                                    const block = lines[vi.index];
                                    return (
                                        <React.Fragment key={vi.key}>
                                            {!draggingId && (
                                                <div
                                                    style={{
                                                        position: 'absolute',
                                                        top: vi.start,
                                                        left: 0,
                                                        width: '100%',
                                                        zIndex: 5,
                                                        transform: 'translateY(-50%)',
                                                    }}
                                                >
                                                    <InsertDivider onInsert={() => insertAtIndex(vi.index)} />
                                                </div>
                                            )}
                                            <div
                                                data-index={vi.index}
                                                ref={virtualizer.measureElement}
                                                style={{
                                                    position: 'absolute',
                                                    top: 0,
                                                    left: 0,
                                                    width: '100%',
                                                    transform: `translateY(${vi.start}px)`,
                                                }}
                                            >
                                                <LineRow
                                                    block={block}
                                                    depth={tree.depthOf.get(block.instanceId) ?? 0}
                                                    chainText={availableRefs.find((r) => r.id === block.instanceId)?.chainText}
                                                    showUids={showUids}
                                                    dragging={draggingId === block.instanceId}
                                                    dropSide={dropTarget?.id === block.instanceId ? dropTarget.side : null}
                                                    highlight={highlightLineId === block.instanceId}
                                                    focused={focusedLineId === block.instanceId}
                                                    onDragStartLine={(id) => { dragIdRef.current = id; setDraggingId(id); }}
                                                    onDragEndLine={() => { dragIdRef.current = null; setDraggingId(null); setDropTarget(null); }}
                                                    onDragOverLine={handleDragOverLine}
                                                    onDropLine={handleDropLine}
                                                />
                                            </div>
                                        </React.Fragment>
                                    );
                                })}
                                {virtualItems.some((vi) => vi.index === lines.length - 1) && !draggingId && (
                                    <div
                                        style={{
                                            position: 'absolute',
                                            top: virtualizer.getTotalSize(),
                                            left: 0,
                                            width: '100%',
                                            zIndex: 5,
                                            transform: 'translateY(-50%)',
                                        }}
                                    >
                                        <InsertDivider onInsert={() => insertAtIndex(lines.length)} />
                                    </div>
                                )}
                            </div>
                        )}
                        <div className={styles.wyPromptRow}>
                            <button type="button" className={styles.wyPromptBtn} onClick={promptRowOpenSlash}>
                                + Введите / для команды
                            </button>
                        </div>
                    </div>
                </div>
                {slash && (
                    <SlashMenu
                        items={slashItems}
                        selectedIdx={selectedSlashIdx}
                        top={slash.top}
                        left={slash.left}
                        onSelect={applySlashCommand}
                        onHover={setSelectedSlashIdx}
                    />
                )}
            </div>
        </WysiwygApiContext.Provider>
    );
};

export default React.memo(WysiwygEditor);
