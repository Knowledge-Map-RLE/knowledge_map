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

export async function uploadPdfForExtraction(file: File, onProgress?: (progress: number) => void): Promise<DataExtractionResponse> {
  const form = new FormData();
  form.append('file', file);
  
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  
  // If progress tracking is requested, use XMLHttpRequest instead of fetch
  if (onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const percentComplete = Math.round((event.loaded / event.total) * 100);
          onProgress(percentComplete);
        }
      });
      
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve(response);
          } catch (e) {
            reject(new Error('Failed to parse response'));
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      });
      
      xhr.addEventListener('error', () => {
        reject(new Error('Network error'));
      });
      
      xhr.open('POST', `${base}/api/data_extraction/data_extraction`);
      xhr.send(form);
    });
  } else {
    // Use fetch for simple upload without progress
    const res = await fetch(`${base}/api/data_extraction/data_extraction`, { method: 'POST', body: form });
    return res.json();
  }
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

export async function getDocumentProgress(docId: string): Promise<{ doc_id: string; processing_status: string; percent: number; phase: string; message: string }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/progress`);
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

export async function listDocuments(): Promise<{ success: boolean; documents: Array<{ doc_id: string; has_markdown: boolean; title?: string; pubmed_id?: string; pmc_id?: string; files: Record<string,string> }> }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents`);
  return res.json();
}

// --- PubMed / PMC ---

export interface PubMedSearchResult {
  pmid?: string;
  pmcid?: string;
  title: string;
  authors: string[];
  journal: string;
  pub_date: string;
  abstract: string;
  doi?: string;
  is_open_access: boolean;
  source: string;
}

export interface PubMedSearchResponse {
  success: boolean;
  results: PubMedSearchResult[];
  total: number;
  query: string;
  db: string;
}

export interface PubMedIngestResponse {
  success: boolean;
  doc_id?: string;
  message: string;
  processing_status: string;
}

export async function searchPubMed(
  query: string,
  limit: number = 10
): Promise<PubMedSearchResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ query, limit: String(limit) });
  const res = await fetch(`${base}/api/data_extraction/pubmed/search?${params}`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function getByPubMedId(id: string): Promise<PubMedSearchResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ id });
  const res = await fetch(`${base}/api/data_extraction/pubmed/by-id?${params}`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function ingestPubMedArticle(
  pmid?: string,
  pmcid?: string,
  source: string = 'pubmed'
): Promise<PubMedIngestResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/pubmed/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pmid, pmcid, source }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
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

// ==================== ANNOTATION API ====================

export interface Annotation {
  uid: string;
  text: string;
  annotation_type: string;
  start_offset: number;
  end_offset: number;
  color: string;
  metadata?: Record<string, any>;
  confidence?: number;
  source?: 'user' | 'spacy' | 'custom' | 'file';
  processor_version?: string;
  created_date?: string;
}

export interface AnnotationRelation {
  relation_uid: string;
  source_uid: string;
  target_uid: string;
  relation_type: string;
  created_date?: string;
  metadata?: Record<string, any>;
  // Денормализованные поля для отображения (заполняются на клиенте)
  source_annotation_type?: string;
  source_text?: string;
  target_annotation_type?: string;
  target_text?: string;
}

export interface CreateAnnotationRequest {
  text: string;
  annotation_type: string;
  start_offset: number;
  end_offset: number;
  color?: string;
  metadata?: Record<string, any>;
  confidence?: number;
  user_id?: string;
}

export interface UpdateAnnotationRequest {
  text?: string;
  annotation_type?: string;
  start_offset?: number;
  end_offset?: number;
  color?: string;
  metadata?: Record<string, any>;
}

export interface CreateRelationRequest {
  target_id: string;
  relation_type: string;
  metadata?: Record<string, any>;
}

export interface NLPAnalyzeRequest {
  text: string;
  start?: number;
  end?: number;
}

export interface NLPSuggestion {
  type: string;
  category: string;
  confidence: number;
  spacy_label?: string;
}

export interface NLPAnalyzeResponse {
  success: boolean;
  suggestions?: NLPSuggestion[];
  selected_text?: string;
  token_count?: number;
  error?: string;
}

// Создать аннотацию
export async function createAnnotation(docId: string, request: CreateAnnotationRequest): Promise<Annotation> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  return data.annotation ?? data;
}

// Интерфейс для ответа с пагинацией аннотаций
export interface AnnotationsResponse {
  annotations: Annotation[];
  total: number;
  skip: number;
  limit: number | null;
  has_more: boolean;
}

