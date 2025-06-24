export interface BlockData {
  id: string;
  text: string;
  content?: string;
  x?: number;
  y?: number;
  level: number;
  sublevel: number;
  layer: number;
  isHovered?: boolean;
  hoveredArrow?: 'left' | 'right' | null;
  is_pinned?: boolean;
}

export interface LinkData {
  id: string;
  source_id: string;
  target_id: string;
}

export interface LevelData {
  id: number;
  sublevel_ids: number[];
  min_x?: number;
  max_x?: number;
  min_y?: number;
  max_y?: number;
  color?: string | number;
  name?: string;
}

export interface SublevelData {
  id: number;
  level_id: number;
  block_ids: string[];
  min_x?: number;
  max_x?: number;
  min_y?: number;
  max_y?: number;
  /** Hex color string (e.g. "#D3D3D3") or number (e.g. 0xD3D3D3) */
  color?: string | number;
  level?: number; // для обратной совместимости
}

export const EditMode = {
  SELECT: 'SELECT',
  CREATE_BLOCKS: 'CREATE_BLOCKS',
  CREATE_LINKS: 'CREATE_LINKS',
  DELETE: 'DELETE'
} as const;

export type EditMode = typeof EditMode[keyof typeof EditMode];

export type LinkCreationStep = 'waiting' | 'selecting_source' | 'selecting_target';

export type LinkCreationState = 
  | { step: 'waiting' }
  | { step: 'selecting_source' }
  | { step: 'selecting_target', sourceBlock: BlockData };