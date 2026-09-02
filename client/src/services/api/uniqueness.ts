import { fetchJson } from './http';

export interface UniquenessResponse {
    success: boolean;
    status: 'SAME' | 'UNCERTAIN' | 'DIFFERENT' | 'NEW' | 'UNKNOWN';
    existing_statement_id: string;
    confidence: number;
    candidates: {
        statement_id: string;
        similarity: number;
        subject_text: string;
        predicate: string;
        object_text: string;
    }[];
    message: string;
}

export interface AddStatementResponse {
    success: boolean;
    uniqueness_status: 'SAME' | 'UNCERTAIN' | 'DIFFERENT' | 'NEW' | 'UNKNOWN';
    statement_id: string;
    existing_statement_id: string;
    message: string;
}

export interface MatchedElementUids {
    as_subject: string[];
    as_object: string[];
}

export interface PatternMatchData {
    pattern_to_graph: Record<string, string>;
    matched_node_ids: string[];
    node_uids?: Record<string, MatchedElementUids>;
    edge_uids?: Record<string, string[]>;
}

export interface CheckSubgraphResponse {
    success: boolean;
    status: 'SAME' | 'UNCERTAIN' | 'DIFFERENT' | 'NEW' | 'UNKNOWN';
    wl_hash: string;
    existing_subgraph_id: string;
    subgraph_matches: PatternMatchData[];
    frequent_patterns: unknown[];
    message: string;
}

export interface CheckPatternResponse {
    success: boolean;
    status: 'SAME' | 'UNCERTAIN' | 'DIFFERENT' | 'NEW' | 'UNKNOWN';
    matches: PatternMatchData[];
    total_matches: number;
    message: string;
}

export async function checkUniqueness(input: {
    subject_text: string;
    predicate: string;
    object_text: string;
    sentence_text: string;
}): Promise<UniquenessResponse> {
    return fetchJson<UniquenessResponse>('/api/uniqueness/check', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export async function addStatementWithUniqueness(input: {
    subject_text: string;
    predicate: string;
    object_text: string;
    sentence_text: string;
    doc_id: string;
}): Promise<AddStatementResponse> {
    return fetchJson<AddStatementResponse>('/api/uniqueness/add', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export async function checkSubgraphUniqueness(input: {
    nodes: { id: string; node_type: string; text?: string; predicate?: string }[];
    edges: { source_id: string; target_id: string; edge_type?: string; predicate?: string }[];
}): Promise<CheckSubgraphResponse> {
    return fetchJson<CheckSubgraphResponse>('/api/uniqueness/check-subgraph', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export async function checkPatternMatch(input: {
    nodes: { id: string; required_type?: string; text_constraint?: string; predicate_constraint?: string }[];
    edges: { source_id: string; target_id: string; required_edge_type?: string; predicate_constraint?: string }[];
    max_results?: number;
}): Promise<CheckPatternResponse> {
    return fetchJson<CheckPatternResponse>('/api/uniqueness/check-pattern', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}
