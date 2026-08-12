import React, { useCallback, useMemo, useState } from 'react';
import type { ArticleBlockData, BlockDataValue } from '../model';
import { getBlockTypeDef } from './blockTypes';
import FieldInput, { type UuidRef } from './FieldInput';
import AuthorBadge from './AuthorBadge';
import styles from '../Article_editor.module.css';

interface StructuredBlockItemProps {
    block: ArticleBlockData;
    totalBlocks: number;
    sameTypeCount: number;
    sameTypeIndex: number;
    isHighlighted: boolean;
    onChange: (instanceId: string, fieldKey: string, value: BlockDataValue) => void;
    onDragStart: (index: number) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDrop: (index: number) => void;
    onDelete: (instanceId: string) => void;
    index: number;
    availableUuids?: UuidRef[];
    onBlurSave?: () => void;
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

const StructuredBlockItem: React.FC<StructuredBlockItemProps> = ({
    block, index, sameTypeCount, sameTypeIndex, isHighlighted,
    onChange, onDragStart, onDragOver, onDrop, onDelete, availableUuids = [], onBlurSave, onUploadImage,
}) => {
    const typeDef = useMemo(() => getBlockTypeDef(block.blockType), [block.blockType]);
    const [copied, setCopied] = useState(false);

    const handleCopyId = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(block.instanceId);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch { /* ignore */ }
    }, [block.instanceId]);

    const handleDragStart = useCallback(
        (e: React.DragEvent) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', String(index));
            onDragStart(index);
        },
        [index, onDragStart],
    );

    const handleDrop = useCallback(() => {
        onDrop(index);
    }, [index, onDrop]);

    const handleFieldChange = useCallback(
        (fieldKey: string, value: BlockDataValue) => {
            onChange(block.instanceId, fieldKey, value);
        },
        [block.instanceId, onChange],
    );

    const handleDelete = useCallback(() => {
        onDelete(block.instanceId);
    }, [block.instanceId, onDelete]);

    if (!typeDef) return null;

    const colorStyle = { borderLeftColor: typeDef.color } as React.CSSProperties;
    const noClear = block.blockType === 2 || block.blockType === 22 || block.blockType === 54;

    return (
        <div
            className={`${styles.sbItem} ${isHighlighted ? styles.sbHighlighted : ''}`}
            style={colorStyle}
            data-block-index={index}
        >
            <div
                className={styles.sbDragHandle}
                draggable
                onDragStart={handleDragStart}
                onDragOver={onDragOver}
                onDrop={handleDrop}
                title="Перетащить"
            >
                &#x2261;
            </div>

            <div className={styles.sbContent}>
                <div className={styles.sbHeader}>
                    <span className={styles.sbTypeBadge} style={{ background: typeDef.color + '20', color: typeDef.color }}>
                        {typeDef.icon} T{typeDef.typeNumber}
                    </span>
                    <button
                        className={styles.sbCopyIdBtn}
                        onClick={handleCopyId}
                        title={copied ? 'Скопировано' : 'Копировать UUID блока'}
                    >
                        {copied ? '\u2713' : '\u2398'}
                    </button>
                    <span className={styles.sbTypeName}>{typeDef.name}</span>
                    <span className={styles.sbInstanceNum}>
                        {block.instanceId}
                    </span>
                    <div style={{ flex: 1 }} />
                    <AuthorBadge author={block.author} label="Автор блока" />
                    {typeDef.description && (
                        <span className={styles.sbHelpIcon} title={typeDef.description}>?</span>
                    )}
                    <button
                        className={styles.sbDeleteBtn}
                        onClick={handleDelete}
                        title="Удалить блок"
                    >
                        &times;
                    </button>
                </div>

                <div className={`${styles.sbFields} ${typeDef.layout === 'row' ? styles.sbFieldsRow : ''}`}>
                    {typeDef.fields.map((field) => (
                        <FieldInput
                            key={field.key}
                            field={field}
                            value={block.data[field.key] ?? ''}
                            onChange={handleFieldChange}
                            availableUuids={field.inputType === 'uuid-ref' || field.inputType === 'pair-list' || field.inputType === 'uuid-list' ? availableUuids : undefined}
                            compact={typeDef.layout === 'row'}
                            onBlurSave={onBlurSave}
                            noClear={noClear}
                            onUploadImage={onUploadImage}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};

export default React.memo(StructuredBlockItem);
