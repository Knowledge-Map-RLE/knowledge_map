export interface Annotation {
    uid: string;
    text: string;
    annotation_type: string;
    start_offset: number;
    end_offset: number;
    color: string;
    metadata?: Record<string, unknown>;
    confidence?: number;
    source?: 'user' | 'spacy' | 'custom' | 'file';
    processor_version?: string;
    created_date?: string;
}

export interface AnnotationRelation {
    relation_uid: string;
    source_uid: string;
    target_uid: string;
    relation_type: string;
    created_date?: string;
    metadata?: Record<string, unknown>;
    source_annotation_type?: string;
    source_text?: string;
    target_annotation_type?: string;
    target_text?: string;
}

export interface CreateAnnotationRequest {
    text: string;
    annotation_type: string;
    start_offset: number;
    end_offset: number;
    color?: string;
    metadata?: Record<string, unknown>;
    confidence?: number;
    user_id?: string;
}

export interface UpdateAnnotationRequest {
    text?: string;
    annotation_type?: string;
    start_offset?: number;
    end_offset?: number;
    color?: string;
    metadata?: Record<string, unknown>;
}

export interface CreateRelationRequest {
    target_id: string;
    relation_type: string;
    metadata?: Record<string, unknown>;
}

export interface AnnotationsResponse {
    annotations: Annotation[];
    total: number;
    skip: number;
    limit: number | null;
    has_more: boolean;
}

export interface AnnotationOffsetUpdate {
    annotation_id: string;
    start_offset: number;
    end_offset: number;
}

export interface BatchUpdateOffsetsRequest {
    updates: AnnotationOffsetUpdate[];
}

export interface BatchUpdateOffsetsResponse {
    success: boolean;
    updated_count: number;
    errors: string[];
}
