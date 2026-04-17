import type { Annotation, AnnotationRelation, CreateAnnotationRequest, UpdateAnnotationRequest, CreateRelationRequest, AnnotationsResponse, BatchUpdateOffsetsRequest, BatchUpdateOffsetsResponse } from '../entities/annotation';
import { fetchJson } from './http';

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
  return data.relation ?? data;
}

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

export async function getAnnotationRelations(docId: string): Promise<AnnotationRelation[]> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/relations`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  const data = await res.json();
  return Array.isArray(data) ? data : (data.relations ?? []);
}