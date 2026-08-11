import type { Annotation, AnnotationRelation, CreateAnnotationRequest, UpdateAnnotationRequest, CreateRelationRequest, AnnotationsResponse, BatchUpdateOffsetsRequest, BatchUpdateOffsetsResponse } from '../../entities/annotation';
import { fetchJson } from './http';

export async function createAnnotation(docId: string, request: CreateAnnotationRequest): Promise<Annotation> {
  const data = await fetchJson<Annotation | { annotation: Annotation }>(`/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations`, {
    method: 'POST',
    body: JSON.stringify(request)
  });
  return 'annotation' in data ? data.annotation : data;
}

export async function getAnnotations(
  docId: string,
  skip: number = 0,
  limit: number | null = null,
  annotationTypes: string[] | null = null,
  source: string | null = null
): Promise<AnnotationsResponse> {
  const params = new URLSearchParams();
  params.append('skip', skip.toString());
  if (limit !== null) params.append('limit', limit.toString());
  if (annotationTypes && annotationTypes.length > 0) params.append('annotation_types', annotationTypes.join(','));
  if (source) params.append('source', source);
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations?${params}`);
}

export async function updateAnnotation(annotationId: string, request: UpdateAnnotationRequest): Promise<Annotation> {
  return fetchJson(`/api/data_extraction/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'PUT',
    body: JSON.stringify(request)
  });
}

export async function deleteAnnotation(annotationId: string): Promise<{ message: string }> {
  return fetchJson(`/api/data_extraction/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'DELETE'
  });
}

export async function deleteAllAnnotations(docId: string): Promise<{ success: boolean; message: string; deleted_count: number }> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/annotations/all`, {
    method: 'DELETE'
  });
}

export async function batchUpdateAnnotationOffsets(request: BatchUpdateOffsetsRequest): Promise<BatchUpdateOffsetsResponse> {
  return fetchJson(`/api/data_extraction/annotations/batch-update-offsets`, {
    method: 'POST',
    body: JSON.stringify(request)
  });
}

export async function createAnnotationRelation(sourceId: string, request: CreateRelationRequest): Promise<AnnotationRelation> {
  const data = await fetchJson<AnnotationRelation | { relation: AnnotationRelation }>(`/api/data_extraction/annotations/${encodeURIComponent(sourceId)}/relations`, {
    method: 'POST',
    body: JSON.stringify(request)
  });
  return 'relation' in data ? data.relation : data;
}

export async function deleteAnnotationRelation(sourceId: string, targetId: string): Promise<{ message: string }> {
  return fetchJson(`/api/data_extraction/annotations/${encodeURIComponent(sourceId)}/relations/${encodeURIComponent(targetId)}`, {
    method: 'DELETE'
  });
}

export async function getAnnotationRelations(docId: string): Promise<AnnotationRelation[]> {
  const data = await fetchJson<AnnotationRelation[] | { relations: AnnotationRelation[] }>(
    `/api/data_extraction/documents/${encodeURIComponent(docId)}/relations`
  );
  return Array.isArray(data) ? data : data.relations;
}
