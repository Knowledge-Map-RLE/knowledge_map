import { fetchJson } from './http';

export async function createArticle(title: string = 'New Article'): Promise<any> {
    return fetchJson('/api/article_editor/articles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
    });
}

export async function listArticles(skip = 0, limit = 200): Promise<any> {
    return fetchJson(`/api/article_editor/articles?skip=${skip}&limit=${limit}`);
}

export async function getArticle(docId: string): Promise<any> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}`);
}

export async function getArticleText(docId: string): Promise<any> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/text`);
}

export async function saveArticleText(docId: string, text: string): Promise<any> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/text`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
    });
}

export async function saveStatements(docId: string, statements: any[]): Promise<any> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/statements`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ statements }),
    });
}

export async function parseText(text: string, docId = '', useLlm = false, save = false): Promise<any> {
    return fetchJson('/api/article_editor/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, doc_id: docId, use_llm: useLlm, save }),
    });
}

export async function getArticleGraph(docId: string): Promise<any> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/graph`);
}

export interface ParseProgress {
    processed: number;
    total: number;
}

export interface ParseStreamCallbacks {
    onProgress?: (progress: ParseProgress) => void;
    onResult?: (result: any) => void;
    onError?: (error: string) => void;
    signal?: AbortSignal;
}

export async function parseTextStream(
    text: string, docId = '', useLlm = false, save = false,
    callbacks: ParseStreamCallbacks = {},
): Promise<void> {
    const base = ((import.meta as any).env?.VITE_API_BASE_URL || '').replace(/\/$/, '');
    const url = `${base}/api/article_editor/parse_stream`;
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
                    callbacks.onResult?.(msg.data);
                } else if (msg.type === 'start') {
                    // no-op
                }
            } catch { /* skip malformed */ }
        }
    }
}

export { fetchJson }; // re-export for convenience
