export interface NLPAnalyzeRequest {
    text: string;
    start?: number;
    end?: number;
}

export interface NLPSuggestion {
    type: string;
    category: string;
    confidence: number;
    spacy_label?: string;
}

export interface NLPAnalyzeResponse {
    success: boolean;
    suggestions?: NLPSuggestion[];
    selected_text?: string;
    token_count?: number;
    error?: string;
}

export interface AutoAnnotateResponse {
    success: boolean;
    doc_id: string;
    created_annotations: number;
    created_relations: number;
    processors_used: string[];
    text_length: number;
}

export interface MultiLevelAnalysisResponse {
    doc_id: string;
    text_length: number;
    sentences: unknown[];
    summary: {
        total_sentences: number;
        total_tokens: number;
        agreement_score: number;
        pos_distribution: Record<string, number>;
        dependency_distribution: Record<string, number>;
    };
    graph: {
        nodes: Array<{
            id: number;
            label: string;
            type: 'token' | 'entity';
            pos?: string;
            entity_type?: string;
            confidence: number;
            sources: string[];
            sentence_idx: number;
        }>;
        edges: Array<{
            source: number;
            target: number;
            relation: string;
            confidence: number;
            sources?: string[];
        }>;
        metadata: {
            total_nodes: number;
            total_edges: number;
            sentences: number;
        };
    };
    created_annotations?: Array<{
        uid: string;
        text: string;
        type: string;
        confidence: number;
        start: number;
        end: number;
        color: string;
    }>;
    annotations_count?: number;
    processing_time: number;
    processed_levels: string[];
}

export interface Document {
    doc_id: string;
    has_markdown: boolean;
    processing_status: string;
    is_processed: boolean;
    title?: string;
    pubmed_id?: string;
    pmc_id?: string;
    files: Record<string, string>;
}

export interface DocumentProgress {
    doc_id: string;
    processing_status: string;
    percent: number;
    phase: string;
    message: string;
}

export interface DocumentAssets {
    success: boolean;
    markdown?: string;
    images?: string[];
    image_urls?: Record<string, string>;
    pdf_url?: string;
    files?: { pdf?: string; pdf_url?: string };
}

export interface DataExtractionResponse {
    success: boolean;
    doc_id?: string;
    message?: string;
    files?: Record<string, string>;
}

export interface PatternRow {
    pattern_str: string;
    pattern_type: string;
    frequency: number;
}

export interface AnnotationTypePatterns {
    annotation_type: string;
    patterns: PatternRow[];
    total_annotations: number;
}

export interface AnalyzePatternsResponse {
    success: boolean;
    doc_id: string;
    results: AnnotationTypePatterns[];
    total_patterns_saved: number;
    message: string;
}

export interface PendingEdge {
    src_uid: string;
    src_text: string;
    src_phrase: string;
    src_sentence: string;
    src_class: string;
    tgt_uid: string;
    tgt_text: string;
    tgt_phrase: string;
    tgt_sentence: string;
    tgt_class: string;
    relation_subtype: string;
    confidence: number;
    evidence: string[];
}

export interface PendingEdgesResponse {
    success: boolean;
    doc_id: string;
    edges: PendingEdge[];
    total: number;
}

export interface ReviewEdgeRequest {
    src_uid: string;
    tgt_uid: string;
    relation_subtype: string;
    decision: 'confirmed' | 'rejected';
}

export interface ExtractActionsResponse {
    success: boolean;
    doc_id: string;
    actions_count: number;
    edges_count: number;
    pending_count: number;
    message: string;
}

export interface ConfirmedActionNode {
    uid: string;
    verb: string;
    verb_text: string;
    object: string;
    full_phrase: string;
    sentence_text: string;
    action_class: string;
}

export interface ConfirmedActionEdge {
    src_uid: string;
    tgt_uid: string;
    relation_subtype: string;
    confidence: number;
}

export interface ConfirmedActionGraphResponse {
    success: boolean;
    doc_id: string;
    nodes: ConfirmedActionNode[];
    edges: ConfirmedActionEdge[];
    total_nodes: number;
    total_edges: number;
}

export interface AutoReviewEdgeDetail {
    src_uid: string;
    tgt_uid: string;
    src_phrase: string;
    tgt_phrase: string;
    relation_subtype: string;
    confidence: number;
    reason: string;
}

export interface AutoReviewResponse {
    success: boolean;
    doc_id: string;
    confirmed: number;
    rejected: number;
    total: number;
    confirmed_edges: AutoReviewEdgeDetail[];
    rejected_edges: AutoReviewEdgeDetail[];
    message: string;
}

export interface DataAvailabilityStatus {
    pdf_exists: boolean;
    markdown_exists: boolean;
    has_annotations: boolean;
    has_annotation_relations: boolean;
    has_action_graph: boolean;
    annotation_count: number;
    relation_count: number;
    action_node_count: number;
    action_edge_count: number;
    is_ready: boolean;
    missing_items: string[];
}

export interface SaveForTestsRequest {
    validate?: boolean;
}

export interface SaveForTestsResponse {
    success: boolean;
    sample_id: string;
    exported_files: string[];
    validation_result?: unknown;
    dvc_command: string;
    message?: string;
}

