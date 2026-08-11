import type { KnowledgeArticle, KnowledgeStatement, ArticleBlockData } from '../../pages/Article_editor/model';
import { fetchJson, withBase, authHeaders } from './http';

export interface ArticleResponse {
    success: boolean;
    article?: KnowledgeArticle;
}

export interface ArticleTextResponse {
    success: boolean;
    text?: string;
}

export interface ArticleListResponse {
    success: boolean;
    articles?: KnowledgeArticle[];
}

export interface SaveTextResponse {
    success: boolean;
    message?: string;
}

export interface SaveStatementsResponse {
    success: boolean;
    statement_ids?: string[];
}

export interface SaveStatementPayload {
    uid?: string;
    subject_text: string;
    predicate: string;
    object_text: string;
    subject_type?: string;
    object_type?: string;
    type?: string;
    confidence?: number;
    sentence_text?: string;
    sort_order?: number;
    sourceBlockId?: string;
}

export interface CreateArticleResponse {
    success?: boolean;
    uid?: string;
    title?: string;
    original_filename?: string;
}

export interface ParseTextResult {
    success?: boolean;
    statements?: KnowledgeStatement[];
    message?: string;
}

export interface ArticleGraphResponse {
    success: boolean;
    nodes: unknown[];
    edges: unknown[];
}

export async function createArticle(title: string = 'New Article'): Promise<CreateArticleResponse> {
    return fetchJson('/api/article_editor/articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
    });
}

export async function listArticles(skip = 0, limit = 200): Promise<ArticleListResponse> {
    return fetchJson(`/api/article_editor/articles?skip=${skip}&limit=${limit}`);
}

export async function getArticle(docId: string): Promise<ArticleResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}`);
}

export async function getArticleText(docId: string): Promise<ArticleTextResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/text`);
}

export interface AgentArticleTextResult {
    success: boolean;
    text: string;
    source: 'stored' | 'doi' | 'docling' | 'none';
}

export async function getAgentArticleText(docId: string, doi?: string): Promise<AgentArticleTextResult> {
    const params = new URLSearchParams();
    if (doi) params.set('doi', doi);
    const qs = params.toString();
    const url = `/api/article_editor/articles/${encodeURIComponent(docId)}/agent-text${qs ? `?${qs}` : ''}`;
    return fetchJson(url);
}

export async function saveArticleText(docId: string, text: string): Promise<SaveTextResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/text`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
    });
}

export async function saveStatements(docId: string, statements: SaveStatementPayload[]): Promise<SaveStatementsResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/statements`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ statements }),
    });
}

export async function saveBlocks(docId: string, blocks: ArticleBlockData[]): Promise<SaveTextResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/blocks`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blocks }),
    });
}

export async function getBlocks(docId: string): Promise<{ success: boolean; blocks?: ArticleBlockData[] }> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/blocks`);
}

export async function uploadArticleImage(docId: string, file: File): Promise<{ success: boolean; object_key?: string }> {
    const form = new FormData();
    form.append('doc_id', docId);
    form.append('file', file);
    return fetchJson('/api/article_editor/images', { method: 'POST', body: form });
}

export async function deleteArticleImage(objectKey: string): Promise<{ success: boolean }> {
    const encoded = objectKey.split('/').map(encodeURIComponent).join('/');
    return fetchJson(`/api/article_editor/images/${encoded}`, { method: 'DELETE' });
}

export function articleImageUrl(objectKey: string): string {
    const encoded = objectKey.split('/').map(encodeURIComponent).join('/');
    return withBase(`/api/article_editor/images/${encoded}`);
}

export async function updateArticleTitle(docId: string, title: string): Promise<SaveTextResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
    });
}

export async function parseText(text: string, docId = '', useLlm = false, save = false): Promise<ParseTextResult> {
    return fetchJson('/api/article_editor/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, doc_id: docId, use_llm: useLlm, save }),
    });
}

