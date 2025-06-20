export interface BlockData {
  id: string;
  text: string;
  x: number;
  y: number;
  level: number;
  sublevel: number;
  layer: number;
}

export interface LinkData {
  id: string;
  source_id: string;
  target_id: string;
}

export interface LevelData {
  id: number;
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color?: number;
  name?: string;
}

export interface SublevelData {
  id: number;
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  /** Hex color number (e.g. 0xD3D3D3) */
  color: number;
  block_ids: string[];
  level: number;
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