export const EditMode = {
    SELECT: 'select',
    CREATE_BLOCKS: 'create_blocks',
    CREATE_LINKS: 'create_links',
    DELETE: 'delete',
} as const;

export type EditMode = (typeof EditMode)[keyof typeof EditMode];

export type LinkCreationStep = 'waiting' | 'select_source' | 'select_target';

export interface LinkCreationState {
    step: LinkCreationStep;
    sourceId?: string;
}

export interface PolylinePoint {
    x: number;
    y: number;
}

export interface BlockData {
    id: string;
    title: string;
    text?: string;
    x: number;
    y: number;
    level: number;
    layer?: number;
    sublevel?: number;
    is_pinned?: boolean;
    physical_scale?: number;
}

export interface LinkData {
    id: string;
    source_id: string;
    target_id: string;
    metadata?: Record<string, unknown>;
    polyline?: PolylinePoint[];
}

export interface LevelData {
    id: number;
    sublevel_ids: number[];
    name: string;
    color: string;
    min_x?: number;
    max_x?: number;
    min_y?: number;
    max_y?: number;
}

export interface SublevelData {
    id: number;
    level_id: number;
    block_ids: string[];
    color: string;
    min_x?: number;
    max_x?: number;
    min_y?: number;
    max_y?: number;
}
