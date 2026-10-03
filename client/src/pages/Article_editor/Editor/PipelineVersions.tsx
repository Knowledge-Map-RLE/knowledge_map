import { useCallback, useEffect, useState } from 'react';
import { fetchJson } from '../../../services/api/http';
import PipelineStructuralRows, {
    type StructuralRow,
} from './PipelineStructuralRows';

type Version = {
    version_id: string; status: string; stage: string; active?: boolean; created_at: string;
    timing?: { total_seconds?: number };
    map_rebuild?: { source_version_id: string; strategy: string; schema_version: number } | null;
};
type MapNode = { id: string; block_type: string; display_text: string };
type MapEdge = { source: string; target: string; evidence?: { structural_id: string; field: string }[] };
type MapEvidence = { id: string; owner_id?: string | null; block_type: string; display_text: string };
type Detail = {
    status: string; stage: string; error?: string;
    map_rebuild?: { source_version_id: string; strategy: string; schema_version: number; elapsed_seconds?: number } | null;
    graph?: {
        schema_version?: number;
        nodes: MapNode[];
        edges?: MapEdge[];
        evidence?: MapEvidence[];
        requirement_groups?: { id: string; target: string; mode: 'all' | 'any' }[];
        reading_order?: string[];
        goal_ids?: string[];
        semantic_edges?: MapEdge[];
        dependency_edges?: MapEdge[];
    };
    coverage?: { semantic_token_fraction: number; token_preservation: number };
    timing?: { total_seconds?: number; nlp_seconds?: number; llm_seconds?: number; map_and_metrics_seconds?: number };
    model_steps?: Array<{
        prompt_id?: string; prompt_version?: string; dsl?: string;
        model_call?: { provider?: string; model?: string; elapsed_seconds?: number; usage?: Record<string, unknown> };
    }>;
    quality_metrics?: {
        gates?: { passed?: boolean; checks?: Record<string, boolean> };
        structural_rows?: { row_count?: number; caption_image_row_count?: number; duplicate_fingerprint_candidates?: number };
        knowledge_map?: { node_count?: number; edge_count?: number; orphan_node_count?: number };
        source_accounting?: {
            assertional_unit_count: number;
            annotated_unit_count: number;
            annotated_unit_coverage: number;
            references_excluded?: boolean;
        };
    };
    validation?: Record<string, string>;
};
type CurrentMap = {
    graph: Detail['graph'] | null;
    blocks: StructuralRow[];
    rebuilt_at?: string | null;
    stale?: boolean;
};
type Provenance = {
    source: { text: string; article_id: string };
    structural: { data: { provenance: { source_spans: { start: number; end: number }[] } } };
    fragment: string;
    tokens: unknown[];
};

