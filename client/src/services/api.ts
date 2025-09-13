/**
 * API клиент для взаимодействия с бэкендом
 */

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

export interface Link {
    id: string;
  source_id: string;
  target_id: string;
    metadata?: Record<string, any>;
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

// API функции остаются теми же
export const api = {
  async loadLayout(): Promise<ApiResponse> {
    const response = await fetch('/layout/articles_page?offset=0&limit=1000');
    return response.json();
  },

  async loadAround(centerX: number, centerY: number, limit: number = 1000): Promise<LoadAroundResponse> {
    const response = await fetch(`/layout/articles_page?offset=0&limit=${limit}&center_x=${centerX}&center_y=${centerY}`);
    return response.json();
  },

  async loadArticlesPage(offset: number = 0, limit: number = 2000, centerX: number = 0, centerY: number = 0): Promise<ApiResponse> {
    const response = await fetch(`/layout/articles_page?offset=${offset}&limit=${limit}&center_x=${centerX}&center_y=${centerY}`);
    return response.json();
  },

  async createBlock(data: Partial<Block>): Promise<{ success: boolean; block: Block }> {
    const response = await fetch('/api/blocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return response.json();
  },

  async updateBlock(id: string, data: Partial<Block>): Promise<{ success: boolean; block: Block }> {
    const response = await fetch(`/api/blocks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return response.json();
  },

  async deleteBlock(id: string): Promise<{ success: boolean }> {
    const response = await fetch(`/api/blocks/${id}`, {
      method: 'DELETE',
    });
    return response.json();
  },
};

// Convenience wrappers for existing api methods
export async function loadLayout(): Promise<ApiResponse> {
  return api.loadLayout();
}

export async function loadAround(centerX: number, centerY: number, limit: number = 50): Promise<LoadAroundResponse> {
  return api.loadAround(centerX, centerY, limit);
}

export async function edgesByViewport(bounds: {left:number; right:number; top:number; bottom:number}): Promise<{blocks: Partial<Block>[]; links: Partial<Link>[]}>
{
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/articles/edges_by_viewport`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bounds)
  });
  return res.json();
}

// Обёртки для удобства использования в хуках
export async function createBlock(name: string): Promise<{ success: boolean; block: any }> {
  const response = await fetch('/api/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: name })
  });
  return response.json();
}

export async function deleteBlock(id: string): Promise<{ success: boolean }> {
  return api.deleteBlock(id);
}

export async function createLink(sourceId: string, targetId: string): Promise<{ success: boolean; link: any }> {
  const response = await fetch('/api/links', {
        method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId })
  });
    return response.json();
}

export async function deleteLink(id: string): Promise<{ success: boolean }> {
  const response = await fetch(`/api/links/${id}`, {
    method: 'DELETE'
  });
    return response.json();
}

export async function createBlockAndLink(
  sourceId: string,
  direction: 'to_source' | 'from_source'
): Promise<{ success: boolean; new_block?: any; new_link?: any; error?: string }> {
  const response = await fetch('/api/create_block_and_link', {
        method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, direction })
  });
  return response.json();
}

export async function pinBlock(blockId: string): Promise<{ success: boolean; error?: string }> {
  const response = await fetch(`/api/blocks/${blockId}/pin`, {
    method: 'POST'
  });
    return response.json();
}

export async function unpinBlock(blockId: string): Promise<{ success: boolean; error?: string }> {
  const response = await fetch(`/api/blocks/${blockId}/unpin`, {
    method: 'POST'
  });
    return response.json();
}

export async function pinBlockWithScale(blockId: string, physicalScale: number): Promise<{ success: boolean; error?: string }> {
  const response = await fetch(`/api/blocks/${blockId}/pin_with_scale`, {
            method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ physical_scale: physicalScale })
  });
  return response.json();
}

export async function moveBlockToLevel(blockId: string, targetLevel: number): Promise<{ success: boolean; error?: string }> {
  const response = await fetch(`/api/blocks/${blockId}/move_level`, {
            method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_level: targetLevel })
  });
  return response.json();
}

// NLP: загрузка markdown файла из S3 через бэкенд
export async function getNLPMarkdown(filename: string): Promise<{ content?: string; error?: string }> {
  try {
    const response = await fetch(`/api/nlp/markdown/${encodeURIComponent(filename)}`);
        if (!response.ok) {
      return { error: `HTTP ${response.status}` };
    }
    return response.json();
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Network error';
    return { error: message };
  }
}