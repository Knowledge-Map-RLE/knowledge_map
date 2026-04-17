export interface Block {
    id: string;
    title: string;
    content?: string;
    x: number;
    y: number;
    layer: number;
    level: number;
    sublevel_id?: number;
    is_pinned?: boolean;
    physical_scale?: number;
}

export interface Level {
    id: number;
    sublevel_ids: number[];
    name: string;
    color: string;
}

export interface Sublevel {
    id: number;
    level_id: number;
    block_ids: string[];
    color: string;
}

export interface ApiResponse {
    success: boolean;
    blocks: Block[];
    links: Link[];
    levels: Level[];
    sublevels: Sublevel[];
    statistics: {
        total_blocks: number;
        total_layers: number;
        total_levels: number;
    };
}

export interface LoadAroundResponse {
    success: boolean;
    blocks: Block[];
    links: Link[];
    levels: Level[];
    sublevels: Sublevel[];
}

export interface CreateBlockRequest {
    content?: string;
    title?: string;
    x?: number;
    y?: number;
    layer?: number;
    level?: number;
}

export interface UpdateBlockRequest {
    title?: string;
    content?: string;
    x?: number;
    y?: number;
    layer?: number;
    level?: number;
    sublevel_id?: number;
    is_pinned?: boolean;
    physical_scale?: number;
}
