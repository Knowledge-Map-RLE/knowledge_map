/**
 * API клиент для взаимодействия с бэкендом
 */

const API_BASE_URL = ((import.meta as any).env?.VITE_API_BASE_URL || '').replace(/\/$/, '');

const withBase = (path: string) => {
  if (!API_BASE_URL) {
    return path;
  }
  return path.startsWith('/') ? `${API_BASE_URL}${path}` : `${API_BASE_URL}/${path}`;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBase(path), init);
  const cloned = response.clone();
  try {
    return await response.json() as T;
  } catch (error) {
    const bodyPreview = await cloned.text().catch(() => '');
    throw new Error(`Failed to parse JSON from ${path}: ${bodyPreview.slice(0, 200)}`);
  }
}

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
    polyline?: unknown;
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

export interface DataExtractionResponse {
  success: boolean;
  doc_id?: string;
  message?: string;
  files?: Record<string, string>;
}

export async function uploadPdfForExtraction(file: File): Promise<DataExtractionResponse> {
  const form = new FormData();
  form.append('file', file);
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/data_extraction`, { method: 'POST', body: form });
  return res.json();
}

export async function importAnnotations(docId: string, annotations: any): Promise<{ success: boolean; key?: string }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_id: docId, annotations_json: annotations })
  });
  return res.json();
}

export async function exportAnnotations(docId: string): Promise<string> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/export?doc_id=${encodeURIComponent(docId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

export async function getDocumentAssets(docId: string): Promise<{ success: boolean; markdown?: string; images?: string[]; image_urls?: Record<string,string> }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/assets?include_urls=true`);
  return res.json();
}

export async function saveMarkdown(docId: string, markdown: string): Promise<{ success: boolean; doc_id: string; s3_key?: string; message?: string }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/markdown`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown })
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function deleteDocument(docId: string): Promise<{ success: boolean; deleted?: number }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
  return res.json();
}

export async function listDocuments(): Promise<{ success: boolean; documents: Array<{ doc_id: string; has_markdown: boolean; files: Record<string,string> }> }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents`);
  return res.json();
}

// API функции остаются теми же
export const api = {
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

  async deleteBlock(id: string): Promise<{ success: boolean }> {
    return fetchJson<{ success: boolean }>(`/api/blocks/${id}`, {
      method: 'DELETE',
    });
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
  return fetchJson<{blocks: Partial<Block>[]; links: Partial<Link>[]}>('/layout/api/articles/edges_by_viewport', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bounds)
  });
}

// Обёртки для удобства использования в хуках
export async function createBlock(name: string): Promise<{ success: boolean; block: any }> {
  return fetchJson<{ success: boolean; block: any }>('/api/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: name })
  });
}

export async function deleteBlock(id: string): Promise<{ success: boolean }> {
  return api.deleteBlock(id);
}

export async function createLink(sourceId: string, targetId: string): Promise<{ success: boolean; link: any }> {
  return fetchJson<{ success: boolean; link: any }>('/api/links', {
        method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId })
  });
}

export async function deleteLink(id: string): Promise<{ success: boolean }> {
  return fetchJson<{ success: boolean }>(`/api/links/${id}`, {
    method: 'DELETE'
  });
}

export async function createBlockAndLink(
  sourceId: string,
  direction: 'to_source' | 'from_source'
): Promise<{ success: boolean; new_block?: any; new_link?: any; error?: string }> {
  return fetchJson<{ success: boolean; new_block?: any; new_link?: any; error?: string }>('/api/create_block_and_link', {
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

// NLP: загрузка markdown файла из S3 через бэкенд
export async function getNLPMarkdown(filename: string): Promise<{ content?: string; error?: string }> {
  try {
    return await fetchJson<{ content?: string; error?: string }>(`/api/nlp/markdown/${encodeURIComponent(filename)}`);
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Network error';
    return { error: message };
  }
}
