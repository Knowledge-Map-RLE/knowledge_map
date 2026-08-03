import React, { useState, useCallback, useRef, useMemo } from 'react';
import type { ArticleBlockData, KnowledgeStatement } from '../model';
import { BLOCK_TYPES, getBlockTypeDef } from './blockTypes';
import StructuredBlockItem from './StructuredBlockItem';
import type { UuidRef } from './FieldInput';
import styles from '../Article_editor.module.css';

// Block types that contain uuid-ref / pair-list / uuid-list fields. Only these
// consume the `availableUuids` list, so passing it to every item would break
// React.memo for all blocks on each keystroke.
const UUID_FIELD_TYPES: ReadonlySet<number> = new Set(
    BLOCK_TYPES
        .filter((t) => t.fields.some((f) => f.inputType === 'uuid-ref' || f.inputType === 'pair-list' || f.inputType === 'uuid-list'))
        .map((t) => t.typeNumber),
);

interface StructuredBlockEditorProps {
    blocks: ArticleBlockData[];
    onAddBlock: (typeNumber: number) => void;
    onDeleteBlock: (instanceId: string) => void;
    onUpdateBlock: (instanceId: string, fieldKey: string, value: string | boolean) => void;
    onReorderBlocks: (fromIndex: number, toIndex: number) => void;
    highlightBlockId?: string | null;
    articleUuid?: string;
    statements?: KnowledgeStatement[];
    onBlurSave?: () => void;
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

const StructuredBlockEditor: React.FC<StructuredBlockEditorProps> = ({
    blocks, onAddBlock, onDeleteBlock, onUpdateBlock, onReorderBlocks,
    highlightBlockId = null, articleUuid, statements = [], onBlurSave, onUploadImage,
}) => {
    const [showAddMenu, setShowAddMenu] = useState(false);
    const [dragIndex, setDragIndex] = useState<number | null>(null);
    const [menuFilter, setMenuFilter] = useState('');
    const listRef = useRef<HTMLDivElement>(null);
    const menuRef = useRef<HTMLDivElement>(null);
    const prevUuidsRef = useRef<UuidRef[] | null>(null);

    const sortedBlocks = useMemo(
        () => [...blocks].sort((a, b) => a.order - b.order),
        [blocks],
    );

    const typeCounts = useMemo(() => {
        const counts = new Map<number, number>();
        const indices = new Map<number, number>();
        for (const b of sortedBlocks) {
            const c = (counts.get(b.blockType) || 0) + 1;
            counts.set(b.blockType, c);
        }
        for (const b of sortedBlocks) {
            const prev = indices.get(b.blockType) || 0;
            indices.set(b.blockType, prev);
        }
        return counts;
    }, [sortedBlocks]);

    const typeCurrentIndex = useMemo(() => {
        const map = new Map<string, number>();
        const counters = new Map<number, number>();
        for (const b of sortedBlocks) {
            const c = counters.get(b.blockType) || 0;
            map.set(b.instanceId, c);
            counters.set(b.blockType, c + 1);
        }
        return map;
    }, [sortedBlocks]);

    const filteredTypes = useMemo(() => {
        if (!menuFilter.trim()) return BLOCK_TYPES;
        const q = menuFilter.toLowerCase();
        return BLOCK_TYPES.filter(
            (t) => t.name.toLowerCase().includes(q) || String(t.typeNumber).includes(q),
        );
    }, [menuFilter]);

    // Only rebuild the ref list when its content actually changes; otherwise
    // keep the previous array reference so React.memo on items holds.
    // Identity (id/blockType) drives the reference; labels are refreshed lazily
    // so that typing in a field does not re-render every uuid-ref block.
    const availableUuids = useMemo<UuidRef[] | undefined>(() => {
        const seen = new Set<string>();
        const ids: { id: string; blockType?: number }[] = [];
        if (articleUuid && !seen.has(articleUuid)) {
            seen.add(articleUuid);
            ids.push({ id: articleUuid });
        }
        for (const s of statements) {
            if (!s.id || seen.has(s.id)) continue;
            seen.add(s.id);
            ids.push({ id: s.id });
        }
        for (const b of blocks) {
            if (seen.has(b.instanceId)) continue;
            seen.add(b.instanceId);
            ids.push({ id: b.instanceId, blockType: b.blockType });
        }
        const prev = prevUuidsRef.current;
        if (prev && prev.length === ids.length) {
            let same = true;
            for (let i = 0; i < ids.length; i++) {
                if (prev[i].id !== ids[i].id || prev[i].blockType !== ids[i].blockType) { same = false; break; }
            }
            if (same) return prev;
        }
        // Id-set changed — rebuild with fresh labels.
        const seenL = new Set<string>();
        const refs: UuidRef[] = [];
        if (articleUuid && !seenL.has(articleUuid)) {
            seenL.add(articleUuid);
            refs.push({ id: articleUuid, label: articleUuid });
        }
        for (const s of statements) {
            if (!s.id || seenL.has(s.id)) continue;
            seenL.add(s.id);
            const label = s.subject_text
                ? `${s.subject_text} → ${s.predicate} → ${s.object_text}`
                : s.id;
            refs.push({ id: s.id, label });
        }
        for (const b of blocks) {
            if (seenL.has(b.instanceId)) continue;
            seenL.add(b.instanceId);
            const def = getBlockTypeDef(b.blockType);
            const prefix = def ? `T${def.typeNumber}: ${def.name}` : b.instanceId;
            const s = typeof b.data.subject === 'string' ? b.data.subject : '';
            const p = typeof b.data.predicate === 'string' ? b.data.predicate : '';
            const o = typeof b.data.object === 'string' ? b.data.object : '';
            let summary = '';
            if (s || p || o) {
                summary = `${s || '?'} → ${p || '?'} → ${o || '?'}`;
            } else if (def) {
                const nameField = def.fields.find(f =>
                    (f.inputType === 'text' || f.inputType === 'textarea') &&
                    typeof b.data[f.key] === 'string' && (b.data[f.key] as string).trim(),
                );
                if (nameField) summary = b.data[nameField.key] as string;
            }
            refs.push({ id: b.instanceId, label: summary ? `${prefix}. ${summary}` : prefix, blockType: b.blockType });
        }
        prevUuidsRef.current = refs;
        return refs;
    }, [articleUuid, statements, blocks]);

    const handleDragStart = useCallback((index: number) => {
        setDragIndex(index);
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }, []);

    const handleDrop = useCallback((targetIndex: number) => {
        if (dragIndex !== null && dragIndex !== targetIndex) {
            onReorderBlocks(dragIndex, targetIndex);
        }
        setDragIndex(null);
    }, [dragIndex, onReorderBlocks]);

    const handleAddClick = useCallback(() => {
        setShowAddMenu((prev) => !prev);
        setMenuFilter('');
    }, []);

    const handleSelectType = useCallback((typeNumber: number) => {
        onAddBlock(typeNumber);
        setShowAddMenu(false);
        setMenuFilter('');
    }, [onAddBlock]);

    const handleMenuFilterChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        setMenuFilter(e.target.value);
    }, []);

    const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
        e.stopPropagation();
    }, []);

    return (
        <div className={styles.sbeRoot}>
            <div className={styles.sbeToolbar}>
                <button
                    className={styles.sbeAddBtn}
                    onClick={handleAddClick}
                    title="Добавить блок"
                >
                    + Добавить блок
                </button>
                <span className={styles.sbeCount}>
                    {sortedBlocks.length > 0 ? `${sortedBlocks.length} блоков` : ''}
                </span>
            </div>

            {showAddMenu && (
                <div className={styles.sbeAddMenu} ref={menuRef}>
                    <input
                        type="text"
                        className={styles.sbeMenuFilter}
                        placeholder="Фильтр..."
                        value={menuFilter}
                        onChange={handleMenuFilterChange}
                        onKeyDown={handleMenuKeyDown}
                        autoFocus
                    />
                    <div className={styles.sbeMenuList}>
                        {filteredTypes.map((t) => (
                            <button
                                key={t.typeNumber}
                                className={styles.sbeMenuItem}
                                onClick={() => handleSelectType(t.typeNumber)}
                                title={t.description}
                            >
                                <span
                                    className={styles.sbeMenuItemBadge}
                                    style={{ background: t.color + '20', color: t.color }}
                                >
                                    {t.icon} {t.typeNumber}
                                </span>
                                <span className={styles.sbeMenuItemName}>{t.name}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            <div className={styles.sbeList} ref={listRef}>
                {sortedBlocks.length === 0 && (
                    <div className={styles.sbeEmpty}>
                        Нажмите &laquo;Добавить блок&raquo; для начала работы
                    </div>
                )}

                {sortedBlocks.map((block, i) => (
                    <StructuredBlockItem
                        key={block.instanceId}
                        block={block}
                        index={i}
                        totalBlocks={sortedBlocks.length}
                        sameTypeCount={typeCounts.get(block.blockType) || 1}
                        sameTypeIndex={typeCurrentIndex.get(block.instanceId) || 0}
                        isHighlighted={block.instanceId === highlightBlockId}
                        onChange={onUpdateBlock}
                        onDragStart={handleDragStart}
                        onDragOver={handleDragOver}
                        onDrop={handleDrop}
                        onDelete={onDeleteBlock}
                        availableUuids={UUID_FIELD_TYPES.has(block.blockType) ? availableUuids : undefined}
                        onBlurSave={onBlurSave}
                        onUploadImage={onUploadImage}
                    />
                ))}
            </div>
        </div>
    );
};

export default React.memo(StructuredBlockEditor);
