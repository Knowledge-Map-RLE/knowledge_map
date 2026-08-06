import React, { useCallback, useRef, useEffect, useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import type { BlockFieldDef, BlockDataValue } from '../model';
import { withBase } from '../../../services/api/http';
import { deleteArticleImage } from '../../../services/api/article_editor';
import styles from '../Article_editor.module.css';

export interface UuidRef {
    id: string;
    label: string;
    blockType?: number;
}

interface FieldInputProps {
    field: BlockFieldDef;
    value: BlockDataValue;
    onChange: (key: string, value: string | boolean) => void;
    availableUuids?: UuidRef[];
    compact?: boolean;
    onBlurSave?: () => void;
    noClear?: boolean;
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

const UuidRefInput: React.FC<{
    field: BlockFieldDef;
    value: string;
    availableUuids: UuidRef[];
    onChange: (key: string, value: string | boolean) => void;
    labelText: React.ReactNode;
    compact?: boolean;
    onBlurSave?: () => void;
    noClear?: boolean;
}> = ({ field, value, availableUuids, onChange, labelText, compact = false, onBlurSave, noClear }) => {
    const [query, setQuery] = useState<string | null>(null);
    const [open, setOpen] = useState(false);
    const wrapRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null);

    const updatePosition = useCallback(() => {
        if (inputRef.current) {
            const rect = inputRef.current.getBoundingClientRect();
            setDropdownPos({ top: rect.bottom + 2, left: rect.left, width: rect.width });
        }
    }, []);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    useEffect(() => {
        if (open) updatePosition();
    }, [open, updatePosition]);

    useEffect(() => {
        if (!open) return;
        const handler = () => updatePosition();
        window.addEventListener('scroll', handler, true);
        window.addEventListener('resize', handler);
        return () => {
            window.removeEventListener('scroll', handler, true);
            window.removeEventListener('resize', handler);
        };
    }, [open, updatePosition]);

    const matched = useMemo(() => {
        let candidates = availableUuids;
        if (field.uuidRefBlockTypes && field.uuidRefBlockTypes.length > 0) {
            candidates = candidates.filter(
                (u) => u.blockType !== undefined && field.uuidRefBlockTypes!.includes(u.blockType),
            );
        }
        const q = (query ?? '').toLowerCase();
        if (!q) return candidates;
        return candidates.filter(
            (u) => u.id.toLowerCase().includes(q) || u.label.toLowerCase().includes(q),
        );
    }, [query, availableUuids, field.uuidRefBlockTypes]);

    const displayLabel = useMemo(() => {
        const found = availableUuids.find((u) => u.id === value);
        return found ? found.label : '';
    }, [value, availableUuids]);

    const fieldGroupClass = compact ? styles.fieldGroupInline : styles.fieldGroup;

    const showClear = false;

    return (
        <div className={fieldGroupClass} ref={wrapRef}>
            {labelText}
            <div className={styles.uuidRefWrap}>
                <input
                    ref={inputRef}
                    type="text"
                    className={styles.fieldInput}
                    value={value || query || ''}
                    placeholder={field.placeholder}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setOpen(true);
                        if (displayLabel) {
                            onChange(field.key, '');
                        } else {
                            onChange(field.key, e.target.value);
                        }
                    }}
                    onFocus={() => { setOpen(true); updatePosition(); }}
                    onBlur={() => {
                        if (query && !value) onChange(field.key, query);
                        onBlurSave?.();
                    }}
                />
                {showClear && (
                    <button
                        className={styles.uuidRefClear}
                        onClick={() => { onChange(field.key, ''); setQuery(''); }}
                        title="\u041E\u0447\u0438\u0441\u0442\u0438\u0442\u044C"
                    >
                        &times;
                    </button>
                )}
                {open && matched.length > 0 && dropdownPos && createPortal(
                    <div
                        className={styles.uuidRefDropdown}
                        style={{ position: 'fixed', top: dropdownPos.top, left: dropdownPos.left, width: dropdownPos.width }}
                    >
                        {matched.map((u) => (
                            <button
                                key={u.id}
                                className={`${styles.uuidRefOption} ${u.id === value ? styles.uuidRefSelected : ''}`}
                                onMouseDown={(e) => { e.preventDefault(); onChange(field.key, u.id); setQuery(''); setOpen(false); }}
                            >
                                <span className={styles.uuidRefOptionLabel}>{u.label}</span>
                            </button>
                        ))}
                    </div>,
                    document.body,
                )}
            </div>
        </div>
    );
};

