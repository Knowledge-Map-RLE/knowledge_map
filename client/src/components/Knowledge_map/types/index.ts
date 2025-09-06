export interface BlockData {
  id: string;
  title: string;
  x: number;
  y: number;
  layer: number;
  level: number;
  is_pinned?: boolean;
}

export interface LinkData {
  id: string;
  source: string;
  target: string;
  source_block?: BlockData;
  target_block?: BlockData;
}

export interface LevelData {
  id: number;
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color: string;
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