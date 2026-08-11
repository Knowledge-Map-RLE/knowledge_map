import type { NLPAnalyzeRequest, NLPAnalyzeResponse, AutoAnnotateResponse, MultiLevelAnalysisResponse } from '../../entities/document';
import { fetchJson, withBase } from './http';

export async function analyzeText(request: NLPAnalyzeRequest): Promise<NLPAnalyzeResponse> {
  return fetchJson('/api/data_extraction/nlp/analyze', {
    method: 'POST',
    body: JSON.stringify(request)
  });
}

export async function autoAnnotateDocument(
  docId: string,
  processors: string[] = ['spacy'],
  annotationTypes: string[] | null = null,
  minConfidence: number = 0.7
): Promise<AutoAnnotateResponse> {
  return fetchJson(`/api/data_extraction/documents/${docId}/auto-annotate`, {
    method: 'POST',
    body: JSON.stringify({
      processors,
      annotation_types: annotationTypes,
      min_confidence: minConfidence
    })
  });
}

export async function autoAnnotateMultilevel(
  docId: string,
  enableVoting: boolean = true,
  maxLevel: number = 3,
  createAnnotations: boolean = true,
  minConfidence: number = 0.8
): Promise<MultiLevelAnalysisResponse> {
  return fetchJson(`/api/data_extraction/documents/${docId}/analyze-multilevel`, {
    method: 'POST',
    body: JSON.stringify({
      enable_voting: enableVoting,
      max_level: maxLevel,
      create_annotations: createAnnotations,
      min_confidence: minConfidence
    })
  });
}

export async function getNlpTaskStatus(docId: string): Promise<{ status: string; error?: string | null }> {
  return fetchJson(`/api/data_extraction/documents/${docId}/nlp-status`);
}

export async function exportAnnotationsYAML(docId: string): Promise<Blob> {
  const res = await fetch(withBase(`/api/data_extraction/annotations/export-yaml?doc_id=${encodeURIComponent(docId)}`));
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }
  return res.blob();
}

export async function importAnnotationsYAML(docId: string, file: File): Promise<{ success: boolean; message?: string }> {
  const formData = new FormData();
  formData.append('file', file);
  return fetchJson(`/api/data_extraction/annotations/import-yaml?doc_id=${encodeURIComponent(docId)}`, {
    method: 'POST',
    body: formData
  });
}
