import { fetchJson } from './http';

export interface PatternMinerPattern {
    id: string;
    size: number;
    edges_count: number;
    support: number;
    support_ratio: number;
    graphs: string[];
    nodes: string[];
    edges: [number, number, string][];
    examples?: { subject_text: string; predicate: string; object_text: string; doc_id?: string }[];
}

export interface MinePatternsResponse {
    success: boolean;
    patterns: PatternMinerPattern[];
    corpus_size: number;
    using_graphs: number;
    message?: string;
    params?: {
        min_support: number;
        min_size: number;
        max_size: number;
        predicate_mode: string;
    };
}

export interface CorpusDocument {
    doc_id: string;
    statements_count: number;
}

export interface GapCandidate {
    subject_text: string;
    predicate: string;
    object_text: string;
    edge: [number, number, string];
}

export interface PatternEmbedding {
    pattern_to_graph: Record<string, string>;
    matched_nodes: string[];
    matched_edges: [number, number, string][];
    missing_edges: [number, number, string][];
    matched_count: number;
    missing_count: number;
    complete: boolean;
    pattern_key: string;
}

export interface ApplyPatternResult {
    pattern: {
        id: string;
        size: number;
        edges_count: number;
        support: number;
        nodes: string[];
        edges: [number, number, string][];
    };
    embeddings: PatternEmbedding[];
    gaps: GapCandidate[];
    complete_matches: number;
    partial_matches: number;
    target_doc_id?: string;
    target_node_count?: number;
    target_edge_count?: number;
}

// ── Генерация нового знания (4 способа) ────────────────────────────────────

export type KnowledgeMethod = 'pattern' | 'logical' | 'syllogism' | 'thinking';

export interface KnowledgeCheck {
    subject_text: string;
    predicate: string;
    object_text: string;
    status: 'new' | 'exists' | 'conflicts';
    check_mode?: 'new' | 'exists' | 'conflicts';
    evidence_doc_ids?: string[];
    conflicting_direction?: string;
    note?: string;
}

export interface GeneratedStatement {
    subject_text: string;
    predicate: string;
    object_text: string;
    subject_type?: string;
    object_type?: string;
    doc_id?: string;
    check?: KnowledgeCheck;
}

export interface GenerationProvenance {
    method: string;
    method_label: string;
    operation: string;
    operation_label: string;
    source_count: number;
    new_count: number;
}

export interface GenerationGroup {
    knowledge_method: string;
    operation: string;
    operation_label: string;
    description: string;
    source_statements: GeneratedStatement[];
    new_statements: GeneratedStatement[];
    provenance: GenerationProvenance;
    checks?: KnowledgeCheck[];
}

export interface MethodOption {
    value: string;
    label: string;
    description: string;
    operations: { value: string; label: string }[];
    moduses?: { name: string; mood: string; figure: number }[];
    info?: string;
}

export interface GenerationApplyResult {
    knowledge_method: string;
    operation?: string | null;
    results: GenerationGroup[];
    corpus_size: number;
}

export interface ApplyPatternResponse {
    success: boolean;
    message?: string;
    target_doc_id?: string;
    result: ApplyPatternResult | null;
    knowledge_method?: string;
    operation?: string | null;
    results?: GenerationGroup[];
    corpus_size?: number;
    corpus_pool_size?: number;
}

export interface GenerateAllMethod {
    method: string;
    label: string;
    count: number;
    groups: GenerationGroup[];
}

export interface GenerateAllResponse {
    success: boolean;
    message?: string;
    knowledge_method?: string;
    corpus_size?: number;
    corpus_pool_size?: number;
    methods?: GenerateAllMethod[];
}

export interface MinerMethodsResponse {
    success: boolean;
    methods: MethodOption[];
}

export async function listMinerDocuments(): Promise<{ success: boolean; documents: CorpusDocument[] }> {
    return fetchJson('/api/pattern-miner/documents');
}

export async function minePatterns(input: {
    doc_ids?: string[];
    min_support?: number;
    min_size?: number;
    max_size?: number;
    limit?: number;
    predicate_mode?: string;
    useful_only?: boolean;
    statements_per_doc_cap?: number;
    max_nodes?: number;
}): Promise<MinePatternsResponse> {
    return fetchJson<MinePatternsResponse>('/api/pattern-miner/mine', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export interface ApplyPatternRequest {
    doc_id: string;
    pattern?: Pick<PatternMinerPattern, 'id' | 'size' | 'edges_count' | 'support' | 'nodes' | 'edges'>;
    predicate_mode?: string;
    max_nodes?: number;
    knowledge_method?: KnowledgeMethod;
    operation?: string | null;
    check_existing?: boolean;
    limit?: number;
    statements_per_doc_cap?: number;
    corpus_doc_ids?: string[];
}

export interface GenerateKnowledgeRequest {
    corpus_doc_ids?: string[];
    predicate_mode?: string;
    check_existing?: boolean;
    limit_per_method?: number;
    max_nodes?: number;
    min_support?: number;
    min_size?: number;
    max_size?: number;
    statements_per_doc_cap?: number;
}

export async function generateKnowledge(input: GenerateKnowledgeRequest): Promise<GenerateAllResponse> {
    return fetchJson<GenerateAllResponse>('/api/pattern-miner/generate', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export async function applyPattern(input: ApplyPatternRequest): Promise<ApplyPatternResponse> {
    return fetchJson<ApplyPatternResponse>('/api/pattern-miner/apply', {
        method: 'POST',
        body: JSON.stringify(input),
    });
}

export async function listMinerMethods(): Promise<MinerMethodsResponse> {
    return fetchJson<MinerMethodsResponse>('/api/pattern-miner/methods');
}