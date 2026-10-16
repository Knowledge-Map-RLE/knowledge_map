import type {
    Document,
    DocumentAssets,
    DocumentProgress,
    PubMedIngestResponse,
    PubMedSearchResponse,
} from '../../entities/document';
import { authHeaders, fetchJson, withBase } from './http';
import { invalidateToken } from '../token';

export interface ExtractionUploadResponse {
    success: boolean;
    doc_id?: string;
    message?: string;
    files?: Record<string, string>;
}

export interface SaveMarkdownResponse {
    success?: boolean;
    message?: string;
    validation?: { is_valid: boolean };
}

export interface DocumentsListResponse {
    success: boolean;
    documents: Document[];
    total_count: number;
}

export interface DocumentStatsResponse {
    success: boolean;
    full_text_count: number;
}

export interface DeleteDocumentResponse {
    success: boolean;
    message: string;
}

export async function uploadPdfForExtraction(file: File, onProgress?: (progress: number) => void): Promise<ExtractionUploadResponse> {
  const form = new FormData();
  form.append('file', file);

  if (onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const headers = new Headers(authHeaders());

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const percentComplete = Math.round((event.loaded / event.total) * 100);
          onProgress(percentComplete);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText) as ExtractionUploadResponse;
            resolve(response);
          } catch {
            reject(new Error('Failed to parse response'));
          }
        } else {
          if (xhr.status === 401) {
            const authorization = headers.get('Authorization');
            if (authorization?.startsWith('Bearer ')) {
              invalidateToken(authorization.slice('Bearer '.length));
            }
          }
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error'));
      });

      xhr.open('POST', withBase('/api/data_extraction/data_extraction'));
      headers.forEach((value, name) => xhr.setRequestHeader(name, value));
      xhr.send(form);
    });
  } else {
    return fetchJson<ExtractionUploadResponse>(
      '/api/data_extraction/data_extraction',
      { method: 'POST', body: form },
    );
  }
}

export async function importAnnotations(docId: string, annotations: unknown): Promise<{ success: boolean; key?: string }> {
  return fetchJson(`/api/data_extraction/annotations/import`, {
    method: 'POST',
    body: JSON.stringify({ doc_id: docId, annotations_json: annotations })
  });
}

export async function exportAnnotations(docId: string): Promise<string> {
  const res = await fetch(withBase(`/api/data_extraction/annotations/export?doc_id=${encodeURIComponent(docId)}`));
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

export async function getDocumentAssets(docId: string): Promise<DocumentAssets> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/assets?include_urls=true`);
}

export async function getDocumentProgress(docId: string): Promise<DocumentProgress> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/progress`);
}

export async function reprocessDocument(docId: string): Promise<ExtractionUploadResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/reprocess`, {
    method: 'POST',
  });
}

export async function saveMarkdown(docId: string, markdown: string, annotate = false): Promise<SaveMarkdownResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/markdown`, {
    method: 'PUT',
    body: JSON.stringify({ markdown, annotate })
  });
}

export async function deleteDocument(docId: string): Promise<DeleteDocumentResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
}

export async function listDocuments(skip: number = 0, limit: number = 200, signal?: AbortSignal, fullTextOnly: boolean = false, goldOnly: boolean = false): Promise<DocumentsListResponse> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  if (fullTextOnly) params.set('full_text_only', 'true');
  if (goldOnly) params.set('gold_only', 'true');
  return fetchJson(`/api/data_extraction/documents?${params}`, { signal });
}

export async function getDocumentStats(): Promise<DocumentStatsResponse> {
  return fetchJson(`/api/data_extraction/documents/stats`);
}

export async function searchDocuments(q: string, skip: number = 0, limit: number = 100, signal?: AbortSignal, fullTextOnly: boolean = false): Promise<DocumentsListResponse> {
  const params = new URLSearchParams({ q, skip: String(skip), limit: String(limit) });
  if (fullTextOnly) params.set('full_text_only', 'true');
  return fetchJson(`/api/data_extraction/documents/search?${params}`, { signal });
}

export async function searchPubMed(query: string, limit: number = 10, signal?: AbortSignal): Promise<PubMedSearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return fetchJson(`/api/data_extraction/pubmed/search?${params}`, { signal });
}

export async function getByPubMedId(id: string, signal?: AbortSignal): Promise<PubMedSearchResponse> {
  const params = new URLSearchParams({ id });
  return fetchJson(`/api/data_extraction/pubmed/by-id?${params}`, { signal });
}

export async function ingestPubMedArticle(pmid?: string, pmcid?: string, source: string = 'pubmed'): Promise<PubMedIngestResponse> {
  return fetchJson(`/api/data_extraction/pubmed/ingest`, {
    method: 'POST',
    body: JSON.stringify({ pmid, pmcid, source }),
  });
}
