import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { BlockFieldDef } from '../../model';
import { isUuid } from './resolveTree';
import type { UuidRef } from './WysiwygContext';
import styles from '../../Article_editor.module.css';

interface RefChipProps {
    lineId: string;
    fieldKey: string;
    value: string;
    field: BlockFieldDef;
    refs: UuidRef[];
    compact?: boolean;
    onEnterEmpty?: () => void;
    onEscapeEmpty?: () => void;
    onChange: (value: string) => void;
    onJumpTo: (lineId: string) => void;
}

function shortId(id: string): string {
    return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

const RefChip: React.FC<RefChipProps> = ({ lineId, fieldKey, value, field, refs, compact, onEnterEmpty, onEscapeEmpty, onChange, onJumpTo }) => {
    const [query, setQuery] = useState<string | null>(null);
    const [selectedIdx, setSelectedIdx] = useState(0);
    const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
    const wrapRef = useRef<HTMLSpanElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const resolved = useMemo(() => {
        if (!value) return null;
        return refs.find((r) => r.id === value) ?? null;
    }, [value, refs]);

    const orphaned = !!value && !resolved && isUuid(value);

    const displayValue = useMemo(() => {
        if (resolved) return compact || !resolved.chainText || resolved.chainText === resolved.label
            ? resolved.label
            : resolved.chainText;
        return value;
    }, [resolved, value, compact]);

    const candidates = useMemo(() => {
        let pool = refs;
        if (field.uuidRefBlockTypes && field.uuidRefBlockTypes.length > 0) {
            const allowed = new Set(field.uuidRefBlockTypes);
            pool = pool.filter((r) => r.blockType !== undefined && allowed.has(r.blockType));
        }
        if (value) pool = pool.filter((r) => r.id !== value);
        const q = (query ?? '').trim().toLowerCase();
        if (!q) return pool.slice(0, 40);
        const lower = pool.map((r) => ({
            ref: r,
            hay: `${r.label} ${r.chainText ?? ''} ${r.id}`.toLowerCase(),
        }));
        return lower.filter((x) => x.hay.includes(q)).slice(0, 40).map((x) => x.ref);
    }, [refs, field.uuidRefBlockTypes, query, value]);

    useEffect(() => {
        setSelectedIdx(0);
    }, [query]);

    const openDropdown = useCallback(() => {
        setQuery('');
        const el = wrapRef.current;
        if (el) {
            const r = el.getBoundingClientRect();
            setRect({ top: r.bottom + 2, left: Math.min(r.left, window.innerWidth - 340), width: Math.max(r.width, 300) });
        }
    }, []);

    const closeDropdown = useCallback(() => {
        setQuery(null);
        setRect(null);
    }, []);

    const pick = useCallback((ref: UuidRef) => {
        onChange(ref.id);
        closeDropdown();
        inputRef.current?.blur();
    }, [onChange, closeDropdown]);

    useEffect(() => {
        if (rect === null) return;
        const handler = (e: MouseEvent) => {
            if (wrapRef.current && !wrapRef.current.contains(e.target as Node)
                && !(e.target instanceof Element && e.target.closest(`.${styles.wyDropdown}`))) {
                closeDropdown();
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [rect, closeDropdown]);

    const isEmpty = !displayValue;

    return (
        <span className={styles.wyRefWrap} ref={wrapRef}>
            <input
                ref={inputRef}
                data-wy-line={lineId}
                data-wy-field={fieldKey}
                type="text"
                className={`${styles.wyChipInput} ${isEmpty ? styles.wyChipEmpty : ''} ${orphaned ? styles.wyChipOrphan : ''}`}
                value={query !== null ? query : displayValue}
                placeholder={field.placeholder ?? 'ссылка'}
                title={orphaned
                    ? `Ссылка на несуществующую строку\nUUID: ${value}`
                    : resolved
                        ? `UUID: ${value}`
                        : undefined}
                onChange={(e) => {
                    setQuery(e.target.value);
                    if (query === null) openDropdown();
                    if (resolved) onChange('');
                    else onChange(e.target.value);
                }}
                onFocus={() => { if (rect === null) openDropdown(); }}
                onBlur={() => {
                    if (query !== null && query.trim() && !resolved) onChange(query.trim());
                    closeDropdown();
                }}
                onKeyDown={(e) => {
                    if (rect !== null) {
                        if (e.key === 'ArrowDown') {
                            e.preventDefault();
                            setSelectedIdx((i) => Math.min(i + 1, candidates.length - 1));
                            return;
                        }
                        if (e.key === 'ArrowUp') {
                            e.preventDefault();
                            setSelectedIdx((i) => Math.max(i - 1, 0));
                            return;
                        }
                        if (e.key === 'Enter' && candidates[selectedIdx]) {
                            e.preventDefault();
                            e.stopPropagation();
                            pick(candidates[selectedIdx]);
                            return;
                        }
                        if (e.key === 'Escape') {
                            e.stopPropagation();
                            closeDropdown();
                            return;
                        }
                    }
                    if (e.key === 'Enter' && query === null && !value && onEnterEmpty) {
                        e.preventDefault();
                        e.stopPropagation();
                        onEnterEmpty();
                        return;
                    }
                    if (e.key === 'Escape' && query === null && !value && onEscapeEmpty) {
                        e.preventDefault();
                        e.stopPropagation();
                        onEscapeEmpty();
                        return;
                    }
                    if ((e.key === 'Backspace' || e.key === 'Delete') && resolved && query === null) {
                        e.preventDefault();
                        onChange('');
                    }
                }}
            />
            {resolved && (
                <button
                    type="button"
                    className={styles.wyChipJump}
                    title={`Перейти к утверждению\nUUID: ${value}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => onJumpTo(value)}
                >
                    ↗
                </button>
            )}
            {rect !== null && createPortal(
                <div
                    className={styles.wyDropdown}
                    style={{ position: 'fixed', top: rect.top, left: rect.left, width: rect.width }}
                >
                    {candidates.length === 0 && <div className={styles.wyDropdownEmpty}>Ничего не найдено</div>}
                    {candidates.map((ref, idx) => (
                        <button
                            key={ref.id}
                            type="button"
                            className={`${styles.wyDropdownItem} ${idx === selectedIdx ? styles.wyDropdownItemActive : ''}`}
                            onMouseEnter={() => setSelectedIdx(idx)}
                            onMouseDown={(e) => { e.preventDefault(); pick(ref); }}
                        >
                            <span className={styles.wyDropdownChain}>{ref.chainText ?? ref.label}</span>
                            <span className={styles.wyDropdownId}>{shortId(ref.id)}</span>
                        </button>
                    ))}
                </div>,
                document.body,
            )}
        </span>
    );
};

export default React.memo(RefChip);
