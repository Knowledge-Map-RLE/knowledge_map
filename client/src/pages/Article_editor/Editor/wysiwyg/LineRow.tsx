import React, { useCallback, useRef, useState } from 'react';
import type { ArticleBlockData, BlockTypeDef } from '../../model';
import { getBlockTypeDef } from '../blockTypes';
import { useWysiwygApi } from './WysiwygContext';
import InlineField from './InlineField';
import YamlHeading from './YamlHeading';
import { queryLineFieldEls } from './focusNav';
import styles from '../../Article_editor.module.css';

interface LineRowProps {
    block: ArticleBlockData;
    depth: number;
    chainText?: string;
    showUids: boolean;
    dragging: boolean;
    dropSide: 'before' | 'after' | null;
    highlight: boolean;
    focused: boolean;
    onDragStartLine: (instanceId: string) => void;
    onDragEndLine: () => void;
    onDragOverLine: (e: React.DragEvent, instanceId: string) => void;
    onDropLine: (e: React.DragEvent, instanceId: string) => void;
}

const PAD_BASE = 52;
const PAD_STEP = 24;

/** Кнопка копирования UUID строки: видна при наведении на строку. */
const UuidCopyButton: React.FC<{ instanceId: string; chainText?: string }> = ({ instanceId, chainText }) => {
    const [copied, setCopied] = useState(false);
    const timerRef = useRef<number | null>(null);

    const handleCopy = useCallback(() => {
        navigator.clipboard?.writeText(instanceId).then(() => {
            setCopied(true);
            if (timerRef.current !== null) window.clearTimeout(timerRef.current);
            timerRef.current = window.setTimeout(() => setCopied(false), 1200);
        }).catch(() => { /* буфер недоступен */ });
    }, [instanceId]);

    return (
        <button
            type="button"
            className={`${styles.wyUuidCopy} ${copied ? styles.wyUuidCopyDone : ''}`}
            title={copied ? 'UUID скопирован' : `Скопировать UUID: ${instanceId}${chainText ? `\n${chainText}` : ''}`}
            onClick={handleCopy}
        >
            {copied ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                </svg>
            ) : (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="9" y="9" width="13" height="13" rx="2" />
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
            )}
        </button>
    );
};

/** Кнопка удаления строки: видна при наведении на строку, слева от копирования UUID. */
const DeleteLineButton: React.FC<{ instanceId: string }> = ({ instanceId }) => {
    const api = useWysiwygApi();
    return (
        <button
            type="button"
            className={styles.wyDeleteLine}
            title={`Удалить строку\nUUID: ${instanceId}`}
            aria-label="Удалить строку"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => api.removeLine(instanceId)}
        >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
        </button>
    );
};

const LineRowInner: React.FC<LineRowProps> = ({
    block,
    depth,
    chainText,
    showUids,
    dragging,
    dropSide,
    highlight,
    focused,
    onDragStartLine,
    onDragEndLine,
    onDragOverLine,
    onDropLine,
}) => {
    const api = useWysiwygApi();
    const def: BlockTypeDef | undefined = getBlockTypeDef(block.blockType);

    const handleTypeBarClick = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        api.openSlashMenu({ lineId: block.instanceId, fieldKey: '__type__', rect });
    }, [api, block.instanceId]);

    const handleRowClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        if (e.target !== e.currentTarget) return;
        const fields = queryLineFieldEls(e.currentTarget, block.instanceId)
            .filter((el): el is HTMLInputElement | HTMLTextAreaElement =>
                el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement);
        const empty = fields.find((f) => !f.value.trim());
        (empty ?? fields[0])?.focus();
    }, [block.instanceId]);

    const rowClass = [
        styles.wyLine,
        showUids ? styles.wyUidsOn : '',
        dragging ? styles.wyLineDragging : '',
        dropSide === 'before' ? styles.wyLineDropBefore : '',
        dropSide === 'after' ? styles.wyLineDropAfter : '',
        highlight ? styles.wyLineHighlight : '',
        focused ? styles.wyLineFocused : '',
    ].filter(Boolean).join(' ');

    if (!def) {
        return (
            <div
                className={rowClass}
                data-wy-line-row={block.instanceId}
                style={{ ['--pad' as string]: `${PAD_BASE + depth * PAD_STEP}px` }}
            >
                <span className={styles.wyTypeName}>{`T${block.blockType}`}</span>
            </div>
        );
    }

    const typeTitle = `T${def.typeNumber} · ${def.name}${def.description ? ` — ${def.description}` : ''}\nUUID: ${block.instanceId}\nКлик — сменить тип (/)`;

    return (
        <div
            className={rowClass}
            data-wy-line-row={block.instanceId}
            style={{ ['--pad' as string]: `${PAD_BASE + depth * PAD_STEP}px`, ['--wy-chip-color' as string]: def.color }}
            onClick={handleRowClick}
            onDragOver={(e) => onDragOverLine(e, block.instanceId)}
            onDrop={(e) => onDropLine(e, block.instanceId)}
        >
            <div className={styles.wyGutter}>
                {/* Порядок важен: при переполнении gutter (overflow: hidden)
                    срезается левый край, поэтому имя типа — первым,
                    а handle и копирование UUID — у правого края. */}
                <span className={styles.wyTypeName} title={def.name}>
                    {def.name}
                </span>
                <button
                    type="button"
                    className={styles.wyDragHandle}
                    draggable
                    onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = 'move';
                        e.dataTransfer.setData('text/plain', block.instanceId);
                        onDragStartLine(block.instanceId);
                    }}
                    onDragEnd={onDragEndLine}
                    title="Перетащите, чтобы переместить строку"
                >
                    ⠿
                </button>
                <DeleteLineButton instanceId={block.instanceId} />
                <UuidCopyButton instanceId={block.instanceId} chainText={chainText} />
            </div>
            {Array.from({ length: depth }).map((_, i) => (
                <span key={i} className={styles.wyGuide} style={{ left: PAD_BASE - 9 + i * PAD_STEP }} />
            ))}
            <button
                type="button"
                className={styles.wyTypeBarBtn}
                onClick={handleTypeBarClick}
                title={typeTitle}
                aria-label={`Тип T${def.typeNumber}: ${def.name}`}
            />
            {def.layout === 'yaml' ? (
                <div className={styles.wyYamlWrap}>
                    <pre className={styles.wyYaml} data-wy-line={block.instanceId}>
                        {def.fields.map((f) => (
                            <span key={f.key} className={styles.wyYamlLine}>
                                <span className={styles.wyYamlKey}>{`${f.key}:`}</span>
                                <span className={styles.wyYamlValue}>
                                    <InlineField lineId={block.instanceId} field={f} value={block.data[f.key] ?? ''} />
                                </span>
                            </span>
                        ))}
                    </pre>
                    <YamlHeading
                        value={typeof block.data.title === 'string' ? block.data.title : ''}
                        placeholder="Название статьи"
                        onChange={(v) => api.setField(block.instanceId, 'title', v)}
                    />
                </div>
            ) : (
                <div className={styles.wyFields}>
                    {def.fields.map((f) => (
                        <InlineField key={f.key} lineId={block.instanceId} field={f} value={block.data[f.key] ?? ''} />
                    ))}
                </div>
            )}
        </div>
    );
};

const LineRow = React.memo(LineRowInner);

export default LineRow;
