import type { AnalyzePatternsResponse, PendingEdgesResponse, ReviewEdgeRequest, ExtractActionsResponse, ConfirmedActionGraphResponse, AutoReviewResponse, DataAvailabilityStatus, SaveForTestsRequest, SaveForTestsResponse } from '../entities/annotation';
import { fetchJson } from './http';

export async function checkDataAvailability(docId: string): Promise<DataAvailabilityStatus> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${encodeURIComponent(docId)}/data-availability`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.json();
}

export async function saveDocumentForTests(docId: string, request: SaveForTestsRequest): Promise<SaveForTestsResponse> {
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

export async function analyzeDocumentGoals(
  docId: string,
  minFrequency: number = 1,
): Promise<AnalyzePatternsResponse> {
  const GOAL_TYPES = [
    'Успешная цель',
    'Не успешная цель',
    'Фрагмент ведёт к успеху',
    'Фрагмент ведёт к неуспеху',
  ];
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/analyze-goals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ annotation_types: GOAL_TYPES, clear_existing: true, min_frequency: minFrequency }),
  });
}

export async function getDocumentGoals(docId: string): Promise<AnalyzePatternsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/goals`);
}

export async function extractDocumentActions(docId: string): Promise<ExtractActionsResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/extract-actions`, {
    method: 'POST',
  });
}

export async function getPendingEdges(docId: string): Promise<PendingEdgesResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/actions/pending`);
}

export async function reviewEdge(docId: string, req: ReviewEdgeRequest): Promise<{ success: boolean }> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/actions/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
}

export async function autoReview(docId: string, dryRun: boolean = false): Promise<AutoReviewResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/actions/auto-review?dry_run=${dryRun}`, {
    method: 'POST',
  });
}

export async function getConfirmedActionGraph(docId: string): Promise<ConfirmedActionGraphResponse> {
  return fetchJson(`/api/data_extraction/documents/${encodeURIComponent(docId)}/actions/graph`);
}

export async function backfillNormKeys(): Promise<{ updated: number }> {
  return fetchJson('/api/data_extraction/shared-actions/backfill', { method: 'POST' });
}
