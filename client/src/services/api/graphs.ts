import type { LinguisticGraphResponse, DependencyNgramResponse, PatternContextResponse, PatternData, PatternGraphData, ExtractPatternsResponse, PatternCreateStatus, SavePatternsResponse } from '../../entities/document';
import { fetchJson } from './http';

export async function getDocumentLinguisticGraph(docId: string): Promise<LinguisticGraphResponse> {
  return fetchJson(`/api/patterns/linguistic-graph/${encodeURIComponent(docId)}`);
}

export async function getGlobalLinguisticGraph(options?: {
  lexicalLimit?: number;
  actionLimit?: number;
  edgeLimit?: number;
  autoLayout?: boolean;
}): Promise<LinguisticGraphResponse> {
  const params = new URLSearchParams();
  if (options?.lexicalLimit) params.set('lexical_limit', String(options.lexicalLimit));
  if (options?.actionLimit) params.set('action_limit', String(options.actionLimit));
  if (options?.edgeLimit) params.set('edge_limit', String(options.edgeLimit));
  if (options?.autoLayout !== undefined) params.set('auto_layout', String(options.autoLayout));

  const query = params.toString();
  return fetchJson(`/api/patterns/global-linguistic-graph${query ? `?${query}` : ''}`);
}

export async function getDependencyNgrams(maxDepth = 5, limitPerN = 50): Promise<DependencyNgramResponse> {
  return fetchJson(`/api/data_extraction/nlp/dependency-ngrams?max_depth=${maxDepth}&limit_per_n=${limitPerN}`);
}

export async function getPatternContext(nodeIds: number[]): Promise<PatternContextResponse> {
  return fetchJson(`/api/data_extraction/nlp/pattern-context?node_ids=${encodeURIComponent(JSON.stringify(nodeIds))}`);
}

export async function getExtractedPatterns(options?: {
  maxNodes?: number;
  maxDepth?: number;
  limitPerN?: number;
  minFrequency?: number;
  mode?: 'all' | 'dependency' | 'action' | 'mixed';
}): Promise<ExtractPatternsResponse> {
  const params = new URLSearchParams();
  if (options?.maxNodes !== undefined) params.set('max_nodes', String(options.maxNodes));
  if (options?.maxDepth !== undefined) params.set('max_depth', String(options.maxDepth));
  if (options?.limitPerN !== undefined) params.set('limit_per_n', String(options.limitPerN));
  if (options?.minFrequency !== undefined) params.set('min_frequency', String(options.minFrequency));
  if (options?.mode) params.set('mode', options.mode);

  const query = params.toString();
  return fetchJson(`/api/data_extraction/patterns/extract${query ? `?${query}` : ''}`, { method: 'POST' });
}

export async function getExtractStatus(): Promise<ExtractPatternsResponse> {
  return fetchJson('/api/data_extraction/patterns/extract-status');
}

export async function getPatternGraph(patternUid: string): Promise<PatternGraphData> {
  return fetchJson(`/api/data_extraction/patterns/${encodeURIComponent(patternUid)}/graph`);
}

export async function getPatternText(patternUid: string): Promise<{
  success: boolean;
  pattern_uid: string;
  rendered_text: string;
  node_count: number;
  edge_count: number;
}> {
  return fetchJson(`/api/data_extraction/patterns/${encodeURIComponent(patternUid)}/text`);
}

export async function savePatternsToDb(patterns: PatternData[]): Promise<SavePatternsResponse> {
  return fetchJson('/api/data_extraction/patterns/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patterns),
  });
}

export async function createPatternsInDb(options?: {
  maxNodes?: number;
  maxDepth?: number;
  limitPerN?: number;
  minFrequency?: number;
  mode?: string;
}): Promise<{ success: boolean; message: string; status_url: string }> {
  const params = new URLSearchParams();
  if (options?.maxNodes !== undefined) params.set('max_nodes', String(options.maxNodes));
  if (options?.maxDepth !== undefined) params.set('max_depth', String(options.maxDepth));
  if (options?.limitPerN !== undefined) params.set('limit_per_n', String(options.limitPerN));
  if (options?.minFrequency !== undefined) params.set('min_frequency', String(options.minFrequency));
  if (options?.mode) params.set('mode', options.mode);
  params.set('save_to_db', 'true');

  return fetchJson(`/api/data_extraction/patterns/create?${params.toString()}`, { method: 'POST' });
}

export async function getPatternCreateStatus(): Promise<PatternCreateStatus> {
  return fetchJson('/api/data_extraction/patterns/create-status');
}
