export type ArticleEditorTab = 'editor' | 'graph' | 'patterns';

export interface KnowledgeArticle {
    uid: string;
    title?: string;
    original_filename?: string;
    text?: string;
    statements?: KnowledgeStatement[];
    processing_status?: string;
    is_processed?: boolean;
    created_at?: string;
    updated_at?: string;
}

export interface KnowledgeStatement {
    id: string;
    subject_text: string;
    predicate: string;
    object_text: string;
    confidence?: number;
    sentence_text?: string;
    sort_order?: number;
    type?: string;
    subject_type?: string;
    object_type?: string;
}

export interface StatementSelection {
    index: number;
    statement: KnowledgeStatement;
    range?: { start: number; end: number };
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
