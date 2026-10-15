import { expect, test, vi } from 'vitest';
import { initialMapFocus, mapOverview } from './articleMapViewport';
import type { ArticleMapNode } from './articleMapGraph';

vi.mock('./ArticleBlock', () => ({ ARTICLE_BLOCK_WIDTH: 200 }));
const node = (id: string, layer: number, y: number, height = 100) => ({ id, layer, x: layer * 300 + 100,
    y, height, order: layer } as ArticleMapNode);

test('focus stays on a connected knowledge block despite distant isolated nodes', () => {
    const chain = [node('A', 0, 100), node('B', 1, 150), node('C', 2, 100)];
    const focus = initialMapFocus({ nodes: [...chain, node('isolated', 0, 9000)],
        links: [{ id: 'AB', source_id: 'A', target_id: 'B' }, { id: 'BC', source_id: 'B', target_id: 'C' }], studyVerdict: '' });
    expect(focus).toBe(chain[1]);
});

test('overview contains every complete card within the screen', () => {
    const nodes = [node('A', 0, 100, 120), node('B', 12, 7000, 1400)];
    const screen = { width: 800, height: 600 };
    const view = mapOverview(nodes, screen)!;
    for (const item of nodes) {
        expect((item.x - 100 - view.x) * view.scale + screen.width / 2).toBeGreaterThan(0);
        expect((item.x + 100 - view.x) * view.scale + screen.width / 2).toBeLessThan(screen.width);
        expect((item.y - item.height! / 2 - view.y) * view.scale + screen.height / 2).toBeGreaterThan(0);
        expect((item.y + item.height! / 2 - view.y) * view.scale + screen.height / 2).toBeLessThan(screen.height);
    }
});

test('empty map or uninitialized screen has no camera target', () => {
    expect(initialMapFocus({ nodes: [], links: [], studyVerdict: '' })).toBeUndefined();
    expect(mapOverview([], { width: 800, height: 600 })).toBeNull();
    expect(mapOverview([node('A', 0, 100)], { width: 0, height: 600 })).toBeNull();
});
