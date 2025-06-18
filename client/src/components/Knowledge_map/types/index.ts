export interface BlockData {
  id: string;
  text: string;
  x: number;
  y: number;
  level?: number;
  layer: number;
  sublevel_id?: number;
}

export interface LinkData {
  id: string;
  fromId: string;
  toId: string;
}

export interface LevelData {
  id: number;
  sublevel_ids: number[];
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color: number;
}

export interface SublevelData {
  id: number;
  block_ids: string[];
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color: number;
  level_id: number;
}

export const EditMode = {
  SELECT: 'SELECT',
  CREATE_BLOCKS: 'CREATE_BLOCKS',
  CREATE_LINKS: 'CREATE_LINKS',
  DELETE: 'DELETE'
} as const;

export type EditMode = typeof EditMode[keyof typeof EditMode];

export interface LinkCreationState {
  step: 'waiting' | 'first_selected';
} 