import type { TFunction } from 'i18next';
import type { SavedArticleMap } from '../../../services/api/article_maps';
import { ARTICLE_BLOCK_WIDTH, getArticleBlockHeight } from './ArticleBlock';
import type { ArticleMapGraph, ArticleMapNode } from './articleMapGraph';

/** Адаптеры сохранённых контрактов к общей модели существующего отображения. */
function project(result: SavedArticleMap, verdict: string, kindLabel?: (kind: string) => string): ArticleMapGraph {
    const nextY = new Map<number, number>();
    const ordered = [...result.graph.nodes].sort((a, b) =>
        a.rank - b.rank || a.order - b.order || a.id.localeCompare(b.id));
    const nodes: ArticleMapNode[] = ordered.map(node => {
        // Читаемый текст берётся только из подписи, скрытая семантика сюда не попадает.
        const label = node.display_text.trim();
        const height = getArticleBlockHeight(label, node.is_goal === true);
        const top = nextY.get(node.rank) ?? 60;
        nextY.set(node.rank, top + height + 24);
        return {
            id: node.id, title: label, text: label, label,
            x: node.rank * 300 + 60 + ARTICLE_BLOCK_WIDTH / 2, y: top + height / 2,
            level: 0, layer: node.rank, blockType: node.block_type, order: node.order,
            outcome: 'neutral', outcomeLabel: '', data: {}, isGoal: node.is_goal === true,
            height, typeLabel: kindLabel?.(node.block_type),
        };
    });
    return { nodes, links: result.graph.edges.map(edge => ({
        id: `${edge.source}::${edge.target}`, source_id: edge.source, target_id: edge.target,
    })), studyVerdict: verdict };
}

export function adaptReifiedArticleMap(result: SavedArticleMap, t: TFunction): ArticleMapGraph {
    return project(result, t('articleEditor.map.reified'), kind => t(`articleEditor.map.kinds.${kind}`));
}

export function adaptKnowledgeArticleMap(result: SavedArticleMap, t: TFunction): ArticleMapGraph {
    // На схеме 5 показываем только самостоятельные знания; словарь и роли скрыты.
    return project(result, t('articleEditor.map.knowledge', { depth: result.graph.analysis?.depth }),
        kind => t(`articleEditor.map.kinds.${kind}`));
}

export function adaptStructuralArticleMap(result: SavedArticleMap, t: TFunction): ArticleMapGraph {
    return project(result, t('articleEditor.map.deterministic', { version: result.graph.schema_version }));
}

export function adaptSavedArticleMap(result: SavedArticleMap, t: TFunction): ArticleMapGraph {
    if (result.pipeline_id === 'structural_rows') return adaptStructuralArticleMap(result, t);
    if (result.graph.schema_version === 4) return adaptReifiedArticleMap(result, t);
    if (result.graph.schema_version === 5) return adaptKnowledgeArticleMap(result, t);
    throw new Error(t('articleEditor.map.unsupportedSchema', { version: result.graph.schema_version }));
}
