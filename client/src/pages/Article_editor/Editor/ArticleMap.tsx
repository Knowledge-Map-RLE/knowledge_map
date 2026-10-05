import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FiFileText, FiList } from 'react-icons/fi';
import ArticleMapCanvas from './ArticleMapCanvas';
import styles from './ArticleMap.module.css';
import {
    buildStructuralArticleMap, buildTextArticleMap, getArticleMap, listArticleMaps, translateArticleMap,
    type ArticleMapInventory, type MapPipelineId, type SavedArticleMap,
} from '../../../services/api/article_maps';

const selectionKey = (docId: string) => `article-map.selection.${docId}`;
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

/** Две независимые карты; новая карта по умолчанию отображается на английском. */
export default function ArticleMap({ docId, enabled }: { docId: string; enabled: boolean }) {
    const { t, i18n } = useTranslation();
    const [inventory, setInventory] = useState<ArticleMapInventory | null>(null);
    const [selected, setSelected] = useState<MapPipelineId | ''>('');
    const [detail, setDetail] = useState<SavedArticleMap | null>(null);
    const [locale, setLocale] = useState<'en' | 'ru'>('en');
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [stage, setStage] = useState('');
    const [error, setError] = useState('');
    const generation = useRef(0);
    const operation = useRef<AbortController | null>(null);
    const owner = useRef(docId);
    owner.current = docId;

    const refresh = useCallback(async (signal: AbortSignal) => {
        const result = await listArticleMaps(docId, signal);
        if (owner.current === docId && !signal.aborted) setInventory(result);
        return result;
    }, [docId]);

    useEffect(() => {
        const controller = new AbortController();
        generation.current++;
        operation.current?.abort();
        setInventory(null); setSelected(''); setDetail(null); setLocale('en');
        setBusy(false); setError(''); setLoading(enabled);
        if (enabled) {
            void refresh(controller.signal).then(result => {
                if (controller.signal.aborted) return;
                const saved = sessionStorage.getItem(selectionKey(docId));
                const choice = result.maps.find(map => map.pipeline_id === saved) ?? result.maps[0];
                setSelected(choice?.pipeline_id ?? '');
            }).catch(cause => {
                if (!controller.signal.aborted) setError(message(cause));
            }).finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });
        }
        return () => { controller.abort(); operation.current?.abort(); };
    }, [docId, enabled, refresh]);

    useEffect(() => {
        if (!enabled || !selected) return;
        const controller = new AbortController();
        const requestId = ++generation.current;
        setLoading(true); setDetail(null);
        sessionStorage.setItem(selectionKey(docId), selected);
        void getArticleMap(docId, selected, locale, controller.signal).then(result => {
            if (!controller.signal.aborted && requestId === generation.current) setDetail(result);
        }).catch(cause => {
            if (!controller.signal.aborted && requestId === generation.current) setError(message(cause));
        }).finally(() => {
            if (!controller.signal.aborted && requestId === generation.current) setLoading(false);
        });
        return () => controller.abort();
    }, [docId, enabled, selected, locale]);

    async function build(pipeline: MapPipelineId) {
        if (busy) return;
        const controller = new AbortController();
        operation.current = controller;
        setBusy(true); setError(''); setStage('model');
        try {
            const result = pipeline === 'text_reified'
                ? await buildTextArticleMap(docId, controller.signal, next => {
                    if (!controller.signal.aborted) setStage(next);
                }) : await buildStructuralArticleMap(docId, controller.signal);
            if (controller.signal.aborted || owner.current !== docId) return;
            setLocale('en'); setSelected(pipeline); setDetail(result);
            sessionStorage.setItem(selectionKey(docId), pipeline);
            setInventory(current => current && ({ ...current,
                maps: [...current.maps.filter(map => map.pipeline_id !== pipeline), result],
            }));
            await refresh(controller.signal);
        } catch (cause) {
            if (!controller.signal.aborted && owner.current === docId) setError(message(cause));
        } finally {
            if (!controller.signal.aborted && owner.current === docId) setBusy(false);
        }
    }

    async function showRussian() {
        if (!selected || busy) return;
        const controller = new AbortController();
        operation.current = controller;
        setBusy(true); setError(''); setStage('translation');
        try {
            await translateArticleMap(docId, selected, controller.signal);
            if (!controller.signal.aborted && owner.current === docId) setLocale('ru');
        } catch (cause) {
            if (!controller.signal.aborted && owner.current === docId) setError(message(cause));
        } finally {
            if (!controller.signal.aborted && owner.current === docId) setBusy(false);
        }
    }

    const canBuild = (pipeline: MapPipelineId) => enabled && !loading && !busy && inventory?.availability[pipeline] === true;
    const currentDetail = detail?.article_id === docId && detail.pipeline_id === selected ? detail : null;
    return <section style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div aria-label={t('articleEditor.map.controls')} className={styles.controls}>
            <div className={styles.actions}>
                <button type="button" className={`${styles.buildButton} ${styles.primaryButton}`}
                    onClick={() => void build('text_reified')} disabled={!canBuild('text_reified')}>
                    <FiFileText aria-hidden="true" focusable="false" />
                    {t('articleEditor.map.buildText')}
                </button>
                <button type="button" className={`${styles.buildButton} ${styles.secondaryButton}`}
                    onClick={() => void build('structural_rows')} disabled={!canBuild('structural_rows')}>
                    <FiList aria-hidden="true" focusable="false" />
                    {t('articleEditor.map.buildRows')}
                </button>
            </div>
            <label className={styles.field}>{t('articleEditor.map.version')}
                <select className={styles.select} value={selected} disabled={!enabled || busy || loading || !inventory?.maps.length}
                    onChange={event => { setError(''); setLocale('en'); setSelected(event.target.value as MapPipelineId); }}>
                    {!inventory?.maps.length && <option value="">{t('articleEditor.map.noVersions')}</option>}
                    {inventory?.maps.map(map => <option key={map.pipeline_id} value={map.pipeline_id}>
                        {t(`articleEditor.map.pipeline.${map.pipeline_id === 'text_reified' && map.graph_schema_version === 5 ? 'text_knowledge' : map.pipeline_id}`)} · {new Date(map.updated_at).toLocaleString(i18n.resolvedLanguage)}
                    </option>)}
                </select>
            </label>
            {selected && <label className={styles.field}>{t('articleEditor.map.language')}
                <select className={styles.select} value={locale} disabled={busy || loading} onChange={event => {
                    if (event.target.value === 'ru') void showRussian(); else setLocale('en');
                }}>
                    <option value="en">English</option><option value="ru">Русский</option>
                </select>
            </label>}
        </div>
        {enabled && inventory && !inventory.availability.text_reified && <p style={{ margin: '4px 10px' }}>{t('articleEditor.map.noFullText')}</p>}
        {enabled && inventory && !inventory.availability.structural_rows && <p style={{ margin: '4px 10px' }}>{t('articleEditor.map.noRows')}</p>}
        {error && <div role="alert" style={{ padding: 10, color: '#b91c1c' }}>{t('articleEditor.map.loadError', { error })}</div>}
        {busy && <div role="status" style={{ padding: 10 }}>{t(`articleEditor.map.stages.${stage}`)}</div>}
        <div style={{ flex: 1, minHeight: 0 }}>
            {!enabled ? <p>{t('articleEditor.map.loginRequired')}</p>
                : loading ? <p role="status">{t('articleEditor.map.loading')}</p>
                    : currentDetail ? <ArticleMapCanvas key={`${docId}:${selected}:${currentDetail.run_id}:${locale}`} result={currentDetail} />
                        : <p style={{ padding: 16 }}>{t('articleEditor.map.notBuilt')}</p>}
        </div>
    </section>;
}
