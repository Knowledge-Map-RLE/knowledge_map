import type { Block, ApiResponse, LoadAroundResponse } from '../../entities/block';
import type { Link } from '../../entities/link';
import { fetchJson } from './http';

export const layoutApi = {
  async loadLayout(): Promise<ApiResponse> {
    return fetchJson<ApiResponse>('/layout/articles_page?offset=0&limit=1000');
  },

  async loadAround(centerX: number, centerY: number, limit: number = 1000): Promise<LoadAroundResponse> {
    return fetchJson<LoadAroundResponse>(`/layout/articles_page?offset=0&limit=${limit}&center_x=${centerX}&center_y=${centerY}`);
  },

  async loadArticlesPage(offset: number = 0, limit: number = 2000, centerX: number = 0, centerY: number = 0): Promise<ApiResponse> {
    return fetchJson<ApiResponse>(`/layout/articles_page?offset=${offset}&limit=${limit}&center_x=${centerX}&center_y=${centerY}`);
  },

  async createBlock(data: Partial<Block>): Promise<{ success: boolean; block: Block }> {
    return fetchJson<{ success: boolean; block: Block }>('/api/blocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async updateBlock(id: string, data: Partial<Block>): Promise<{ success: boolean; block: Block }> {
    return fetchJson<{ success: boolean; block: Block }>(`/api/blocks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async deleteBlock(id: string): Promise<{ success: boolean; error?: string }> {
    return fetchJson<{ success: boolean; error?: string }>(`/api/blocks/${id}`, {
      method: 'DELETE',
    });
  },
};

export async function loadLayout(): Promise<ApiResponse> {
  return layoutApi.loadLayout();
}

export async function loadAround(centerX: number, centerY: number, limit: number = 50): Promise<LoadAroundResponse> {
  return layoutApi.loadAround(centerX, centerY, limit);
}

export async function edgesByViewport(bounds: {left:number; right:number; top:number; bottom:number}): Promise<{blocks: Partial<Block>[]; links: Partial<Link>[]}> {
  return fetchJson<{blocks: Partial<Block>[]; links: Partial<Link>[]}>('/layout/api/articles/edges_by_viewport', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bounds)
  });
}

export async function createBlock(name: string): Promise<{ success: boolean; block: Block }> {
  return fetchJson<{ success: boolean; block: Block }>('/api/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: name })
  });
}

export async function deleteBlock(id: string): Promise<{ success: boolean; error?: string }> {
  return layoutApi.deleteBlock(id);
}

export async function createLink(sourceId: string, targetId: string): Promise<{ success: boolean; link: Link }> {
  return fetchJson<{ success: boolean; link: Link }>('/api/links', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId })
  });
}

export async function deleteLink(id: string): Promise<{ success: boolean; error?: string }> {
  return fetchJson<{ success: boolean; error?: string }>(`/api/links/${id}`, {
    method: 'DELETE'
  });
}

export async function createBlockAndLink(
  sourceId: string,
  direction: 'to_source' | 'from_source'
): Promise<{ success: boolean; new_block?: Block; new_link?: Link; error?: string }> {
  return fetchJson<{ success: boolean; new_block?: Block; new_link?: Link; error?: string }>('/api/create_block_and_link', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, direction })
  });
}

export async function pinBlock(blockId: string): Promise<{ success: boolean; error?: string }> {
  return fetchJson<{ success: boolean; error?: string }>(`/api/blocks/${blockId}/pin`, {
    method: 'POST'
  });
}

export async function unpinBlock(blockId: string): Promise<{ success: boolean; error?: string }> {
  return fetchJson<{ success: boolean; error?: string }>(`/api/blocks/${blockId}/unpin`, {
    method: 'POST'
  });
}

export async function pinBlockWithScale(blockId: string, physicalScale: number): Promise<{ success: boolean; error?: string }> {
  return fetchJson<{ success: boolean; error?: string }>(`/api/blocks/${blockId}/pin_with_scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ physical_scale: physicalScale })
  });
}

export async function moveBlockToLevel(blockId: string, targetLevel: number): Promise<{ success: boolean; error?: string }> {
  return fetchJson<{ success: boolean; error?: string }>(`/api/blocks/${blockId}/move_level`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_level: targetLevel })
  });
}

export async function getNLPMarkdown(filename: string): Promise<{ content?: string; error?: string }> {
  try {
    return await fetchJson<{ content?: string; error?: string }>(`/api/nlp/markdown/${encodeURIComponent(filename)}`);
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Network error';
    return { error: message };
  }
}

export async function getKnowledgeMapPage(
  offset = 0,
  limit = 200,
  centerX = 0,
  centerY = 0,
): Promise<ApiResponse> {
  return fetchJson<ApiResponse>(`/layout/knowledge_map_page?offset=${offset}&limit=${limit}&center_x=${centerX}&center_y=${centerY}`);
}
