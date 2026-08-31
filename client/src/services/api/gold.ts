import { fetchJson } from './http';

export interface GoldCaseSummary {
    slug: string;
    article_title?: string;
    doi?: string;
    lang?: string;
    doc_id?: string | null;
    needs_review?: boolean;
}

export interface GoldCasesResponse {
    success: boolean;
    cases: GoldCaseSummary[];
    by_doc_id?: Record<string, string>;
}

export interface GoldCaseResponse {
    success: boolean;
    slug: string;
    meta: Record<string, unknown>;
    article_text: string;
    blocks: Array<Record<string, unknown>>;
}

export interface FixGoldResult {
    slug: string;
    created: boolean;
}

export async function listGoldCases(): Promise<GoldCasesResponse> {
    return fetchJson<GoldCasesResponse>('/api/article_editor/gold/cases');
}

export async function createGoldCase(docId: string, blocks: unknown[]): Promise<FixGoldResult> {
    const res = await fetchJson<{ success: boolean; slug: string }>('/api/article_editor/gold/cases', {
        method: 'POST',
        body: JSON.stringify({ doc_id: docId, blocks }),
    });
    return { slug: res.slug, created: true };
}

export async function updateGoldCase(slug: string, blocks: unknown[]): Promise<FixGoldResult> {
    const res = await fetchJson<{ success: boolean; slug: string }>(
        `/api/article_editor/gold/cases/${encodeURIComponent(slug)}`,
        { method: 'PUT', body: JSON.stringify({ blocks }) },
    );
    return { slug: res.slug || slug, created: false };
}
