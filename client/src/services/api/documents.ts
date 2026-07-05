import { fetchJson } from './http';

export async function uploadPdfForExtraction(file: File, onProgress?: (progress: number) => void): Promise<any> {
  const form = new FormData();
  form.append('file', file);
  
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  
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

export async function getDocumentAssets(docId: string): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/assets?include_urls=true`);
  return res.json();
}

export async function getDocumentProgress(docId: string): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/progress`);
  return res.json();
}

export async function saveMarkdown(docId: string, markdown: string, annotate = false): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/markdown`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown, annotate })
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail || await res.text().catch(() => '');
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export async function deleteDocument(docId: string): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
  return res.json();
}

export async function listDocuments(skip: number = 0, limit: number = 200, signal?: AbortSignal): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  const res = await fetch(`${base}/api/data_extraction/documents?${params}`, { signal });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function searchDocuments(q: string, skip: number = 0, limit: number = 100, signal?: AbortSignal): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ q, skip: String(skip), limit: String(limit) });
  const res = await fetch(`${base}/api/data_extraction/documents/search?${params}`, { signal });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function searchPubMed(query: string, limit: number = 10): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ query, limit: String(limit) });
  const res = await fetch(`${base}/api/data_extraction/pubmed/search?${params}`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function getByPubMedId(id: string): Promise<any> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const params = new URLSearchParams({ id });
  const res = await fetch(`${base}/api/data_extraction/pubmed/by-id?${params}`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function ingestPubMedArticle(pmid?: string, pmcid?: string, source: string = 'pubmed'): Promise<any> {
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