const arrowBtnStyle: React.CSSProperties = {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: '#6b7280',
    fontSize: 12,
    lineHeight: 1,
    padding: '2px 6px',
};

const ImageUploadInput: React.FC<{
    field: BlockFieldDef;
    value: string;
    onChange: (key: string, value: string | boolean) => void;
    onUploadImage?: (key: string, file: File) => Promise<string>;
    onBlurSave?: () => void;
    labelText: React.ReactNode;
}> = ({ field, value, onChange, onUploadImage, onBlurSave, labelText }) => {
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const handleFile = useCallback(async (file: File) => {
        if (!onUploadImage) return;
        setUploading(true);
        setError(null);
        try {
            const objectKey = await onUploadImage(field.key, file);
            if (objectKey) {
                if (value && value !== objectKey) {
                    deleteArticleImage(value).catch(() => { /* orphan cleanup */ });
                }
                onChange(field.key, objectKey);
                onBlurSave?.();
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setUploading(false);
        }
    }, [field.key, onChange, onUploadImage, onBlurSave, value]);

    const handleRemove = useCallback(() => {
        if (value) {
            deleteArticleImage(value).catch(() => { /* orphan cleanup */ });
        }
        onChange(field.key, '');
    }, [value, onChange]);

    const previewUrl = value
        ? withBase(`/api/article_editor/images/${value.split('/').map(encodeURIComponent).join('/')}`)
        : '';

    return (
        <div className={styles.fieldGroup}>
            {labelText}
            <div className={styles.imageUploadWrap}>
                {previewUrl ? (
                    <div className={styles.imageUploadPreview}>
                        <img src={previewUrl} alt={field.label} className={styles.imageUploadImg} />
                        <div className={styles.imageUploadActions}>
                            <button
                                type="button"
                                className={styles.imageUploadBtn}
                                onClick={() => fileRef.current?.click()}
                                disabled={uploading}
                            >
                                {uploading ? 'Загрузка...' : 'Заменить'}
                            </button>
                            <button
                                type="button"
                                className={styles.imageUploadBtnDanger}
                                onClick={handleRemove}
                            >
                                Удалить
                            </button>
                        </div>
                    </div>
                ) : (
                    <button
                        type="button"
                        className={styles.imageUploadBtn}
                        onClick={() => fileRef.current?.click()}
                        disabled={uploading}
                    >
                        {uploading ? 'Загрузка...' : 'Загрузить изображение'}
                    </button>
                )}
                <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleFile(f);
                        e.target.value = '';
                    }}
                />
                {error && <div className={styles.imageUploadError}>{error}</div>}
                {field.helpText && <div className={styles.fieldHelp}>{field.helpText}</div>}
            </div>
        </div>
    );
};

const AUTO_SIZE_SUPPORTED =
    typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('field-sizing', 'content');