export async function getArticleGraph(docId: string): Promise<ArticleGraphResponse> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/graph`);
}

export interface SplitBlocksResult {
    success: boolean;
    blocks: ArticleBlockData[];
}

export async function splitIntoBlocks(text: string): Promise<SplitBlocksResult> {
    return fetchJson('/api/article_editor/split_into_blocks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
    });
}

export interface ParseProgress {
    processed: number;
    total: number;
}

export interface ParseStreamCallbacks {
    onProgress?: (progress: ParseProgress) => void;
    onResult?: (result: ParseTextResult) => void;
    onError?: (error: string) => void;
    signal?: AbortSignal;
}

export async function parseTextStream(
    text: string, docId = '', useLlm = false, save = false,
    callbacks: ParseStreamCallbacks = {},
): Promise<void> {
    const response = await fetch(withBase('/api/article_editor/parse_stream'), {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text, doc_id: docId, use_llm: useLlm, save }),
        signal: callbacks.signal,
    });
    if (!response.ok) {
        const body = await response.text().catch(() => '');
        callbacks.onError?.(`HTTP ${response.status}: ${body.slice(0, 200)}`);
        return;
    }
    const reader = response.body?.getReader();
    if (!reader) {
        callbacks.onError?.('No response body');
        return;
    }
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const payload = line.slice(6).trim();
            if (payload === '[DONE]') return;
            try {
                const msg = JSON.parse(payload);
                if (msg.type === 'progress') {
                    callbacks.onProgress?.({ processed: msg.processed, total: msg.total });
                } else if (msg.type === 'result') {
                    callbacks.onResult?.(msg.data as ParseTextResult);
                } else if (msg.type === 'start') {
                    // no-op
                }
            } catch { /* skip malformed */ }
        }
    }
}

export interface ExtractBlocksRequest {
    text: string;
    docId: string;
    lang?: 'ru' | 'en';
    model?: string;
    save?: boolean;
}

export interface ExtractBlocksResult {
    success?: boolean;
    blocks?: ArticleBlockData[];
    message?: string;
}

export interface ExtractBlocksCallbacks {
    onStart?: (total: number) => void;
    onProgress?: (progress: ParseProgress) => void;
    onResult?: (result: ExtractBlocksResult) => void;
    onError?: (error: string) => void;
    onCancelled?: () => void;
    signal?: AbortSignal;
}

/** SSE-поток: LLM-экстракция структурных блоков из текста статьи. */
export async function extractBlocksStream(
    req: ExtractBlocksRequest,
    callbacks: ExtractBlocksCallbacks = {},
): Promise<void> {
    const response = await fetch(withBase(`/api/article_editor/articles/${encodeURIComponent(req.docId)}/llm-extract`), {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            text: req.text,
            doc_id: req.docId,
            lang: req.lang || 'ru',
            model: req.model,
            save: req.save !== false,
        }),
        signal: callbacks.signal,
    });
    if (!response.ok) {
        const body = await response.text().catch(() => '');
        callbacks.onError?.(`HTTP ${response.status}: ${body.slice(0, 200)}`);
        return;
    }
    const reader = response.body?.getReader();
    if (!reader) {
        callbacks.onError?.('Нет ответа от сервера');
        return;
    }
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const payload = line.slice(6).trim();
            if (payload === '[DONE]') return;
            try {
                const msg = JSON.parse(payload);
                if (msg.type === 'start') {
                    callbacks.onStart?.(msg.total ?? 0);
                } else if (msg.type === 'progress') {
                    callbacks.onProgress?.({ processed: msg.processed, total: msg.total });
                } else if (msg.type === 'result') {
                    callbacks.onResult?.(msg.data as ExtractBlocksResult);
                } else if (msg.type === 'cancelled') {
                    callbacks.onCancelled?.();
                } else if (msg.type === 'error') {
                    callbacks.onError?.(msg.message || 'Ошибка извлечения');
                }
            } catch { /* skip malformed */ }
        }
    }
}

