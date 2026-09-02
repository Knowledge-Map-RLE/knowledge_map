import type { AnalyzePatternsResponse, DataAvailabilityStatus, SaveForTestsRequest, SaveForTestsResponse } from '../../entities/document';
import { fetchJson } from './http';

export async function checkDataAvailability(docId: string): Promise<DataAvailabilityStatus> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/data-availability`);
}

export async function saveDocumentForTests(docId: string, request: SaveForTestsRequest): Promise<SaveForTestsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/save-for-tests`, {
    method: 'POST',
    body: JSON.stringify(request)
  });
}

export async function analyzeDocumentPatterns(
  docId: string,
  annotationTypes?: string[],
  minFrequency: number = 1,
): Promise<AnalyzePatternsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/analyze-patterns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotation_types: annotationTypes, clear_existing: true, min_frequency: minFrequency }),
  });
}

export async function getDocumentPatterns(docId: string): Promise<AnalyzePatternsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/patterns`);
}

export async function getDocumentSpecificPatterns(docId: string): Promise<AnalyzePatternsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/patterns/specific`);
}

export async function backfillNormKeys(): Promise<{ updated: number }> {
  return fetchJson('/api/data_extraction/shared-actions/backfill', { method: 'POST' });
}
