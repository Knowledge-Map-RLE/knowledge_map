import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getMapProvenance, getTransitionProvenance, type MapProvenance, type SavedArticleMap } from '../../../services/api/article_maps';
import styles from './ArticleMap.module.css';

export type MapSelection = { nodeId: string } | { transitionIds: string[] };

/** Происхождение всегда загружается для выбранного неизменяемого запуска. */
export default function ArticleMapDetails({ result, selection, onClose }: {
    result: SavedArticleMap; selection: MapSelection; onClose: () => void;
}) {
    const { t } = useTranslation();
    const [records, setRecords] = useState<MapProvenance[]>([]);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const selectionKey = 'nodeId' in selection ? selection.nodeId : selection.transitionIds.join(':');
    useEffect(() => {
        const controller = new AbortController();
        setRecords([]); setError(''); setLoading(true);
        const request = 'nodeId' in selection
            ? getMapProvenance(result.article_id, result.pipeline_id, selection.nodeId, result.run_id, controller.signal).then(value => [value])
            : Promise.all(selection.transitionIds.map(id => getTransitionProvenance(
                result.article_id, result.pipeline_id, id, result.run_id, controller.signal)));
        void request.then(values => { if (!controller.signal.aborted) setRecords(values); })
            .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause)); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [result.article_id, result.pipeline_id, result.run_id, selectionKey]);
    const selectedNode = 'nodeId' in selection ? result.graph.nodes.find(node => node.id === selection.nodeId) : undefined;
    return <aside className={styles.detailsPanel} aria-label={t('articleEditor.map.details.title')}>
        <div className={styles.detailsHeading}>
            <strong>{t('articleEditor.map.details.title')}</strong>
            <button type="button" onClick={onClose} aria-label={t('articleEditor.map.details.close')}>×</button>
        </div>
        {selectedNode && <p>{selectedNode.display_text}</p>}
        {loading && <p role="status">{t('articleEditor.map.loading')}</p>}
        {error && <p role="alert">{t('articleEditor.map.loadError', { error })}</p>}
        {records.map((record, index) => <section key={record.transition?.id ?? index}>
            {record.transition && <>
                <strong>{record.transition.sources.join(' + ')} → {record.transition.target}</strong>
                <p>{record.transition.reason}</p>
                <p>{t('articleEditor.map.details.premises', { count: record.transition.sources.length })}</p>
                {record.transition.conditions.length > 0 && <p>{record.transition.conditions.join('; ')}</p>}
            </>}
            {record.knowledge && <>
                <p>{record.knowledge.knowledge_id} · {record.knowledge.knowledge_kind}
                    {record.knowledge.action_status && ` · ${record.knowledge.action_status}`}</p>
                <details><summary>{t('articleEditor.map.details.semantics')}</summary>
                    <pre>{JSON.stringify(record.knowledge.semantic_frame, null, 2)}</pre>
                </details>
            </>}
            <strong>{t('articleEditor.map.details.source')}</strong>
            {record.fragments.map((fragment, i) => <blockquote key={`${fragment.start}:${i}`}>
                <small>{fragment.section_id} · {fragment.start}–{fragment.end}</small>
                <p>{fragment.text}</p>
            </blockquote>)}
            {record.source_attachments?.map(attachment => <details key={attachment.unit_id}>
                <summary>{attachment.unit_id} · {attachment.author} · {attachment.xml_asset}</summary>
                <pre style={{ whiteSpace: 'pre-wrap' }}>{attachment.text}</pre>
            </details>)}
            <small>{t('articleEditor.map.details.unreviewed')}</small>
        </section>)}
    </aside>;
}
