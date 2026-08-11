import { fetchJson } from './http';

export interface EvidenceMapNode {
    id: string;
    label: string;
}

export interface EvidenceMapEdge {
    from: string;
    to: string;
    label: string;
}

export interface EvidenceMapGraph {
    nodes: EvidenceMapNode[];
    edges: EvidenceMapEdge[];
}

export interface EvidenceClaim {
    subject: string;
    predicate: string;
    object: string;
    negated?: boolean;
    domain?: string;
    confidence?: number;
}

export interface EvidenceFinding {
    parameter: string;
    domain?: string;
    polarity?: string;
    direction?: string;
    significance?: string;
    p?: number | null;
    group_role?: string;
    claim_ref?: string;
    experiment?: string;
}

export interface EvidenceExperiment {
    name: string;
    type?: string;
    verdict?: string;
    control_groups?: string[];
    exp_groups?: string[];
    findings?: string[];
}

export interface EvidenceMap {
    hypothesis?: string;
    goals?: string[];
    claims?: EvidenceClaim[];
    experiments?: EvidenceExperiment[];
    findings?: EvidenceFinding[];
    method_flags?: Record<string, boolean>;
    verdict?: string;
    graph?: EvidenceMapGraph;
    model_id?: string;
    created_at?: string;
    uid?: string;
}

export interface GenerateMapResult {
    success: boolean;
    map?: EvidenceMap;
    message?: string;
    tokens?: { input: number; output: number };
}

export interface SaveMapResult {
    success: boolean;
    uid?: string;
    verdict?: string;
    message?: string;
}

export interface MinePattern {
    id: string;
    size: number;
    edges_count: number;
    support: number;
    support_ratio: number;
    graphs: string[];
    nodes: string[];
    edges: number[][];
    verdict_histogram?: Record<string, number>;
}

export interface MineResult {
    success: boolean;
    patterns: MinePattern[];
    corpus_size: number;
    message?: string;
}

export interface MatchResult {
    success: boolean;
    matched: unknown[];
    prediction?: {
        verdict: string;
        confidence: number;
        weighted_histogram: Record<string, number>;
        matched_count: number;
        method_flags: Record<string, boolean>;
    } | null;
    message?: string;
}

export async function generateEvidenceMap(docId: string, modelId?: string): Promise<GenerateMapResult> {
    return fetchJson(`/api/article_editor/patterns/generate?doc_id=${encodeURIComponent(docId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
    });
}

export async function saveEvidenceMap(docId: string, map: EvidenceMap): Promise<SaveMapResult> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/evidence-map`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map }),
    });
}

export async function getEvidenceMap(docId: string): Promise<{ map: EvidenceMap; success: boolean }> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/evidence-map`);
}

export async function deleteEvidenceMap(docId: string): Promise<{ success: boolean }> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/evidence-map`, { method: 'DELETE' });
}

export async function listEvidenceMaps(): Promise<{ maps: Array<{ doc_id: string; verdict: string; created_at: string; model_id: string }>; success: boolean }> {
    return fetchJson('/api/article_editor/patterns/maps');
}

export async function minePatterns(
    opts: { doc_ids?: string[]; min_support?: number; min_size?: number; max_size?: number; limit?: number } = {},
): Promise<MineResult> {
    return fetchJson('/api/article_editor/patterns/mine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            doc_ids: opts.doc_ids,
            min_support: opts.min_support ?? 0.6,
            min_size: opts.min_size ?? 2,
            max_size: opts.max_size ?? 4,
            limit: opts.limit ?? 2000,
        }),
    });
}

export async function matchEvidenceMap(
    docId: string,
    opts: { min_support?: number; min_size?: number; max_size?: number; limit?: number } = {},
): Promise<MatchResult> {
    return fetchJson(`/api/article_editor/articles/${encodeURIComponent(docId)}/evidence-map/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            min_support: opts.min_support ?? 1.0,
            min_size: opts.min_size ?? 2,
            max_size: opts.max_size ?? 4,
            limit: opts.limit ?? 2000,
        }),
    });
}
