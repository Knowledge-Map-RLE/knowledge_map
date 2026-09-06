import { fetchJson } from "./http";

export interface CitationSourceStatus {
    key: string;
    name: string;
    url: string;
    source_type: string;
    description?: string;
    total_edges: number;
    downloaded_edges: number;
    progress_percent: number;
    status: CitationSourceState;
    error_message?: string;
    last_updated?: string;
}

export type CitationSourceState =
    | "idle"
    | "downloading"
    | "completed"
    | "error"
    | "paused";

export interface CitationTestResult {
    source_name: string;
    sample_size: number;
    elapsed_seconds: number;
    edges_found: number;
    estimated_total_edges?: number;
    estimated_time_seconds?: number;
    errors: string[];
    success: boolean;
}

export interface CitationStats {
    document_count: number;
    edge_count: number;
    source_breakdown: Record<string, number>;
}

export interface LoadOneResult {
    doi: string;
    total_edges_raw: number;
    unique_edges: number;
    written_ops: number;
    sources: Record<string, { edges: number; status: string; error?: string }>;
}

const BASE = "/api/citation_graph";

export async function getCitationSources(): Promise<CitationSourceStatus[]> {
    return fetchJson<CitationSourceStatus[]>(`${BASE}/sources`);
}

export async function getCitationSource(key: string): Promise<CitationSourceStatus> {
    return fetchJson<CitationSourceStatus>(`${BASE}/sources/${key}`);
}

export async function initCitationSources(): Promise<void> {
    await fetchJson(`${BASE}/initialize`, { method: "POST" });
}

export async function testCitationSource(key: string, sampleSize: number = 10): Promise<CitationTestResult> {
    return fetchJson<CitationTestResult>(`${BASE}/test/${key}?sample_size=${sampleSize}`, {
        method: "POST",
    });
}

export async function loadCitationSource(key: string, maxFiles?: number): Promise<void> {
    const qs = new URLSearchParams();
    if (maxFiles !== undefined && maxFiles > 0) {
        qs.set("max_files", String(maxFiles));
    }
    const suffix = qs.toString();
    await fetchJson(`${BASE}/load/${key}${suffix ? `?${suffix}` : ""}`, { method: "POST" });
}

export async function pauseCitationSource(key: string): Promise<void> {
    await fetchJson(`${BASE}/pause/${key}`, { method: "POST" });
}

export async function resumeCitationSource(key: string): Promise<void> {
    await fetchJson(`${BASE}/resume/${key}`, { method: "POST" });
}

export async function loadCitationAll(): Promise<void> {
    await fetchJson(`${BASE}/load_all`, { method: "POST" });
}

export async function loadCitationByDoi(doi: string): Promise<LoadOneResult> {
    return fetchJson<LoadOneResult>(`${BASE}/load_one`, {
        method: "POST",
        body: JSON.stringify({ doi }),
    });
}

export async function resetCitationSource(key: string): Promise<void> {
    await fetchJson(`${BASE}/reset/${key}`, { method: "POST" });
}

export async function getCitationStats(): Promise<CitationStats> {
    return fetchJson<CitationStats>(`${BASE}/stats`);
}
