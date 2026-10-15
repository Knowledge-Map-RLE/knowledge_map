import { fetchJson } from './http';
import type { SavedArticleMap } from './article_maps';

export type ComparisonMode = 'text' | 'semantic' | 'hybrid';
export interface MapReference { article_id: string; pipeline_id: 'text_reified'; run_id: string }
export interface ComparisonRun extends MapReference { title: string; updated_at: string; schema_version: number }
export interface ComparisonMap extends SavedArticleMap {
    source: { sha256: string; units: Array<{ id: string; text: string; start: number; end: number }> };
    translations?: { ru?: { knowledge_labels: Record<string, string> } };
    source_attachments?: Array<{ unit_id: string; text: string }>;
}
export interface ComparisonPair {
    pair_id: string; left_knowledge_id: string; right_knowledge_id: string; right_article_id: string;
    text_score: number; semantic_score: number; hybrid_score: number; relations: string[];
    coverage_left: number; coverage_right: number; template_score: number; dag_shape_score: number;
    statement_matches: Array<{ left_statement: string; right_statement: string; relation: string;
        differences: Array<{ field: string; left: unknown; right: unknown }> }>;
}
export interface ComparisonSummary { comparison_id: string; created_at: string; references: MapReference[] }
export interface ArticleComparison extends ComparisonSummary {
    maps: ComparisonMap[];
    analysis: { pair_count: number; normalizer_version: string; comparator_version: string; rrf_constant: number };
    summary?: { equivalent_pairs: number; unique_target_knowledge_by_relation?: Record<string, string[]>;
        covered_target_statements: string[]; shared_attribute_targets?: string[]; auxiliary_description_count?: number };
    evaluation: { retrieval_at_k: Record<string, Record<string, { found: number; total: number }>>;
        observations: Array<{ id: string; kind: string; rationale_ru: string; ranks: Record<string, number | null>;
            retrieved_relations: string[]; detected_difference_fields: string[] }> };
}
const base = '/api/article_editor/comparisons';
export const listComparisons = (articleId: string, signal: AbortSignal) =>
    fetchJson<{ comparisons: ComparisonSummary[] }>(`${base}?article_id=${encodeURIComponent(articleId)}`, { signal });
export async function listComparisonRuns(signal: AbortSignal) {
    const runs: ComparisonRun[] = [];
    let offset: number | null = 0;
    while (offset !== null) {
        const page: { runs: ComparisonRun[]; next_offset: number | null } = await fetchJson(`${base}/runs?offset=${offset}`, { signal });
        runs.push(...page.runs); offset = page.next_offset;
    }
    return runs;
}
export const getComparison = (id: string, signal: AbortSignal) => fetchJson<ArticleComparison>(`${base}/${id}`, { signal });
export const createComparison = (target: MapReference, sources: MapReference[], signal: AbortSignal) =>
    fetchJson<ArticleComparison>(base, { method: 'POST', body: JSON.stringify({ target, sources }), signal });
export const getComparisonPairs = (id: string, query: Record<string, string>, signal: AbortSignal) =>
    fetchJson<{ pairs: ComparisonPair[]; total: number }>(`${base}/${id}/pairs?${new URLSearchParams(query)}`, { signal });

/** Меняются только отображаемые вхождения; английская семантика остаётся исходной. */
export function comparisonDisplayMap(map: ComparisonMap, locale: 'en' | 'ru'): ComparisonMap {
    const labels = locale === 'ru' ? map.translations?.ru?.knowledge_labels : undefined;
    return { ...map, locale, graph: { ...map.graph, nodes: map.graph.nodes.map(n => ({ ...n,
        display_text: (n.knowledge_id && labels?.[n.knowledge_id]) || n.display_text })) } };
}