export interface ImportCSVResponse {
    success: boolean;
    message: string;
    created_annotations: number;
    created_relations: number;
    total_in_file: {
        annotations: number;
        relations: number;
    };
}

export interface PubMedSearchResult {
    pmid?: string;
    pmcid?: string;
    title: string;
    authors: string[];
    journal: string;
    pub_date: string;
    abstract: string;
    doi?: string;
    is_open_access: boolean;
    is_loaded?: boolean;
    source: string;
}

export interface PubMedSearchResponse {
    success: boolean;
    results: PubMedSearchResult[];
    total: number;
    query: string;
    db: string;
}

export interface PubMedIngestResponse {
    success: boolean;
    doc_id?: string;
    message: string;
    processing_status: string;
}

export interface LinguisticGraphNode {
    uid: string;
    _type: 'Action' | 'LexicalUnit';
    verb?: string;
    verb_text?: string;
    subject?: string;
    object?: string;
    full_phrase?: string;
    label_text?: string;
    sentence_text?: string;
    doc_id?: string;
    action_class?: string;
    norm_key?: string;
    text?: string;
    lemma?: string;
    pos?: string;
    pos_fine?: string;
    dep?: string;
    is_stop?: boolean;
    is_punct?: boolean;
    layout_x?: number | null;
    layout_y?: number | null;
}

export interface LinguisticGraphEdge {
    src_uid: string;
    tgt_uid: string;
    edge_type: 'LEADS_TO' | 'DEPENDS_ON' | 'PART_OF';
    relation_subtype?: string;
    confidence?: number;
    status?: string;
    dep_label?: string;
    token_index?: number;
    edge_count?: number;
}

export interface LinguisticGraphResponse {
    doc_id?: string;
    nodes: LinguisticGraphNode[];
    edges: LinguisticGraphEdge[];
}

export interface DependencyNgramResponse {
    success: boolean;
    max_depth: number;
    limit_per_n: number;
    unigrams: Array<{ pos: string; dep: string; lemma: string; node_type?: string; cnt: number }>;
    n_grams: Record<string, Array<{ chain: string[][]; cnt: number; sig_hash: string; exemplars: number[][] }>>;
    long_chains?: Array<{ texts: string[]; deps: string[]; depth: number; cnt: number; sig_hash: string; exemplars: number[][] }>;
    cross_doc: Array<{ lemmas: string[]; deps: string[]; depth: number; cnt: number }>;
}

export interface PatternContextResponse {
    success: boolean;
    node_ids: number[];
    sentences: string[];
}

export interface KnowledgeMapPageResponse {
    success: boolean;
    blocks: Array<{
        id: string;
        content: string;
        verb: string;
        verb_text: string;
        subject: string;
        object: string;
        action_class: string;
        norm_key: string;
        doc_count: number;
        doc_ids: string[];
        x: number;
        y: number;
    }>;
    links: Array<{
        id: string;
        source_id: string;
        target_id: string;
        count: number;
        confidence: number;
        relation_subtype: string;
    }>;
    page: { offset: number; limit: number; returned: number; total: number };
}

export interface PatternNodeData {
    node_id: string;
    node_type: 'Action' | 'LexicalUnit';
    role: string;
    text: string;
    lemma: string;
    pos: string;
    action_class: string;
    doc_id: string;
}

export interface PatternEdgeData {
    source_id: string;
    target_id: string;
    edge_type: 'LEADS_TO' | 'DEPENDS_ON' | 'PART_OF';
    relation_subtype: string;
    confidence: number;
}

export interface PatternData {
    uid: string;
    name: string;
    description: string;
    pattern_hash: string;
    frequency: number;
    stability: number;
    doc_count: number;
    node_count: number;
    edge_count: number;
    size_category: string;
    canon_nodes: PatternNodeData[];
    canon_edges: PatternEdgeData[];
}

export interface PatternGraphNode {
    uid: string;
    _type: 'Action' | 'LexicalUnit';
    verb?: string;
    text?: string;
    lemma?: string;
    pos?: string;
    action_class?: string;
    role?: string;
    doc_id?: string;
    layout_x: number | null;
    layout_y: number | null;
}

export interface PatternGraphEdge {
    src_uid: string;
    tgt_uid: string;
    edge_type: string;
    relation_subtype: string;
    confidence: number;
}

export interface PatternGraphData {
    uid: string;
    name: string;
    frequency: number;
    stability: number;
    doc_count: number;
    size_category: string;
    rendered_text: string;
    nodes: PatternGraphNode[];
    edges: PatternGraphEdge[];
}

export interface ExtractPatternsResponse {
    success: boolean;
    total_patterns: number;
    max_nodes_seen: number;
    extraction_mode: string;
    doc_ids: string[];
    patterns: PatternData[];
    status: 'idle' | 'running' | 'done' | 'error';
    progress: number;
    message: string;
    error: string | null;
    started_at: string | null;
    finished_at: string | null;
}

export interface SavePatternsResponse {
    success: boolean;
    saved_count: number;
    message: string;
}

export interface PatternCreateStatus {
    status: 'idle' | 'running' | 'done' | 'error';
    progress: number;
    message: string;
    total_patterns: number;
    saved_patterns: number;
    error: string | null;
    started_at: string | null;
    finished_at: string | null;
}
