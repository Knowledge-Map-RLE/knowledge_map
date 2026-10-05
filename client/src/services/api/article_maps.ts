import { authHeaders, fetchJson, withBase } from './http';

export type MapPipelineId = 'text_reified' | 'structural_rows';
export interface SavedArticleMapGraph {
    schema_version: number;
    /** Словарь участников схемы 5 не становится узлами отображаемой карты. */
    concepts?: Array<{ id: string; display_text: string; aliases: string[] }>;
    analysis?: { depth: number; layer_counts: Record<string, number>; knowledge_input_count: number;
        concept_count: number; operation_count: number };
    nodes: Array<{
        id: string; block_type: string; kind?: string; order: number; rank: number;
        display_text: string; is_goal?: boolean;
    }>;
    edges: Array<{ source: string; target: string }>;
}
export interface ArticleMapSummary {
    pipeline_id: MapPipelineId; run_id: string; updated_at: string;
    graph_schema_version: number; input_fingerprint: string; builder_version: string;
    translated_locales?: string[];
    prompt?: { id: string; version: string; sha256: string };
}
export interface SavedArticleMap extends ArticleMapSummary {
    article_id: string;
    graph: SavedArticleMapGraph;
    locale?: 'en' | 'ru';
}
export interface ArticleMapInventory {
    maps: ArticleMapSummary[];
    availability: Record<MapPipelineId, boolean>;
}
const base = (docId: string) => `/api/article_editor/articles/${encodeURIComponent(docId)}/maps`;
export const listArticleMaps = (docId: string, signal?: AbortSignal) =>
    fetchJson<ArticleMapInventory>(base(docId), { signal });
export const getArticleMap = (docId: string, pipeline: MapPipelineId, locale: 'en' | 'ru', signal?: AbortSignal) =>
    fetchJson<SavedArticleMap>(`${base(docId)}/${pipeline}?locale=${locale}`, { signal });
export const buildStructuralArticleMap = (docId: string, signal?: AbortSignal) =>
    fetchJson<SavedArticleMap>(`${base(docId)}/structural_rows/build`, { method: 'POST', signal });
export const translateArticleMap = (docId: string, pipeline: MapPipelineId, signal: AbortSignal) =>
    readArticleMapStream(`${base(docId)}/${pipeline}/translate`, signal, () => {});

/** Повреждённый или оборванный SSE-ответ не считается успешным построением. */
export async function buildTextArticleMap(
    docId: string, signal: AbortSignal, onProgress: (stage: string) => void,
): Promise<SavedArticleMap> {
    return readArticleMapStream<SavedArticleMap>(`${base(docId)}/text_reified/build`, signal, onProgress);
}

async function readArticleMapStream<T>(url: string, signal: AbortSignal, onProgress: (stage: string) => void): Promise<T> {
    const response = await fetch(withBase(url), {
        method: 'POST', headers: authHeaders(), signal,
    });
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${response.status}`);
    }
    if (!response.body) throw new Error('Empty server stream');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let result: T | null = null;
    let terminal = false;
    try {
        while (!terminal) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            buffer = buffer.replace(/\r\n/g, '\n');
            let boundary: number;
            while ((boundary = buffer.indexOf('\n\n')) !== -1) {
                const frame = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);
                const payload = frame.split('\n').filter(line => line.startsWith('data:'))
                    .map(line => line.slice(5).trimStart()).join('\n');
                if (!payload) continue;
                if (payload === '[DONE]') { terminal = true; break; }
                const event = JSON.parse(payload);
                if (event.type === 'error') throw new Error(event.message);
                if (event.type === 'cancelled') throw new DOMException('Cancelled', 'AbortError');
                if (event.type === 'progress') onProgress(event.stage);
                if (event.type === 'result') result = event.data as T;
            }
        }
        if (!terminal || !result) throw new Error('Incomplete article map stream');
        return result;
    } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
    }
}
