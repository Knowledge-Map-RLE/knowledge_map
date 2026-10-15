import { act, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import i18n from '../../../shared/i18n';
import * as api from '../../../services/api/article_maps';
import type { MapProvenance, SavedArticleMap } from '../../../services/api/article_maps';
import ArticleMapDetails from './ArticleMapDetails';

vi.mock('../../../services/api/article_maps', () => ({ getMapProvenance: vi.fn(), getTransitionProvenance: vi.fn() }));
const result = { article_id: 'article', pipeline_id: 'text_reified', run_id: 'historic',
    graph: { nodes: [{ id: 'B3', display_text: 'Conclusion' }] } } as SavedArticleMap;
const provenance = { run_id: 'historic', source_sha256: 'hash', offset_encoding: 'unicode_codepoints',
    fragments: [{ start: 1, end: 10, section_id: 'H1', text: 'Original source' }] };

beforeEach(async () => { vi.resetAllMocks(); await i18n.changeLanguage('ru'); });

test('joint inputs and source are loaded for the selected historical run', async () => {
    vi.mocked(api.getTransitionProvenance).mockResolvedValue({ ...provenance, transition: { id: 'T1',
        sources: ['B1', 'B2'], target: 'B3', usage: 'evidence', reason: 'These observations justify this conclusion',
        conditions: [], unit_ids: ['U2'] } });
    render(<ArticleMapDetails result={result} selection={{ transitionIds: ['T1'] }} onClose={() => {}} />);
    await screen.findByText('B1 + B2 → B3');
    expect(screen.getByText('Original source')).toBeInTheDocument();
    expect(api.getTransitionProvenance).toHaveBeenCalledWith('article', 'text_reified', 'T1', 'historic', expect.any(AbortSignal));
});

test('a delayed provenance response cannot replace another article', async () => {
    let resolveOld!: (value: MapProvenance) => void;
    vi.mocked(api.getMapProvenance).mockImplementation(doc => doc === 'article'
        ? new Promise(resolve => { resolveOld = resolve; })
        : Promise.resolve({ ...provenance, fragments: [{ ...provenance.fragments[0], text: 'Second source' }] }));
    const view = render(<ArticleMapDetails result={result} selection={{ nodeId: 'B3' }} onClose={() => {}} />);
    view.rerender(<ArticleMapDetails result={{ ...result, article_id: 'second' }} selection={{ nodeId: 'B3' }} onClose={() => {}} />);
    await screen.findByText('Second source');
    await act(async () => resolveOld(provenance));
    expect(screen.queryByText('Original source')).not.toBeInTheDocument();
});
