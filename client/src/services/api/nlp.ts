import type { NLPAnalyzeRequest, NLPAnalyzeResponse, AutoAnnotateResponse, MultiLevelAnalysisResponse, AutoReviewResponse } from '../entities/annotation';
import { fetchJson } from './http';

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

export async function getNlpTaskStatus(docId: string): Promise<{ status: string; error?: string | null }> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/documents/${docId}/nlp-status`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function exportAnnotationsYAML(docId: string): Promise<Blob> {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  const res = await fetch(`${base}/api/data_extraction/annotations/export-yaml?doc_id=${encodeURIComponent(docId)}`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.blob();
}

export async function importAnnotationsYAML(docId: string, file: File): Promise<any> {
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
