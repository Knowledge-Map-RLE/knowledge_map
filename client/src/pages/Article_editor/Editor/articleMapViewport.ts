import type { ArticleMapGraph, ArticleMapNode } from './articleMapGraph';
import { ARTICLE_BLOCK_WIDTH } from './ArticleBlock';

/** Начальный центр совпадает с блоком цепочки, а не с пустым центром габаритов. */
export function initialMapFocus(graph: ArticleMapGraph): ArticleMapNode | undefined {
    const degree = new Map<string, number>();
    for (const link of graph.links) {
        degree.set(link.source_id, (degree.get(link.source_id) ?? 0) + 1);
        degree.set(link.target_id, (degree.get(link.target_id) ?? 0) + 1);
    }
    const connected = graph.nodes.filter(node => degree.has(node.id));
    const candidates = connected.length ? connected : graph.nodes;
    if (!candidates.length) return undefined;
    const middle = (Math.min(...candidates.map(node => node.layer)) + Math.max(...candidates.map(node => node.layer))) / 2;
    return [...candidates].sort((a, b) => Math.abs(a.layer - middle) - Math.abs(b.layer - middle)
        || (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.order - b.order)[0];
}

/** Габариты учитывают размеры карточек, включая длинные научные подписи. */
export function mapOverview(nodes: ArticleMapNode[], screen: { width: number; height: number }) {
    if (!nodes.length || screen.width <= 0 || screen.height <= 0) return null;
    const left = Math.min(...nodes.map(node => node.x - ARTICLE_BLOCK_WIDTH / 2));
    const right = Math.max(...nodes.map(node => node.x + ARTICLE_BLOCK_WIDTH / 2));
    const top = Math.min(...nodes.map(node => node.y - (node.height ?? 100) / 2));
    const bottom = Math.max(...nodes.map(node => node.y + (node.height ?? 100) / 2));
    return { x: (left + right) / 2, y: (top + bottom) / 2,
        scale: Math.min(1, screen.width / (right - left + 128), screen.height / (bottom - top + 128)) };
}
