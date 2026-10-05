import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import i18n from '../../../shared/i18n';
import ArticleMap from './ArticleMap';
import * as api from '../../../services/api/article_maps';
import type { SavedArticleMap } from '../../../services/api/article_maps';

vi.mock('./ArticleMapCanvas', () => ({ default: ({ result }: { result: SavedArticleMap }) =>
    <div data-testid="map-canvas">{result.graph.nodes[0]?.display_text}</div> }));
vi.mock('../../../services/api/article_maps', () => ({
    listArticleMaps: vi.fn(), getArticleMap: vi.fn(), buildTextArticleMap: vi.fn(),
    buildStructuralArticleMap: vi.fn(), translateArticleMap: vi.fn(),
}));

function result(pipeline: 'text_reified' | 'structural_rows', text: string, article = 'article'): SavedArticleMap {
    return { article_id: article, pipeline_id: pipeline, run_id: pipeline, updated_at: '2026-10-03T10:00:00Z',
        input_fingerprint: 'hash', builder_version: '1', graph_schema_version: pipeline === 'text_reified' ? 4 : 3,
        graph: { schema_version: pipeline === 'text_reified' ? 4 : 3,
            nodes: [{ id: 'N1', rank: 0, order: 0, block_type: 'concept', display_text: text }], edges: [] } };
}
const oldMap = result('structural_rows', 'Structural map');
const newMap = result('text_reified', 'English knowledge');
newMap.builder_version = '2'; newMap.graph_schema_version = 5; newMap.graph.schema_version = 5;
newMap.graph.nodes[0].block_type = 'assertion';
newMap.graph.concepts = [];
newMap.graph.analysis = { depth: 1, layer_counts: { '0': 1 }, knowledge_input_count: 0, concept_count: 0, operation_count: 0 };

beforeEach(async () => {
    vi.resetAllMocks(); sessionStorage.clear();
    await i18n.changeLanguage('ru');
    vi.mocked(api.listArticleMaps).mockResolvedValue({ maps: [oldMap, newMap], availability: { text_reified: true, structural_rows: true } });
    vi.mocked(api.getArticleMap).mockImplementation(async (_doc, pipeline) => pipeline === 'text_reified' ? newMap : oldMap);
});

describe('Independent article maps', () => {
    test('both buttons and two saved pipeline choices remain visible', async () => {
        render(<ArticleMap docId="article" enabled />);
        expect(screen.getByRole('button', { name: 'Текст → карта знаний' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Структурные строки → карта знаний' })).toBeInTheDocument();
        await screen.findByText('Structural map');
        fireEvent.change(screen.getByLabelText('Версия карты'), { target: { value: 'text_reified' } });
        await screen.findByText('English knowledge');
        expect(api.getArticleMap).toHaveBeenLastCalledWith('article', 'text_reified', 'en', expect.any(AbortSignal));
        expect(sessionStorage.getItem('article-map.selection.article')).toBe('text_reified');
    });

    test('failed new conversion preserves the displayed successful old map', async () => {
        vi.mocked(api.buildTextArticleMap).mockRejectedValue(new Error('Model failed'));
        render(<ArticleMap docId="article" enabled />);
        await screen.findByText('Structural map');
        fireEvent.click(screen.getByRole('button', { name: 'Текст → карта знаний' }));
        await screen.findByRole('alert');
        expect(screen.getByText('Structural map')).toBeInTheDocument();
        expect(api.buildStructuralArticleMap).not.toHaveBeenCalled();
    });

    test('successful build selects only its pipeline and retains both options', async () => {
        vi.mocked(api.buildTextArticleMap).mockResolvedValue(newMap);
        render(<ArticleMap docId="article" enabled />);
        await screen.findByText('Structural map');
        fireEvent.click(screen.getByRole('button', { name: 'Текст → карта знаний' }));
        await screen.findByText('English knowledge');
        expect(screen.getByLabelText('Версия карты')).toHaveValue('text_reified');
        expect(screen.getByLabelText('Версия карты').querySelectorAll('option')).toHaveLength(2);
        expect(screen.getByRole('option', { name: /самостоятельные знания/ })).toBeInTheDocument();
    });

    test('dependency review has its own visible progress stage', async () => {
        let complete!: (value: SavedArticleMap) => void;
        vi.mocked(api.buildTextArticleMap).mockImplementation(async (_doc, _signal, progress) => {
            progress('dependencies');
            return new Promise(resolve => { complete = resolve; });
        });
        render(<ArticleMap docId="article" enabled />);
        await screen.findByText('Structural map');
        fireEvent.click(screen.getByRole('button', { name: 'Текст → карта знаний' }));
        await screen.findByText('LLM проверяет зависимости между знаниями по полному источнику…');
        await act(async () => complete(newMap));
        await screen.findByText('English knowledge');
    });

    test('empty article keeps disabled controls and explains missing inputs', async () => {
        vi.mocked(api.listArticleMaps).mockResolvedValue({ maps: [], availability: { text_reified: false, structural_rows: false } });
        render(<ArticleMap docId="article" enabled />);
        await screen.findByText('Для преобразования текста нужен сохранённый полный текст статьи.');
        expect(screen.getByRole('button', { name: 'Текст → карта знаний' })).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Структурные строки → карта знаний' })).toBeDisabled();
    });

    test('inventory refresh failure retains and selects the successfully built map', async () => {
        vi.mocked(api.buildTextArticleMap).mockResolvedValue(newMap);
        vi.mocked(api.listArticleMaps).mockResolvedValueOnce({ maps: [oldMap], availability: { text_reified: true, structural_rows: true } })
            .mockRejectedValue(new Error('Inventory unavailable'));
        render(<ArticleMap docId="article" enabled />);
        await screen.findByText('Structural map');
        fireEvent.click(screen.getByRole('button', { name: 'Текст → карта знаний' }));
        await screen.findByText('English knowledge');
        expect(screen.getByLabelText('Версия карты')).toHaveValue('text_reified');
        expect(screen.getByLabelText('Версия карты').querySelectorAll('option')).toHaveLength(2);
        expect(screen.getByRole('alert')).toHaveTextContent('Inventory unavailable');
    });

    test('switching articles ignores delayed responses from the previous article', async () => {
        let resolveOld!: (value: SavedArticleMap) => void;
        vi.mocked(api.getArticleMap).mockImplementation((doc) => doc === 'article'
            ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve(result('structural_rows', 'Second article', 'second')));
        const view = render(<ArticleMap docId="article" enabled />);
        await waitFor(() => expect(api.getArticleMap).toHaveBeenCalled());
        view.rerender(<ArticleMap docId="second" enabled />);
        await screen.findByText('Second article');
        await act(async () => resolveOld(oldMap));
        expect(screen.queryByText('Structural map')).not.toBeInTheDocument();
    });

    test('English UI exposes localized controls', async () => {
        await i18n.changeLanguage('en');
        render(<ArticleMap docId="article" enabled />);
        expect(screen.getByRole('button', { name: 'Text → knowledge map' })).toBeInTheDocument();
        await screen.findByText('Structural map');
    });
});
