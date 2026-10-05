import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import i18n from '../../../shared/i18n';
import ArticleMapCanvas from './ArticleMapCanvas';
import type { SavedArticleMap } from '../../../services/api/article_maps';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';

const { focus } = vi.hoisted(() => ({ focus: vi.fn() }));
vi.mock('pixi.js', () => ({ Container: class {}, Graphics: class {}, Text: class {} }));
vi.mock('@pixi/react', async () => {
    const R = await import('react');
    return { extend: vi.fn(), Application: ({ children }: React.PropsWithChildren) => {
        const [ready, setReady] = R.useState(false);
        R.useEffect(() => { const timer = setTimeout(() => setReady(true), 500); return () => clearTimeout(timer); }, []);
        return ready ? <div>{children}</div> : null;
    } };
});
vi.mock('../../../widgets/KnowledgeMap', async () => {
    const R = await import('react');
    return { Link: () => null, Viewport: R.forwardRef<ViewportRef, React.PropsWithChildren>(({ children }, ref) => {
        R.useImperativeHandle(ref, () => ({ focusOn: focus, containerRef: {},
            getScreenSize: () => ({ width: 800, height: 600 }) }) as unknown as ViewportRef);
        return <div>{children}</div>;
    }) };
});
vi.mock('./ArticleBlock', () => ({ ARTICLE_BLOCK_WIDTH: 200, getArticleBlockHeight: () => 100,
    ArticleBlock: ({ blockData }: { blockData: { label: string } }) => <div>{blockData.label}</div> }));

afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

test('centers after slow viewport initialization and preserves readable block text', async () => {
    await i18n.changeLanguage('ru');
    vi.useFakeTimers();
    const result: SavedArticleMap = { article_id: 'article', pipeline_id: 'text_reified', run_id: 'run',
        updated_at: '2026-10-03T20:00:00Z', input_fingerprint: 'hash', builder_version: '1', graph_schema_version: 4,
        graph: { schema_version: 4, nodes: [{ id: 'N1', display_text: 'Readable English knowledge',
            block_type: 'concept', rank: 0, order: 0 }], edges: [] } };
    render(<ArticleMapCanvas result={result} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(200); });
    expect(focus).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    expect(focus).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Readable English knowledge')).toBeInTheDocument();
});
