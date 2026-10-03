import styles from '../Article_editor.module.css';
import { getBlockTypeDef } from './blockTypes';
import { useTranslation } from 'react-i18next';

export type StructuralTerm = { kind?: string; id?: string; value?: string; unit?: string };

export type StructuralRow = {
    instanceId: string;
    blockType: 'entity' | 'statement' | string;
    order: number;
    data: Record<string, unknown>;
    display_text?: string;
    localized_type_name?: string;
};

type StructuralNode = { id: string; display_text: string };

type PipelineStructuralRowsProps = {
    rows: StructuralRow[];
    nodes: StructuralNode[];
    nodeIds?: ReadonlySet<string>;
    busy: boolean;
    onInspect?: (instanceId: string) => void;
    appearance?: 'pipeline' | 'document';
};

function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asText(value: unknown): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    return '';
}

function termText(value: unknown, nodeLabels: Map<string, string>): string {
    if (!isRecord(value)) return asText(value);
    const term = value as StructuralTerm;
    if (term.kind === 'literal') return `${term.value ?? ''}${term.unit ? ` ${term.unit}` : ''}`.trim();
    if (term.id) return nodeLabels.get(term.id) || term.id;
    return term.value ?? '';
}

function predicateText(value: unknown): string {
    if (!isRecord(value)) return asText(value);
    return asText(value.label) || asText(value.id);
}

function sourceSpanText(row: StructuralRow): string {
    const provenance = row.data.provenance;
    if (!isRecord(provenance) || !Array.isArray(provenance.source_spans)) return '';
    return provenance.source_spans
        .filter(isRecord)
        .map(span => `[${asText(span.start) || '?'}:${asText(span.end) || '?'}]`)
        .join(', ');
}

function typeName(blockType: string): string {
    const def = getBlockTypeDef(blockType);
    return def?.name ?? blockType;
}

function typeColor(blockType: string): string {
    return getBlockTypeDef(blockType)?.color ?? '#94a3b8';
}

function Word({ strong = false, children }: { strong?: boolean; children: React.ReactNode }) {
    return (
        <span className={styles.pipelineWord}>
            <span className={strong ? styles.pipelineWordStrong : styles.pipelineWordValue}>{children}</span>
        </span>
    );
}

function WordMuted({ children }: { children: React.ReactNode }) {
    return (
        <span className={styles.pipelineWord}>
            <span className={styles.pipelineWordMuted}>{children}</span>
        </span>
    );
}

function Arrow() {
    return <span className={styles.pipelineArrow} aria-hidden="true">→</span>;
}

function EntityProse({ row }: { row: StructuralRow }) {
    const label = asText(row.data.label) || asText(row.data.text) || '—';
    const kind = asText(row.data.semantic_kind);
    const context = asText(row.data.identity_context);
    return (
        <>
            <Word strong>{label}</Word>
            {kind && <WordMuted>· {kind}</WordMuted>}
            {context && <WordMuted>· «{context}»</WordMuted>}
        </>
    );
}

function StatementProse({ row, nodeLabels }: { row: StructuralRow; nodeLabels: Map<string, string> }) {
    const predicate = predicateText(row.data.predicate);
    const modality = asText(row.data.modality);
    const status = asText(row.data.status);
    const context = asText(row.data.context);
    return (
        <>
            <Word strong>{termText(row.data.subject, nodeLabels) || '—'}</Word>
            <Arrow />
            <Word strong>{predicate || '—'}</Word>
            <Arrow />
            <Word strong>{termText(row.data.object, nodeLabels) || '—'}</Word>
            {row.data.negated === true && <WordMuted>· отрицание</WordMuted>}
            {modality && <WordMuted>· {modality}</WordMuted>}
            {status && <WordMuted>· {status}</WordMuted>}
            {context && <WordMuted>· «{context}»</WordMuted>}
        </>
    );
}

function TypedProse({ row }: { row: StructuralRow }) {
    const entries = Object.entries(row.data).filter(([key, value]) => (
        key !== 'provenance' && key !== 'sourceSpan' && key !== 'source' && value !== '' && value !== null
        && (!Array.isArray(value) || value.length > 0)
    ));
    return (
        <>
            {entries.map(([key, value]) => {
                const text = typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
                    ? String(value)
                    : JSON.stringify(value);
                return (
                    <span key={key} className={styles.pipelineWord}>
                        <span className={styles.pipelineWordKey}>{key}:</span>
                        <span className={styles.pipelineWordValue}>{text}</span>
                    </span>
                );
            })}
            {asText(row.data.source) && <WordMuted>· {asText(row.data.source)}</WordMuted>}
        </>
    );
}

export default function PipelineStructuralRows({
    rows,
    nodes,
    nodeIds,
    busy,
    onInspect,
    appearance = 'pipeline',
}: PipelineStructuralRowsProps) {
    const { t } = useTranslation();
    const nodeLabels = new Map(nodes.map(node => [node.id, node.display_text]));
    rows.forEach(row => {
        if (row.blockType === 'entity') {
            const id = asText(row.data.id);
            if (id) nodeLabels.set(id, asText(row.data.label) || asText(row.data.text) || id);
        }
    });
    const rowsContent = rows.map(row => {
        const source = sourceSpanText(row);
        return (
            <article
                key={row.instanceId}
                className={styles.pipelineRow}
                data-pipeline-structural-row={row.instanceId}
                style={{ ['--pad' as string]: '52px', ['--wy-chip-color' as string]: typeColor(row.blockType) }}
            >
                <div className={styles.pipelineGutter} aria-hidden="true">
                    <span className={styles.pipelineTypeName} title={row.blockType}>{row.localized_type_name || t(`articleEditor.blockTypes.${row.blockType}`, { defaultValue: typeName(row.blockType) })}</span>
                </div>
                <span className={styles.pipelineBar} aria-hidden="true" />
                <div className={styles.pipelineContent}>
                    {row.display_text
                        ? <Word strong>{row.display_text}</Word>
                        : row.blockType === 'entity'
                        ? <EntityProse row={row} />
                        : row.blockType === 'statement'
                            ? <StatementProse row={row} nodeLabels={nodeLabels} />
                            : <TypedProse row={row} />}
                    <span className={styles.pipelineFoot}>
                        <span title={row.instanceId}>#{row.order + 1} · {row.instanceId.slice(0, 8)}</span>
                        {nodeIds && <span>{t(nodeIds.has(row.instanceId) ? 'articleEditor.rows.mapNode' : 'articleEditor.rows.evidence')}</span>}
                        {source && <span>{t('articleEditor.rows.sourceRange', { source })}</span>}
                        {onInspect && <button
                            type="button"
                            disabled={busy}
                            onClick={() => onInspect(row.instanceId)}
                            title={t('articleEditor.rows.inspectSource')}
                        >
                            {t('articleEditor.rows.source')}
                        </button>}
                    </span>
                </div>
            </article>
        );
    });

    if (appearance === 'document') {
        return (
            <div className={`${styles.wyScroller} ${styles.pipelineDocumentScroller}`} aria-label={t('articleEditor.rows.ariaLabel')}>
                <div className={styles.wyDoc}>{rowsContent}</div>
            </div>
        );
    }

    return <div className={styles.pipelineRows} aria-label={t('articleEditor.rows.ariaLabel')}>{rowsContent}</div>;
}
