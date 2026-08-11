import type {
    Document,
    DocumentAssets,
    DocumentProgress,
    PubMedIngestResponse,
    PubMedSearchResponse,
} from '../../entities/document';
import { fetchJson, withBase } from './http';

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
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error'));
      });

      xhr.open('POST', withBase('/api/data_extraction/data_extraction'));
      xhr.send(form);
    });
  } else {
    const res = await fetch(withBase('/api/data_extraction/data_extraction'), { method: 'POST', body: form });
    return (await res.json()) as ExtractionUploadResponse;
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

export async function saveMarkdown(docId: string, markdown: string, annotate = false): Promise<SaveMarkdownResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/markdown`, {
    method: 'PUT',
    body: JSON.stringify({ markdown, annotate })
  });
}

export async function deleteDocument(docId: string): Promise<DeleteDocumentResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
}

export async function listDocuments(skip: number = 0, limit: number = 200, signal?: AbortSignal): Promise<DocumentsListResponse> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  return fetchJson(`/api/data_extraction/documents?${params}`, { signal });
}

export async function searchDocuments(q: string, skip: number = 0, limit: number = 100, signal?: AbortSignal): Promise<DocumentsListResponse> {
  const params = new URLSearchParams({ q, skip: String(skip), limit: String(limit) });
  return fetchJson(`/api/data_extraction/documents/search?${params}`, { signal });
}

export async function searchPubMed(query: string, limit: number = 10): Promise<PubMedSearchResponse> {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return fetchJson(`/api/data_extraction/pubmed/search?${params}`);
}

export async function getByPubMedId(id: string): Promise<PubMedSearchResponse> {
  const params = new URLSearchParams({ id });
  return fetchJson(`/api/data_extraction/pubmed/by-id?${params}`);
}

export async function ingestPubMedArticle(pmid?: string, pmcid?: string, source: string = 'pubmed'): Promise<PubMedIngestResponse> {
  return fetchJson(`/api/data_extraction/pubmed/ingest`, {
    method: 'POST',
    body: JSON.stringify({ pmid, pmcid, source }),
  });
}
