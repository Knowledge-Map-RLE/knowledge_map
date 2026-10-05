import { describe, expect, test, vi } from 'vitest';
import i18n from '../../../shared/i18n';
import type { SavedArticleMap } from '../../../services/api/article_maps';
import { adaptSavedArticleMap } from './articleMapAdapter';

// Эти проверки относятся к контракту и слоям, а не к Canvas-метрикам шрифта.
vi.mock('./ArticleBlock', () => ({ ARTICLE_BLOCK_WIDTH: 240, getArticleBlockHeight: () => 80 }));

function knowledgeMap(): SavedArticleMap {
    return { article_id: 'article', pipeline_id: 'text_reified', run_id: 'v2', updated_at: '2026-10-04T00:00:00Z',
        input_fingerprint: 'hash', builder_version: '2', graph_schema_version: 5,
        graph: { schema_version: 5,
            concepts: [{ id: 'C1', display_text: 'Hidden method name', aliases: [] }],
            nodes: ['Method', 'Operation', 'Result', 'Conclusion'].map((label, rank) => ({
                id: `N${rank}`, display_text: label, kind: label.toLowerCase(), block_type: label.toLowerCase(), rank, order: rank,
            })), edges: [{ source: 'N0', target: 'N1' }, { source: 'N1', target: 'N2' }, { source: 'N2', target: 'N3' }],
            analysis: { depth: 4, layer_counts: { '0': 1, '1': 1, '2': 1, '3': 1 },
                knowledge_input_count: 3, concept_count: 1, operation_count: 1 } } };
}

describe('Knowledge-first map projection', () => {
    test('four server-computed ranks form four columns and hide the concept dictionary', async () => {
        await i18n.changeLanguage('ru');
        const saved = knowledgeMap();
        const projected = adaptSavedArticleMap(saved, i18n.t.bind(i18n));
        expect(projected.nodes).toHaveLength(4);
        expect(projected.nodes.map(n => n.layer)).toEqual([0, 1, 2, 3]);
        expect(projected.nodes[3].x - projected.nodes[0].x).toBe(900);
        expect(projected.nodes.some(n => n.id === 'C1')).toBe(false);
        expect(projected.nodes[1].typeLabel).toBe('Применение метода');
        expect(projected.studyVerdict).toContain('4');
        expect(projected.links).toHaveLength(3);
    });

    test('English UI translates kinds while preserving canonical English knowledge', async () => {
        await i18n.changeLanguage('en');
        const projected = adaptSavedArticleMap(knowledgeMap(), i18n.t.bind(i18n));
        expect(projected.nodes[1].typeLabel).toBe('Method application');
        expect(projected.nodes[2].label).toBe('Result');
    });

    test('translated labels keep the same ids, links, ranks, and dictionary', () => {
        const saved = knowledgeMap();
        const dictionary = structuredClone(saved.graph.concepts);
        saved.graph.nodes[0].display_text = 'Метод усреднения';
        const projected = adaptSavedArticleMap(saved, i18n.t.bind(i18n));
        expect(projected.nodes[0].id).toBe('N0');
        expect(projected.nodes[0].label).toBe('Метод усреднения');
        expect(projected.links[0]).toMatchObject({ source_id: 'N0', target_id: 'N1' });
        expect(saved.graph.concepts).toEqual(dictionary);
    });

    test('saved schema four maps remain readable without reconstruction', () => {
        const saved = knowledgeMap();
        saved.graph.schema_version = 4;
        expect(adaptSavedArticleMap(saved, i18n.t.bind(i18n)).nodes).toHaveLength(4);
    });

    test('unknown schema is explicitly rejected', () => {
        const saved = knowledgeMap();
        saved.graph.schema_version = 99;
        expect(() => adaptSavedArticleMap(saved, i18n.t.bind(i18n))).toThrow('99');
    });
});
