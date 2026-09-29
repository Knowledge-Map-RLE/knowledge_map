import { useCallback, useEffect, useState } from 'react';
import { fetchJson } from '../../../services/api/http';
import PipelineStructuralRows, {
    type StructuralRow,
} from './PipelineStructuralRows';

type Version = {
    version_id: string; status: string; stage: string; active?: boolean; created_at: string;
    timing?: { total_seconds?: number };
};
type MapNode = { id: string; block_type: string; display_text: string };
type Detail = {
    status: string; stage: string; error?: string;
    graph?: { nodes: MapNode[]; semantic_edges?: { source: string; target: string }[] };
    coverage?: { semantic_token_fraction: number; token_preservation: number };
    timing?: { total_seconds?: number; nlp_seconds?: number; llm_seconds?: number; map_and_metrics_seconds?: number };
    model_steps?: Array<{
        prompt_id?: string; prompt_version?: string; dsl?: string;
        model_call?: { provider?: string; model?: string; elapsed_seconds?: number; usage?: Record<string, unknown> };
    }>;
    quality_metrics?: {
        gates?: { passed?: boolean; checks?: Record<string, boolean> };
        structural_rows?: { row_count?: number; caption_image_row_count?: number; duplicate_fingerprint_candidates?: number };
        knowledge_map?: { node_count?: number; semantic_edge_count?: number; orphan_node_count?: number };
        source_accounting?: {
            assertional_unit_count: number;
            annotated_unit_count: number;
            annotated_unit_coverage: number;
            references_excluded?: boolean;
        };
    };
    validation?: Record<string, string>;
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
    const [rows, setRows] = useState<StructuralRow[]>([]);
    const [provenance, setProvenance] = useState<Provenance | null>(null);
    const [error, setError] = useState('');
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
        if (!enabled) {
            setVersions([]);
            setError('');
            return () => { active = false; };
        }
        loadVersions().catch(e => { if (active) setError(String(e)); });
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
    const relationCount = rows.filter(row => row.blockType === 'relation' || row.blockType === 'temporal_relation').length;
    const formatTimestamp = (value: string) => new Date(value).toLocaleString('ru-RU');
    return <section aria-label="Версии извлечения" style={{ padding: 12, maxHeight: '100%', overflow: 'auto' }}>
        <h3>Версии извлечения и источники <button type="button" onClick={() => void loadVersions()} disabled={!enabled}>Обновить</button></h3>
        <p style={{ margin: '4px 0 8px', color: '#6b7280', fontSize: 12 }}>
            Документ: {docId} · версий: {versions.length}
        </p>
        <div aria-label="Список версий извлечения" role="listbox" style={{ display: 'grid', gap: 6, marginBottom: 12 }}>
            {versions.length === 0 && !error && <p>Сохранённых версий для этого документа нет.</p>}
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
            {detail.timing && <p>
                Время: всего {detail.timing.total_seconds?.toFixed(2) ?? '—'} с;
                {' '}NLP {detail.timing.nlp_seconds?.toFixed(2) ?? '—'} с;
                {' '}LLM {detail.timing.llm_seconds?.toFixed(2) ?? '—'} с;
                {' '}карта и метрики {detail.timing.map_and_metrics_seconds?.toFixed(2) ?? '—'} с.
            </p>}
            {detail.model_steps?.[0]?.model_call && <p>
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
                <button disabled={busy} onClick={() => void apply()}>Применить эту версию</button>
                <p>
                    Структурные строки: {rows.length} (связей {relationCount});
                    {' '}рёбер карты: {detail.graph.semantic_edges?.length ?? 0}.
                </p>
                <PipelineStructuralRows
                    rows={rows}
                    nodes={detail.graph.nodes}
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
                <summary>DSL модели · {detail.model_steps[0].prompt_id ?? 'KM.ARTICLE_ROWS'} v{detail.model_steps[0].prompt_version ?? '—'}</summary>
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
