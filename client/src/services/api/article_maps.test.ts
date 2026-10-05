import { afterEach, describe, expect, test, vi } from 'vitest';
import { buildTextArticleMap } from './article_maps';

vi.mock('./http', () => ({ authHeaders: () => ({}), withBase: (path: string) => path }));
afterEach(() => vi.unstubAllGlobals());

function response(chunks: string[]) {
    let index = 0;
    return { ok: true, body: { getReader: () => ({
        read: async () => index < chunks.length ? { done: false, value: new TextEncoder().encode(chunks[index++]) } : { done: true },
        cancel: async () => undefined, releaseLock: () => undefined,
    }) } };
}
describe('Article map SSE integrity', () => {
    test('accepts frames split across chunks', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([
            'data: {"type":"progress","stage":"model"}\n\ndata: {"type":"res',
            'ult","data":{"pipeline_id":"text_reified"}}\n\ndata: [DONE]\n\n',
        ])));
        const progress = vi.fn();
        const result = await buildTextArticleMap('article', new AbortController().signal, progress);
        expect(result.pipeline_id).toBe('text_reified');
        expect(progress).toHaveBeenCalledWith('model');
    });
    test('rejects a stream missing its terminal frame', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"result","data":{}}\n\n'])));
        await expect(buildTextArticleMap('article', new AbortController().signal, vi.fn())).rejects.toThrow('Incomplete');
    });
    test('rejects server errors without treating them as a result', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"error","message":"Invalid DAG"}\n\n'])));
        await expect(buildTextArticleMap('article', new AbortController().signal, vi.fn())).rejects.toThrow('Invalid DAG');
    });
});