// Получить аннотации документа с пагинацией и фильтрацией
export async function getAnnotations(
  docId: string,
  skip: number = 0,
  limit: number | null = null,
  annotationTypes: string[] | null = null,
  source: string | null = null
): Promise<AnnotationsResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams();

  params.append('skip', skip.toString());
  if (limit !== null) params.append('limit', limit.toString());
  if (annotationTypes && annotationTypes.length > 0) params.append('annotation_types', annotationTypes.join(','));
  if (source) params.append('source', source);

  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations?${params}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Обновить аннотацию
export async function updateAnnotation(annotationId: string, request: UpdateAnnotationRequest): Promise<Annotation> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Удалить аннотацию
export async function deleteAnnotation(annotationId: string): Promise<{ message: string }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Удалить все аннотации документа
export async function deleteAllAnnotations(docId: string): Promise<{ success: boolean; message: string; deleted_count: number }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations/all`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to delete all annotations: ${errText}`);
  }
  return res.json();
}

// Массовое обновление offset аннотаций
export interface AnnotationOffsetUpdate {
  annotation_id: string;
  start_offset: number;
  end_offset: number;
}

export interface BatchUpdateOffsetsRequest {
  updates: AnnotationOffsetUpdate[];
}

export interface BatchUpdateOffsetsResponse {
  success: boolean;
  updated_count: number;
  errors: string[];
}

export async function batchUpdateAnnotationOffsets(request: BatchUpdateOffsetsRequest): Promise<BatchUpdateOffsetsResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/batch-update-offsets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Создать связь между аннотациями
export async function createAnnotationRelation(sourceId: string, request: CreateRelationRequest): Promise<AnnotationRelation> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/${encodeURIComponent(sourceId)}/relations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  // Бэкенд возвращает {success: true, relation: {...}} — извлекаем вложенный объект
  return data.relation ?? data;
}

// Удалить связь между аннотациями
export async function deleteAnnotationRelation(sourceId: string, targetId: string): Promise<{ message: string }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/${encodeURIComponent(sourceId)}/relations/${encodeURIComponent(targetId)}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Получить все связи документа
export async function getAnnotationRelations(docId: string): Promise<AnnotationRelation[]> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/relations`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  return Array.isArray(data) ? data : (data.relations ?? []);
}

// NLP анализ текста
export async function analyzeText(request: NLPAnalyzeRequest): Promise<NLPAnalyzeResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/nlp/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Интерфейс для ответа автоаннотации
export interface AutoAnnotateResponse {
  success: boolean;
  doc_id: string;
  created_annotations: number;
  created_relations: number;
  processors_used: string[];
  text_length: number;
}

// Автоматическая аннотация документа с помощью spaCy
export async function autoAnnotateDocument(
  docId: string,
  processors: string[] = ['spacy'],
  annotationTypes: string[] | null = null,
  minConfidence: number = 0.7
): Promise<AutoAnnotateResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${docId}/auto-annotate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      processors,
      annotation_types: annotationTypes,
      min_confidence: minConfidence
    })
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}

// Multi-level NLP analysis response
export interface MultiLevelAnalysisResponse {
  doc_id: string;
  text_length: number;
  sentences: any[];
  summary: {
    total_sentences: number;
    total_tokens: number;
    agreement_score: number;
    pos_distribution: Record<string, number>;
    dependency_distribution: Record<string, number>;
  };
  graph: {
    nodes: Array<{
      id: number;
      label: string;
      type: 'token' | 'entity';
      pos?: string;
      entity_type?: string;
      confidence: number;
      sources: string[];
      sentence_idx: number;
    }>;
    edges: Array<{
      source: number;
      target: number;
      relation: string;
      confidence: number;
      sources?: string[];
    }>;
    metadata: {
      total_nodes: number;
      total_edges: number;
      sentences: number;
    };
  };
  created_annotations?: Array<{
    uid: string;
    text: string;
    type: string;
    confidence: number;
    start: number;
    end: number;
    color: string;
  }>;
  annotations_count?: number;
  processing_time: number;
  processed_levels: string[];
}

// Multi-level автоматическая аннотация с голосованием
export async function autoAnnotateMultilevel(
  docId: string,
  enableVoting: boolean = true,
  maxLevel: number = 3,
  createAnnotations: boolean = true,
  minConfidence: number = 0.8
): Promise<MultiLevelAnalysisResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${docId}/analyze-multilevel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enable_voting: enableVoting,
      max_level: maxLevel,
      create_annotations: createAnnotations,
      min_confidence: minConfidence
    })
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}

// Интерфейс для ответа импорта CSV
export interface ImportCSVResponse {
  success: boolean;
  message: string;
  created_annotations: number;
  created_relations: number;
  total_in_file: {
    annotations: number;
    relations: number;
  };
}

// Экспорт аннотаций в YAML
export async function exportAnnotationsYAML(docId: string): Promise<Blob> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/export-yaml?doc_id=${encodeURIComponent(docId)}`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.blob();
}