export default function PipelineVersions({ docId, refresh = 0, enabled = true }: { docId: string; refresh?: number; enabled?: boolean }) {
    const [versions, setVersions] = useState<Version[]>([]);
    const [selected, setSelected] = useState('');
    const [detail, setDetail] = useState<Detail | null>(null);
    const [currentMap, setCurrentMap] = useState<CurrentMap | null>(null);
    const [rows, setRows] = useState<StructuralRow[]>([]);
    const [provenance, setProvenance] = useState<Provenance | null>(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState(false);
    const base = '/api/article_editor/articles/' + encodeURIComponent(docId) + '/pipeline/versions';
    const loadVersions = useCallback(async () => {
        if (!enabled) return;
        setError('');
        const result = await fetchJson<{ versions: Version[] }>(base);
        setVersions(result.versions);
    }, [base, enabled]);
    useEffect(() => {
        let active = true;
        setSelected(''); setDetail(null); setRows([]); setProvenance(null);
        setCurrentMap(null);
        if (!enabled) {
            setVersions([]);
            setError('');
            return () => { active = false; };
        }
        loadVersions().catch(e => { if (active) setError(String(e)); });
        fetchJson<CurrentMap>(base.replace('/pipeline/versions', '/pipeline/current-map'))
            .then(result => { if (active) setCurrentMap(result); })
            .catch(e => { if (active) setError(String(e)); });
        return () => { active = false; };
    }, [enabled, loadVersions, refresh]);
    useEffect(() => {
        if (!selected) return;
        let active = true;
        setProvenance(null); setDetail(null); setError('');
        Promise.all([
            fetchJson<Detail>(base + '/' + selected),
            fetchJson<{ result: StructuralRow[] }>(base + '/' + selected + '/stages/structural'),
        ]).then(([result, structural]) => {
            if (!active) return;
            setDetail(result);
            setRows(Array.isArray(structural.result) ? structural.result : []);
        }).catch(e => { if (active) setError(String(e)); });
        return () => { active = false; };
    }, [base, selected]);
    async function inspect(id: string) {
        setBusy(true); setError('');
        try { setProvenance(await fetchJson<Provenance>(base + '/' + selected + '/provenance/' + id)); }
        catch (e) { setError(String(e)); }
        finally { setBusy(false); }
    }
    async function apply() {
        setBusy(true); setError('');
        try {
            await fetchJson(base + '/' + selected + '/apply', { method: 'POST' });
            setVersions(await fetchJson<{ versions: Version[] }>(base).then(r => r.versions));
        } catch (e) { setError(String(e)); }
        finally { setBusy(false); }
    }
    async function rebuildMap() {
        if (!selected) return;
        setBusy(true); setError(''); setNotice('');
        try {
            const result = await fetchJson<{ version_id: string; created: boolean }>(
                base + '/' + selected + '/rebuild-map', { method: 'POST' },
            );
            const updated = await fetchJson<{ versions: Version[] }>(base);
            setVersions(updated.versions);
            setSelected(result.version_id);
            setNotice(result.created
                ? 'Новая карта построена без LLM. Примените эту версию, чтобы она стала активной.'
                : 'Карта уже соответствует текущему детерминированному построителю.');
        } catch (e) { setError(String(e)); }
        finally { setBusy(false); }
    }
    async function rebuildCurrentMap() {
        setBusy(true); setError(''); setNotice('');
        try {
            const result = await fetchJson<CurrentMap & { created: boolean }>(
                base.replace('/pipeline/versions', '/pipeline/current-map/rebuild'),
                { method: 'POST' },
            );
            setCurrentMap(result);
            setNotice(result.created
                ? 'Карта построена из сохранённых структурных строк без LLM.'
                : 'Сохранённая карта уже соответствует текущим структурным строкам.');
        } catch (e) { setError(String(e)); }
        finally { setBusy(false); }
    }
    const relationCount = rows.filter(row => row.blockType === 'relation' || row.blockType === 'temporal_relation').length;
    const nodeIds = new Set(detail?.graph?.nodes.map(node => node.id) ?? []);
    const edgeCount = detail?.graph
        ? detail.graph.schema_version === 2 || detail.graph.schema_version === 3
            ? detail.graph.edges?.length ?? 0
            : (detail.graph.semantic_edges?.length ?? 0) + (detail.graph.dependency_edges?.length ?? 0)
        : 0;
    const formatTimestamp = (value: string) => new Date(value).toLocaleString('ru-RU');
    return <section aria-label="Версии извлечения" style={{ padding: 12, maxHeight: '100%', overflow: 'auto' }}>
        <h3>Версии извлечения и источники <button type="button" onClick={() => void loadVersions()} disabled={!enabled}>Обновить</button></h3>
        <p style={{ margin: '4px 0 8px', color: '#6b7280', fontSize: 12 }}>
            Документ: {docId} · версий: {versions.length}
        </p>
        <div aria-label="Список версий извлечения" role="listbox" style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
            {versions.length === 0 && !error && <>
                <p>Сохранённых версий пайплайна для этого документа нет.</p>
                <p>Можно перестроить карту по текущим сохранённым структурным строкам. LLM не вызывается.</p>
                {currentMap && currentMap.blocks.length === 0 && <p>В статье пока нет сохранённых структурных строк.</p>}
                <button type="button" disabled={busy || !currentMap?.blocks.length}
                    onClick={() => void rebuildCurrentMap()}>
                    Перестроить карту из структурных строк без LLM
                </button>
                {currentMap?.stale && <p>Структурные строки изменились после предыдущей пересборки карты.</p>}
                {currentMap?.graph && <>
                    <p role="status">
                        Сохранённая карта v{currentMap.graph.schema_version}: {currentMap.graph.nodes.length} узлов,
                        {' '}{currentMap.graph.evidence?.length ?? 0} свидетельств,
                        {' '}{currentMap.graph.edges?.length ?? 0} рёбер.
                    </p>
                    <PipelineStructuralRows
                        rows={currentMap.blocks}
                        nodes={currentMap.graph.nodes}
                        nodeIds={new Set(currentMap.graph.nodes.map(node => node.id))}
                        busy={busy}
                    />
                </>}
            </>}
            {versions.map(v => {
                const isSelected = selected === v.version_id;
                return <button
                    key={v.version_id}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => setSelected(v.version_id)}
                    style={{
                        display: 'block', textAlign: 'left', padding: '7px 9px', cursor: 'pointer',
                        border: `1px solid ${isSelected ? '#2563eb' : '#d1d5db'}`,
                        borderRadius: 4, background: isSelected ? '#eff6ff' : '#fff',
                    }}
                >
                    <strong>{formatTimestamp(v.created_at)}</strong>
                    {' — '}{v.status} / {v.stage}
                    {v.timing?.total_seconds != null ? ` — ${v.timing.total_seconds.toFixed(2)} с` : ''}
                    {v.map_rebuild ? ' — карта пересобрана без LLM' : ''}
                    {v.active ? ' — активная' : ''}
                    <small style={{ display: 'block', color: '#6b7280', marginTop: 2 }}>{v.version_id}</small>
                </button>;
            })}
        </div>
        {error && <p role="alert">{error}</p>}
        {detail && <>
            <p>{detail.status} · {detail.stage}</p>
            {detail.error && <p role="alert">{detail.error}</p>}
            {detail.coverage && <p>
                Сохранено токенов: {(detail.coverage.token_preservation * 100).toFixed(0)}%.
                Покрыто семантическими диапазонами: {(detail.coverage.semantic_token_fraction * 100).toFixed(1)}%.
                Это покрытие источника, а не оценка научной точности.
            </p>}
            {detail.map_rebuild && <p>
                Детерминированная пересборка карты: {detail.map_rebuild.elapsed_seconds?.toFixed(3) ?? '—'} с; LLM не вызывалась.
            </p>}
            {!detail.map_rebuild && detail.timing && <p>
                Время: всего {detail.timing.total_seconds?.toFixed(2) ?? '—'} с;
                {' '}NLP {detail.timing.nlp_seconds?.toFixed(2) ?? '—'} с;
                {' '}LLM {detail.timing.llm_seconds?.toFixed(2) ?? '—'} с;
                {' '}карта и метрики {detail.timing.map_and_metrics_seconds?.toFixed(2) ?? '—'} с.
            </p>}
            {!detail.map_rebuild && detail.model_steps?.[0]?.model_call && <p>
                Провайдер: {detail.model_steps[0].model_call.provider ?? '—'};
                {' '}модель: {detail.model_steps[0].model_call.model ?? '—'};
                {' '}ответ LLM: {detail.model_steps[0].model_call.elapsed_seconds?.toFixed(2) ?? '—'} с.
            </p>}
            {detail.quality_metrics?.source_accounting && <p>
                Сопоставлено утверждательных source units: {detail.quality_metrics.source_accounting.annotated_unit_count}/
                {detail.quality_metrics.source_accounting.assertional_unit_count}
                {' '}({(detail.quality_metrics.source_accounting.annotated_unit_coverage * 100).toFixed(1)}%).
                {detail.quality_metrics.source_accounting.references_excluded ? ' References исключены.' : ''}
            </p>}
            {detail.quality_metrics && <p>
                Gates: {detail.quality_metrics.gates?.passed ? 'пройдены' : 'не пройдены'};
                {' '}строк: {detail.quality_metrics.structural_rows?.row_count ?? rows.length};
                {' '}image-подписей: {detail.quality_metrics.structural_rows?.caption_image_row_count ?? 0};
                {' '}дубликатов-кандидатов: {detail.quality_metrics.structural_rows?.duplicate_fingerprint_candidates ?? 0};
                {' '}orphan nodes: {detail.quality_metrics.knowledge_map?.orphan_node_count ?? 0}.
            </p>}
            {detail.graph && <>
                <button disabled={busy || detail.status !== 'completed' && detail.status !== 'completed_with_warnings'}
                    onClick={() => void rebuildMap()}>Перестроить карту из структурных строк без LLM</button>
                <button disabled={busy} onClick={() => void apply()}>Применить эту версию</button>
                {notice && <p role="status">{notice}</p>}
                {detail.map_rebuild && <p>
                    Карта пересобрана без LLM из структурных строк версии {detail.map_rebuild.source_version_id}.
                    {' '}Нажмите «Применить эту версию», чтобы сделать её активной.
                </p>}
                <p>
                    Структурные строки: {rows.length} (связей-свидетельств {relationCount});
                    {' '}узлов карты: {detail.graph.nodes.length}; свидетельств: {detail.graph.evidence?.length ?? 0};
                    {' '}рёбер карты: {edgeCount}.
                </p>
                <PipelineStructuralRows
                    rows={rows}
                    nodes={detail.graph.nodes}
                    nodeIds={nodeIds}
                    busy={busy}
                    onInspect={(id) => void inspect(id)}
                />
            </>}
            {detail.validation && <details><summary>Валидация</summary>
                <ul>{Object.entries(detail.validation).map(([key, value]) =>
                    <li key={key}>{key}: {value}</li>)}
                </ul>
            </details>}
            {detail.model_steps?.[0]?.dsl && <details>
                <summary>{detail.map_rebuild ? 'Исходный DSL структурных строк' : 'DSL модели'} · {detail.model_steps[0].prompt_id ?? 'KM.ARTICLE_ROWS'} v{detail.model_steps[0].prompt_version ?? '—'}</summary>
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto' }}>{detail.model_steps[0].dsl}</pre>
            </details>}
            {detail.graph && <details>
                <summary>Узлы карты ({detail.graph.nodes.length})</summary>
                <ul>{detail.graph.nodes.slice(0, 300).map(node => <li key={node.id}>
                    <button disabled={busy} onClick={() => void inspect(node.id)} style={{ textAlign: 'left' }}>
                        {node.block_type}: {node.display_text}
                    </button>
                </li>)}</ul>
                {detail.graph.nodes.length > 300 && <p>Показаны первые 300 узлов; provenance доступен для каждой структурной строки выше.</p>}
            </details>}
        </>}
        {provenance && <aside aria-label="Происхождение знания">
            <h4>Исходный текст</h4>
            {provenance.structural.data.provenance.source_spans.map((span, index) => {
                const chars = Array.from(provenance.source.text);
                return <pre key={index} style={{ whiteSpace: 'pre-wrap' }}>
                    {chars.slice(Math.max(0, span.start - 100), span.start).join('')}
                    <mark>{chars.slice(span.start, span.end).join('')}</mark>
                    {chars.slice(span.end, span.end + 100).join('')}
                </pre>;
            })}
            <details><summary>Структурная строка</summary><pre style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(provenance.structural, null, 2)}
            </pre></details>
            {provenance.fragment && <details open><summary>Фрагмент источника</summary><pre style={{ whiteSpace: 'pre-wrap' }}>
                {provenance.fragment}
            </pre></details>}
            <details><summary>Токены диапазона</summary><pre style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify({ tokens: provenance.tokens }, null, 2)}
            </pre></details>
        </aside>}
    </section>;
}
