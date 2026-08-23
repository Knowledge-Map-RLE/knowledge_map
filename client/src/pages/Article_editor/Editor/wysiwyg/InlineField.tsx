import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { BlockDataValue, BlockFieldDef } from '../../model';
import { withBase } from '../../../../services/api/http';
import { useWysiwygApi } from './WysiwygContext';
import RefChip from './RefChip';
import { useAutoWidth } from './useAutoWidth';
import styles from '../../Article_editor.module.css';

interface InlineFieldProps {
    lineId: string;
    field: BlockFieldDef;
    value: BlockDataValue;
}

const HIERARCHY_SEPS = new Set(['sequence', 'steps', 'findings']);

function parseJsonArray(value: BlockDataValue): string[] {
    if (typeof value !== 'string' || !value.trim()) return [];
    try {
        const parsed = JSON.parse(value) as unknown;
        if (!Array.isArray(parsed)) return [];
        return parsed.map((v) => String(v));
    } catch {
        return [];
    }
}

const InlineField: React.FC<InlineFieldProps> = ({ lineId, field, value }) => {
    const api = useWysiwygApi();
    const [editingTagIdx, setEditingTagIdx] = useState<number | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    const str = typeof value === 'string'
        ? value
        : typeof value === 'number' ? String(value) : '';

    const autoRef = useAutoWidth(str);

    const onChange = useCallback((v: BlockDataValue) => {
        api.setField(lineId, field.key, v);
    }, [api, lineId, field.key]);

    const textChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        onChange(e.target.value);
    }, [onChange]);

    const keyDown = useCallback((e: React.KeyboardEvent<HTMLElement>, multiline: boolean) => {
        if (e.key === '/' && (e.target as HTMLInputElement).value === '') {
            e.preventDefault();
            e.stopPropagation();
            const rect = (e.target as HTMLElement).getBoundingClientRect();
            api.openSlashMenu({ lineId, fieldKey: field.key, rect });
            return;
        }
        api.fieldKeyDown(e, { lineId, fieldKey: field.key, multiline });
    }, [api, lineId, field.key]);

    const onFocus = useCallback(() => {
        api.beginFieldEdit(lineId, field.key);
    }, [api, lineId, field.key]);

    useEffect(() => {
        const el = textareaRef.current;
        if (!el || 'fieldSizing' in el.style) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 480)}px`;
    });

    const commonProps = {
        'data-wy-line': lineId,
        'data-wy-field': field.key,
        onFocus,
        title: `${field.label}${field.helpText ? ` — ${field.helpText}` : ''}`,
    };

    switch (field.inputType) {
        case 'text':
            return (
                <span className={styles.wyWord}>
                    <input
                        {...commonProps}
                        ref={autoRef}
                        type="text"
                        className={styles.wyInputProse}
                        value={str}
                        placeholder={field.placeholder ?? field.label}
                        onChange={textChange}
                        onKeyDown={(e) => keyDown(e, false)}
                    />
                </span>
            );

        case 'textarea':
            return (
                <span className={`${styles.wyWord} ${styles.wyBlockField}`}>
                    <textarea
                        {...commonProps}
                        ref={textareaRef}
                        rows={1}
                        className={styles.wyTextareaProse}
                        value={str}
                        placeholder={field.placeholder ?? field.label}
                        onChange={textChange}
                        onKeyDown={(e) => keyDown(e, true)}
                    />
                </span>
            );

        case 'number':
            return (
                <span className={styles.wyWord}>
                    <input
                        {...commonProps}
                        ref={autoRef}
                        type="number"
                        step="any"
                        className={styles.wyInputProse}
                        value={str}
                        placeholder={field.placeholder ?? field.label}
                        onChange={textChange}
                        onKeyDown={(e) => keyDown(e, false)}
                    />
                </span>
            );

        case 'select':
            return (
                <span className={styles.wyWord}>
                    <span className={styles.wySelectWrap}>
                        <select
                            {...commonProps}
                            className={`${styles.wySelectProse} ${str ? '' : styles.wySelectEmpty}`}
                            value={str}
                            onChange={(e) => onChange(e.target.value)}
                            onKeyDown={(e) => keyDown(e, false)}
                        >
                            <option value="">{field.placeholder ?? `— ${field.label} —`}</option>
                            {field.options?.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                    </span>
                </span>
            );

        case 'checkbox': {
            const checked = value === true || value === 'true';
            return (
                <button
                    type="button"
                    {...commonProps}
                    className={`${styles.wyCheckQuiet} ${checked ? styles.wyCheckQuietOn : ''}`}
                    onClick={() => { onChange(!checked); api.beginFieldEdit(lineId, field.key); }}
                    onKeyDown={(e) => keyDown(e, false)}
                >
                    <span className={styles.wyCheckMark}>{checked ? '✓' : '○'}</span>
                    {field.label}
                </button>
            );
        }

        case 'uuid-ref':
            return (
                <span className={styles.wyWord}>
                    <RefChip
                        lineId={lineId}
                        fieldKey={field.key}
                        value={str}
                        field={field}
                        refs={api.refs}
                        onChange={onChange}
                        onJumpTo={api.jumpToLine}
                    />
                </span>
            );

        case 'uuid-list': {
            const items = parseJsonArray(value);
            const setItems = (next: string[]) => onChange(JSON.stringify(next));
            const sep = HIERARCHY_SEPS.has(field.key) ? '→' : ',';
            return (
                <span
                    className={styles.wyListBare}
                    onClick={(e) => {
                        if (e.target !== e.currentTarget || items[items.length - 1] === '') return;
                        setItems([...items, '']);
                        api.requestFocus(lineId, `${field.key}#${items.length}`);
                    }}
                >
                    {items.map((id, idx) => (
                        <React.Fragment key={`${idx}-${id}`}>
                            {idx > 0 && <span className={styles.wyListSep}>{sep}</span>}
                            <span className={styles.wyListItemBare}>
                                <span className={styles.wyListNum}>{idx + 1}</span>
                                <RefChip
                                    lineId={lineId}
                                    fieldKey={`${field.key}#${idx}`}
                                    value={id}
                                    field={{ ...field, placeholder: field.placeholder ?? 'ссылка' }}
                                    refs={api.refs}
                                    compact
                                    onEnterEmpty={() => {
                                        setItems([...items, '']);
                                        api.requestFocus(lineId, `${field.key}#${items.length}`);
                                    }}
                                    onEscapeEmpty={() => {
                                        setItems(items.filter((_, i) => i !== idx).filter(Boolean));
                                        api.requestFocus(lineId, `${field.key}#${Math.max(idx - 1, 0)}`);
                                    }}
                                    onChange={(v) => {
                                        const next = [...items];
                                        next[idx] = v;
                                        setItems(next);
                                    }}
                                    onJumpTo={api.jumpToLine}
                                />
                                <button
                                    type="button"
                                    className={styles.wyListItemX}
                                    title="Убрать"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                        setItems(items.filter((_, i) => i !== idx).filter(Boolean));
                                    }}
                                >×</button>
                            </span>
                        </React.Fragment>
                    ))}
                    <button
                        type="button"
                        className={styles.wyListAddGhost}
                        title={`Создать новую строку «${field.placeholder ?? field.label}» с отступом здесь`}
                        onClick={() => api.appendChildLine(lineId, field.key)}
                    >
                        + {field.placeholder ?? field.label ?? 'добавить'}
                    </button>
                </span>
            );
        }

        case 'pair-list': {
            let pairs: Array<{ groupRef: string; interventionRef: string }> = [];
            try {
                const parsed = JSON.parse(typeof value === 'string' ? value : '') as unknown;
                if (Array.isArray(parsed)) pairs = parsed as typeof pairs;
            } catch { /* empty */ }
            const setPairs = (next: Array<{ groupRef: string; interventionRef: string }>) =>
                onChange(JSON.stringify(next.filter((p) => p.groupRef || p.interventionRef)));
            const shown = pairs.length > 0 ? pairs : [];
            return (
                <span className={styles.wyListBare}>
                    {shown.map((pair, idx) => (
                        <React.Fragment key={idx}>
                            {idx > 0 && <span className={styles.wyListSep}>;</span>}
                            <span className={styles.wyListItemBare}>
                                <RefChip
                                    lineId={lineId}
                                    fieldKey={`${field.key}#${idx}g`}
                                    value={pair.groupRef}
                                    compact
                                    field={{ ...field, key: `${field.key}_${idx}_group`, placeholder: 'группа', uuidRefBlockTypes: field.pairGroupBlockTypes }}
                                    refs={api.refs}
                                    onChange={(v) => { const next = [...shown]; next[idx] = { ...next[idx], groupRef: v }; setPairs(next); }}
                                    onJumpTo={api.jumpToLine}
                                />
                                <span className={styles.wyListSep}>+</span>
                                <RefChip
                                    lineId={lineId}
                                    fieldKey={`${field.key}#${idx}i`}
                                    value={pair.interventionRef}
                                    compact
                                    field={{ ...field, key: `${field.key}_${idx}_interv`, placeholder: 'интервенция', uuidRefBlockTypes: field.pairInterventionBlockTypes }}
                                    refs={api.refs}
                                    onChange={(v) => { const next = [...shown]; next[idx] = { ...next[idx], interventionRef: v }; setPairs(next); }}
                                    onJumpTo={api.jumpToLine}
                                />
                                <button type="button" className={styles.wyListItemX} title="Убрать пару" onClick={() => setPairs(shown.filter((_, i) => i !== idx))}>×</button>
                            </span>
                        </React.Fragment>
                    ))}
                    <button
                        type="button"
                        className={styles.wyListAddGhost}
                        onClick={() => setPairs([...pairs, { groupRef: '', interventionRef: '' }])}
                    >
                        + пара группа/интервенция
                    </button>
                </span>
            );
        }

        case 'text-list': {
            const items = str ? str.split('\n') : [];
            const shown = items.length > 0 ? items : [''];
            const isEmptyList = shown.length === 1 && shown[0] === '';
            // Сохраняем как есть: пустой элемент — промежуточное состояние
            // при вводе нового автора; чистка пустых происходит в onBlur.
            const setItems = (next: string[]) => onChange(next.join('\n'));
            const insertAfter = (idx: number) => {
                setItems([...shown.slice(0, idx + 1), '', ...shown.slice(idx + 1)]);
                api.requestFocus(lineId, `${field.key}#${idx + 1}`);
            };
            const removeAt = (idx: number) => {
                const next = shown.filter((_, i) => i !== idx);
                onChange(next.length > 0 ? next.map((s) => s.trim()).filter(Boolean).join('\n') : '');
                api.requestFocus(lineId, `${field.key}#${Math.max(idx - 1, 0)}`);
            };
            return (
                <span className={styles.wyListBare}>
                    {shown.map((item, idx) => (
                        <React.Fragment key={idx}>
                            {idx > 0 && <span className={styles.wyListSep}>,</span>}
                            <span className={styles.wyListItemBare}>
                                <input
                                    {...commonProps}
                                    data-wy-field={`${field.key}#${idx}`}
                                    type="text"
                                    className={styles.wyInputProse}
                                    style={{ width: `${Math.max(item.length, 3)}ch` }}
                                    value={item}
                                    placeholder={isEmptyList ? (field.placeholder ?? field.label) : undefined}
                                    onChange={(e) => {
                                        const next = [...shown];
                                        next[idx] = e.target.value;
                                        setItems(next);
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === ',' || e.key === 'Enter') {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            insertAfter(idx);
                                            return;
                                        }
                                        if ((e.key === 'Backspace' || e.key === 'Delete') && item === '') {
                                            e.preventDefault();
                                            removeAt(idx);
                                            return;
                                        }
                                        keyDown(e, false);
                                    }}
                                    onBlur={() => {
                                        const cleaned = shown.map((s) => s.trim()).filter(Boolean);
                                        onChange(cleaned.length > 0 ? cleaned.join('\n') : '');
                                    }}
                                />
                                <button
                                    type="button"
                                    className={styles.wyListItemX}
                                    title="Убрать"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => removeAt(idx)}
                                >×</button>
                            </span>
                        </React.Fragment>
                    ))}
                    <button
                        type="button"
                        className={styles.wyListAddGhost}
                        title={`Добавить ${field.label.toLowerCase()}`}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                            const lastIdx = shown.length - 1;
                            setItems([...shown.slice(0, lastIdx + 1).map((s) => s.trim()).filter(Boolean), '']);
                            api.requestFocus(lineId, `${field.key}#${lastIdx + 1}`);
                        }}
                    >
                        + {field.placeholder ?? field.label}
                    </button>
                </span>
            );
        }

        case 'tag-list':
        case 'key-value-list': {
            const isKv = field.inputType === 'key-value-list';
            const raw = typeof value === 'string'
                ? value
                : value && typeof value === 'object' && !Array.isArray(value)
                    ? Object.entries(value as Record<string, unknown>).map(([k, v]) => `${k}: ${v}`).join('\n')
                    : '';
            const items = raw.split('\n').map((s) => s.trim()).filter(Boolean);
            const commit = (next: string[]) => onChange(next.join('\n'));
            return (
                <span className={styles.wyListBare}>
                    {items.map((item, idx) => editingTagIdx === idx ? (
                        <input
                            key={idx}
                            autoFocus
                            {...commonProps}
                            type="text"
                            className={styles.wyTagEdit}
                            defaultValue={item}
                            placeholder={isKv ? 'ключ: значение' : field.placeholder}
                            onBlur={(e) => {
                                const v = e.target.value.trim();
                                const next = [...items];
                                if (v) next[idx] = v; else next.splice(idx, 1);
                                commit(next);
                                setEditingTagIdx(null);
                            }}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    (e.target as HTMLInputElement).blur();
                                }
                                if (e.key === 'Escape') {
                                    setEditingTagIdx(null);
                                }
                                keyDown(e, false);
                            }}
                        />
                    ) : (
                        <span
                            key={idx}
                            {...commonProps}
                            tabIndex={0}
                            className={styles.wyTagItem}
                            role="button"
                            onClick={() => setEditingTagIdx(idx)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setEditingTagIdx(idx); }
                                keyDown(e, false);
                            }}
                        >
                            {item}
                            <button
                                type="button"
                                className={styles.wyListItemX}
                                title="Убрать"
                                onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
                                onClick={(e) => { e.stopPropagation(); commit(items.filter((_, i) => i !== idx)); }}
                            >×</button>
                        </span>
                    ))}
                    <input
                        {...commonProps}
                        type="text"
                        className={styles.wyTagAddInput}
                        placeholder={items.length === 0 ? (field.placeholder ?? field.label) : '+'}
                        size={items.length === 0 ? Math.max((field.placeholder ?? field.label).length, 6) : 1}
                        onBlur={(e) => {
                            const v = e.target.value.trim();
                            if (v) { commit([...items, v]); e.target.value = ''; }
                        }}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault();
                                e.stopPropagation();
                                const el = e.currentTarget;
                                const v = el.value.trim();
                                if (v) { commit([...items, v]); el.value = ''; }
                                el.focus();
                                return;
                            }
                            keyDown(e, false);
                        }}
                    />
                </span>
            );
        }

        case 'image-upload': {
            const previewUrl = str
                ? str.split('/').map(encodeURIComponent).join('/')
                : '';
            return (
                <span className={styles.wyImgWrap} title={field.label}>
                    {previewUrl ? (
                        <img src={withBase(`/api/article_editor/images/${previewUrl}`)} alt={field.label} className={styles.wyImgThumb} />
                    ) : null}
                    <label className={styles.wyImgBtn}>
                        {str ? 'Заменить' : '+ изображение'}
                        <input
                            type="file"
                            accept="image/*"
                            style={{ display: 'none' }}
                            onChange={async (e) => {
                                const f = e.target.files?.[0];
                                e.target.value = '';
                                if (f && api.onUploadImage) {
                                    try {
                                        const key = await api.onUploadImage(field.key, f);
                                        onChange(key);
                                    } catch { /* upload failed silently */ }
                                }
                            }}
                        />
                    </label>
                    {str && (
                        <button type="button" className={styles.wyListItemX} title="Убрать" onClick={() => onChange('')}>×</button>
                    )}
                </span>
            );
        }

        default:
            return null;
    }
};

export default React.memo(InlineField);