// Импорт аннотаций из YAML
export async function importAnnotationsYAML(docId: string, file: File): Promise<ImportCSVResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${base}/api/data_extraction/annotations/import-yaml?doc_id=${encodeURIComponent(docId)}`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}

// ==================== CSV IMPORT/EXPORT (CLIENT-SIDE) ====================

function csvEscape(value: string): string {
  const str = String(value ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

function csvParseLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        result.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
  }
  result.push(current);
  return result;
}

export function buildAnnotationsCSV(annotations: Annotation[], relations: AnnotationRelation[]): string {
  const annHeader = 'uid,text,annotation_type,start_offset,end_offset,color,source,confidence';
  const annRows = annotations.map(a =>
    [
      csvEscape(a.uid),
      csvEscape(a.text),
      csvEscape(a.annotation_type),
      a.start_offset,
      a.end_offset,
      csvEscape(a.color),
      csvEscape(a.source ?? ''),
      a.confidence ?? '',
    ].join(',')
  );
  const relHeader = 'relation_uid,source_uid,target_uid,relation_type';
  const relRows = relations.map(r =>
    [
      csvEscape(r.relation_uid),
      csvEscape(r.source_uid),
      csvEscape(r.target_uid),
      csvEscape(r.relation_type),
    ].join(',')
  );
  return ['# ANNOTATIONS', annHeader, ...annRows, '# RELATIONS', relHeader, ...relRows].join('\n');
}

export function parseAnnotationsCSV(csvText: string): {
  annotations: Partial<Annotation>[];
  relations: Partial<AnnotationRelation>[];
} {
  const lines = csvText.split('\n').map(l => l.trimEnd());
  let section: 'none' | 'annotations' | 'relations' = 'none';
  let annHeaders: string[] = [];
  let relHeaders: string[] = [];
  const annotations: Partial<Annotation>[] = [];
  const relations: Partial<AnnotationRelation>[] = [];

  for (const line of lines) {
    if (line === '# ANNOTATIONS') { section = 'annotations'; annHeaders = []; continue; }
    if (line === '# RELATIONS') { section = 'relations'; relHeaders = []; continue; }
    if (!line || line.startsWith('#')) continue;

    if (section === 'annotations') {
      if (annHeaders.length === 0) { annHeaders = csvParseLine(line); continue; }
      const vals = csvParseLine(line);
      const obj: Partial<Annotation> = {};
      annHeaders.forEach((h, i) => {
        const v = vals[i] ?? '';
        if (h === 'start_offset') obj.start_offset = parseInt(v, 10);
        else if (h === 'end_offset') obj.end_offset = parseInt(v, 10);
        else if (h === 'confidence') obj.confidence = v !== '' ? parseFloat(v) : undefined;
        else (obj as any)[h] = v;
      });
      if (obj.text !== undefined) annotations.push(obj);
    } else if (section === 'relations') {
      if (relHeaders.length === 0) { relHeaders = csvParseLine(line); continue; }
      const vals = csvParseLine(line);
      const obj: Partial<AnnotationRelation> = {};
      relHeaders.forEach((h, i) => { (obj as any)[h] = vals[i] ?? ''; });
      if (obj.source_uid && obj.target_uid) relations.push(obj);
    }
  }

  return { annotations, relations };
}

// ==================== SAVE FOR TESTS API ====================

export interface DataAvailabilityStatus {
  pdf_exists: boolean;
  markdown_exists: boolean;
  has_annotations: boolean;
  has_relations: boolean;
  has_chains: boolean;
  has_patterns: boolean;
  annotation_count: number;
  relation_count: number;
  is_ready: boolean;
  missing_items: string[];
}

export interface SaveForTestsRequest {
  validate?: boolean;
}

export interface SaveForTestsResponse {
  success: boolean;
  sample_id: string;
  exported_files: string[];
  validation_result?: any;
  dvc_command: string;
  message?: string;
}

// Проверить доступность данных документа для экспорта
export async function checkDataAvailability(docId: string): Promise<DataAvailabilityStatus> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/data-availability`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}

// Сохранить документ в тестовый датасет
export async function saveDocumentForTests(
  docId: string,
  request: SaveForTestsRequest
): Promise<SaveForTestsResponse> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/save-for-tests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}
