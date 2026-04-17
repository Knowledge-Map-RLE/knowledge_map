export interface Link {
    id: string;
    source_id: string;
    target_id: string;
    metadata?: Record<string, unknown>;
    polyline?: unknown;
}

export interface CreateLinkRequest {
    source_id: string;
    target_id: string;
}

export interface CreateBlockAndLinkRequest {
    source_id: string;
    direction: 'to_source' | 'from_source';
}

export interface CreateBlockAndLinkResponse {
    success: boolean;
    new_block?: unknown;
    new_link?: unknown;
    error?: string;
}