const FieldInput: React.FC<FieldInputProps> = ({ field, value, onChange, availableUuids = [], compact = false, onBlurSave, noClear, onUploadImage }) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const skipAutoResizeRef = useRef(true);

    useEffect(() => {
        // Auto-height is handled by `field-sizing: content` in CSS (no forced reflow).
        // Fallback for browsers without support: resize only on user input, never on mount.
        if (AUTO_SIZE_SUPPORTED || skipAutoResizeRef.current) {
            skipAutoResizeRef.current = false;
            return;
        }
        const el = textareaRef.current;
        if (!el || typeof value !== 'string' || value.length === 0) return;
        if (el.scrollHeight <= el.clientHeight + 1) return;
        el.style.height = 'auto';
        el.style.height = `${el.scrollHeight}px`;
    }, [value]);

    const handleTextChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
            onChange(field.key, e.target.value);
        },
        [field.key, onChange],
    );

    const handleCheckChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            onChange(field.key, e.target.checked);
        },
        [field.key, onChange],
    );

    const handleBlur = useCallback(() => {
        onBlurSave?.();
    }, [onBlurSave]);

    const labelText = (
        <label className={styles.fieldLabel}>
            {field.label}
            {field.required && <span style={{ color: '#dc2626', marginLeft: 2 }}>*</span>}
        </label>
    );

    const fieldGroupClass = compact ? styles.fieldGroupInline : styles.fieldGroup;

    switch (field.inputType) {
        case 'text':
            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <input
                        type="text"
                        className={styles.fieldInput}
                        value={typeof value === 'string' ? value : ''}
                        onChange={handleTextChange}
                        placeholder={field.placeholder}
                        style={compact ? { minWidth: 0 } : undefined}
                        onBlur={handleBlur}
                    />
                </div>
            );

        case 'textarea':
            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <textarea
                        ref={textareaRef}
                        className={styles.fieldTextarea}
                        value={typeof value === 'string' ? value : ''}
                        onChange={handleTextChange}
                        placeholder={field.placeholder}
                        rows={2}
                        onBlur={handleBlur}
                    />
                </div>
            );

        case 'number':
            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <input
                        type="number"
                        className={styles.fieldInput}
                        value={typeof value === 'number' ? String(value) : typeof value === 'string' ? value : ''}
                        onChange={handleTextChange}
                        placeholder={field.placeholder}
                        step="any"
                        onBlur={handleBlur}
                    />
                </div>
            );

        case 'checkbox':
            return (
                <div className={`${styles.fieldGroup} ${styles.fieldGroupInline}`}>
                    <label className={styles.fieldCheckboxLabel}>
                        <input
                            type="checkbox"
                            checked={value === true}
                            onChange={handleCheckChange}
                        />
                        <span>{field.label}</span>
                    </label>
                </div>
            );

        case 'select':
            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <select
                        className={styles.fieldSelect}
                        value={typeof value === 'string' ? value : ''}
                        onChange={handleTextChange}
                        onBlur={handleBlur}
                    >
                        <option value="">---</option>
                        {field.options?.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                </div>
            );

        case 'key-value-list': {
            const kvDisplay = (() => {
                if (typeof value === 'string') return value;
                if (value && typeof value === 'object') {
                    return Object.entries(value)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join('\n');
                }
                return '';
            })();
            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <textarea
                        ref={textareaRef}
                        className={styles.fieldTextarea}
                        value={kvDisplay}
                        onChange={handleTextChange}
                        placeholder={field.placeholder}
                        rows={3}
                        onBlur={handleBlur}
                    />
                </div>
            );
        }

        case 'tag-list': {
            const rawValue = typeof value === 'string' ? value : '';
            const items = rawValue
                ? rawValue.split(/[\n,;]/).map((s: string) => s.trim())
                : [''];

            const commit = (next: string[]) => {
                onChange(field.key, next.join('\n'));
            };

            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <div className={styles.tagList}>
                        {items.map((item: string, idx: number) => (
                            <div key={idx} className={styles.tagListItem}>
                                <input
                                    type="text"
                                    className={styles.tagListInput}
                                    value={item}
                                    placeholder={field.placeholder}
                                    onChange={(e) => {
                                        const next = [...items];
                                        next[idx] = e.target.value;
                                        commit(next);
                                    }}
                                    onPaste={(e) => {
                                        const text = e.clipboardData.getData('text');
                                        if (text.includes(',') || text.includes(';')) {
                                            e.preventDefault();
                                            const parts = (text.includes(';') ? text : text)
                                                .split(/[,;]/)
                                                .map((s: string) => s.trim())
                                                .filter(Boolean);
                                            if (parts.length > 1) {
                                                const next = [...items];
                                                next.splice(idx, 1, ...parts);
                                                commit(next);
                                            }
                                        }
                                    }}
                                    onBlur={handleBlur}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            e.preventDefault();
                                            const next = [...items];
                                            next.splice(idx + 1, 0, '');
                                            commit(next);
                                        }
                                        if (e.key === 'Backspace' && item === '' && items.length > 1) {
                                            e.preventDefault();
                                            const next = items.filter((_: string, i: number) => i !== idx);
                                            commit(next);
                                        }
                                    }}
                                />
                                <button
                                    className={styles.tagListRemove}
                                    onClick={() => {
                                        const next = items.filter((_: string, i: number) => i !== idx);
                                        commit(next.length > 0 ? next : ['']);
                                    }}
                                    title="Удалить"
                                >
                                    &times;
                                </button>
                            </div>
                        ))}
                        <button
                            className={styles.tagListAdd}
                            onClick={() => commit([...items, ''])}
                            title={`Добавить ${field.label.toLowerCase()}`}
                        >
                            +
                        </button>
                    </div>
                </div>
            );
        }

        case 'uuid-ref':
            return (
                <UuidRefInput
                    field={field}
                    value={typeof value === 'string' ? value : ''}
                    availableUuids={availableUuids}
                    onChange={onChange}
                    labelText={labelText}
                    compact={compact}
                    onBlurSave={onBlurSave}
                    noClear={noClear}
                />
            );

        case 'pair-list': {
            const rawValue = typeof value === 'string' ? value : '';
            let pairs: Array<{ groupRef: string; interventionRef: string }> = [];
            try { const p = JSON.parse(rawValue); if (Array.isArray(p)) pairs = p; } catch {}
            if (!pairs.length) pairs = [{ groupRef: '', interventionRef: '' }];

            const setPairs = (next: typeof pairs) =>
                onChange(field.key, JSON.stringify(next.length ? next : [{ groupRef: '', interventionRef: '' }]));

            const updatePair = (idx: number, key: 'groupRef' | 'interventionRef', val: string) => {
                const next = [...pairs];
                next[idx] = { ...next[idx], [key]: val };
                setPairs(next);
            };

            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {pairs.map((pair, idx) => (
                            <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <UuidRefInput
                                        field={{ key: `${field.key}_${idx}_group`, label: 'Группа', inputType: 'uuid-ref', placeholder: 'ссылка на T55', uuidRefBlockTypes: field.pairGroupBlockTypes }}
                                        value={pair.groupRef}
                                        availableUuids={availableUuids}
                                        onChange={(_k, v) => updatePair(idx, 'groupRef', typeof v === 'string' ? v : '')}
                                        labelText={<label style={{ fontSize: 11, color: '#666' }}>Группа</label>}
                                        compact
                                        onBlurSave={onBlurSave}
                                        noClear
                                    />
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <UuidRefInput
                                        field={{ key: `${field.key}_${idx}_interv`, label: 'Интервенция', inputType: 'uuid-ref', placeholder: 'T18 (опционально)', uuidRefBlockTypes: field.pairInterventionBlockTypes }}
                                        value={pair.interventionRef}
                                        availableUuids={availableUuids}
                                        onChange={(_k, v) => updatePair(idx, 'interventionRef', typeof v === 'string' ? v : '')}
                                        labelText={<label style={{ fontSize: 11, color: '#666' }}>Интервенция</label>}
                                        compact
                                        onBlurSave={onBlurSave}
                                        noClear
                                    />
                                </div>
                                <button
                                    type="button"
                                    onClick={() => {
                                        const next = pairs.filter((_, i) => i !== idx);
                                        setPairs(next);
                                    }}
                                    style={{
                                        marginTop: 20,
                                        background: 'none',
                                        border: 'none',
                                        cursor: 'pointer',
                                        color: '#ef4444',
                                        fontSize: 18,
                                        padding: '2px 6px',
                                        flexShrink: 0,
                                    }}
                                    title="Удалить пару"
                                >
                                    &times;
                                </button>
                            </div>
                        ))}
                        <button
                            type="button"
                            onClick={() => setPairs([...pairs, { groupRef: '', interventionRef: '' }])}
                            style={{
                                alignSelf: 'flex-start',
                                background: '#22c55e',
                                color: '#fff',
                                border: 'none',
                                borderRadius: 4,
                                padding: '4px 12px',
                                cursor: 'pointer',
                                fontSize: 13,
                                fontWeight: 600,
                            }}
                        >
                            + Добавить пару
                        </button>
                    </div>
                </div>
            );
        }

        case 'uuid-list': {
            const rawValue = typeof value === 'string' ? value : '';
            let uuids: string[] = [];
            try { const p = JSON.parse(rawValue); if (Array.isArray(p)) uuids = p.map(String); } catch {}
            if (!uuids.length) uuids = [''];

            const setUuids = (next: string[]) =>
                onChange(field.key, JSON.stringify(next.length ? next : ['']));

            const move = (idx: number, dir: -1 | 1) => {
                const target = idx + dir;
                if (target < 0 || target >= uuids.length) return;
                const next = [...uuids];
                [next[idx], next[target]] = [next[target], next[idx]];
                setUuids(next);
            };

            return (
                <div className={fieldGroupClass}>
                    {labelText}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {uuids.map((uuid, idx) => (
                            <div key={idx} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <UuidRefInput
                                        field={{ key: `${field.key}_${idx}`, label: `${field.label} ${idx + 1}`, inputType: 'uuid-ref', placeholder: field.placeholder ? `${field.placeholder} ${idx + 1}` : `Элемент ${idx + 1}`, uuidRefBlockTypes: field.uuidRefBlockTypes }}
                                        value={uuid}
                                        availableUuids={availableUuids}
                                        onChange={(_k, v) => { const next = [...uuids]; next[idx] = typeof v === 'string' ? v : ''; setUuids(next); }}
                                        labelText={<label style={{ fontSize: 11, color: '#666' }}>{idx + 1}.</label>}
                                        compact
                                        onBlurSave={onBlurSave}
                                        noClear
                                    />
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 18 }}>
                                    <button
                                        type="button"
                                        onClick={() => move(idx, -1)}
                                        disabled={idx === 0}
                                        title="Вверх"
                                        style={arrowBtnStyle}
                                    >&#8593;</button>
                                    <button
                                        type="button"
                                        onClick={() => move(idx, 1)}
                                        disabled={idx === uuids.length - 1}
                                        title="Вниз"
                                        style={arrowBtnStyle}
                                    >&#8595;</button>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => {
                                        const next = uuids.filter((_, i) => i !== idx);
                                        setUuids(next);
                                    }}
                                    style={{ marginTop: 20, background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', fontSize: 18, padding: '2px 6px', flexShrink: 0 }}
                                    title="Удалить"
                                >
                                    &times;
                                </button>
                            </div>
                        ))}
                        <button
                            type="button"
                            onClick={() => setUuids([...uuids, ''])}
                            style={{ alignSelf: 'flex-start', background: '#22c55e', color: '#fff', border: 'none', borderRadius: 4, padding: '4px 12px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
                        >
                            + {field.addLabel || 'Добавить шаг'}
                        </button>
                    </div>
                </div>
            );
        }

        case 'image-upload':
            return (
                <ImageUploadInput
                    field={field}
                    value={typeof value === 'string' ? value : ''}
                    onChange={onChange}
                    onUploadImage={onUploadImage}
                    onBlurSave={onBlurSave}
                    labelText={labelText}
                />
            );

        default:
            return null;
    }
};

export default React.memo(FieldInput);
