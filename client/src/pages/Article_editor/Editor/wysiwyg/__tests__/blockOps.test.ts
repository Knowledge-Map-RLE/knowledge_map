import { describe, expect, test } from 'vitest';
import type { ArticleBlockData } from '../../../model';
import {
    duplicateBlock,
    insertBlock,
    moveBlock,
    removeBlocks,
    setBlockField,
    setBlockType,
    sortBlocks,
} from '../blockOps';

const block = (instanceId: string, order: number, data: Record<string, unknown> = {}): ArticleBlockData => ({
    instanceId,
    blockType: 'statement',
    data: data as ArticleBlockData['data'],
    order,
});

describe('blockOps', () => {
    describe('sortBlocks', () => {
        test('сортирует по order, не мутируя вход', () => {
            const input = [block('c', 2), block('a', 0), block('b', 1)];
            const out = sortBlocks(input);
            expect(out.map((b) => b.instanceId)).toEqual(['a', 'b', 'c']);
            expect(input.map((b) => b.instanceId)).toEqual(['c', 'a', 'b']);
        });
    });

    describe('insertBlock', () => {
        test('вставляет в конец и реиндексирует order', () => {
            const { next, instanceId } = insertBlock([block('a', 0)], { blockType: 'statement' });
            expect(next.map((b) => b.instanceId)).toEqual(['a', instanceId]);
            expect(next.map((b) => b.order)).toEqual([0, 1]);
        });

        test('вставляет после указанного индекса', () => {
            const { next, instanceId } = insertBlock(
                [block('a', 0), block('b', 1)],
                { blockType: 'statement', afterIndex: 0 },
            );
            expect(next.map((b) => b.instanceId)).toEqual(['a', instanceId, 'b']);
            expect(next[2].order).toBe(2);
        });

        test('использует переданный instanceId и данные', () => {
            const { next, instanceId } = insertBlock([], {
                blockType: 'statement',
                instanceId: 'fixed-id',
                data: { subject: 'X' },
            });
            expect(instanceId).toBe('fixed-id');
            expect(next[0].data.subject).toBe('X');
        });

        test('не мутирует исходный массив', () => {
            const input = [block('a', 0)];
            insertBlock(input, { blockType: 'statement' });
            expect(input).toHaveLength(1);
        });
    });

    describe('removeBlocks', () => {
        test('удаляет по id и реиндексирует', () => {
            const next = removeBlocks([block('a', 0), block('b', 1), block('c', 2)], ['b']);
            expect(next.map((b) => b.instanceId)).toEqual(['a', 'c']);
            expect(next[1].order).toBe(1);
        });

        test('оставляет порядок при удалении всех', () => {
            expect(removeBlocks([block('a', 0)], ['a'])).toEqual([]);
        });
    });

    describe('moveBlock', () => {
        test('перемещает блок вниз с реиндексацией', () => {
            const next = moveBlock([block('a', 0), block('b', 1), block('c', 2)], 0, 2);
            expect(next.map((b) => b.instanceId)).toEqual(['b', 'c', 'a']);
            expect(next.map((b) => b.order)).toEqual([0, 1, 2]);
        });

        test('перемещает блок вверх', () => {
            const next = moveBlock([block('a', 0), block('b', 1), block('c', 2)], 2, 0);
            expect(next.map((b) => b.instanceId)).toEqual(['c', 'a', 'b']);
        });

        test('ограничивает целевой индекс диапазоном', () => {
            const next = moveBlock([block('a', 0), block('b', 1)], 0, 99);
            expect(next.map((b) => b.instanceId)).toEqual(['b', 'a']);
        });

        test('недопустимый fromIndex оставляет порядок сортированного списка', () => {
            const input = [block('b', 1), block('a', 0)];
            const next = moveBlock(input, -1, 0);
            expect(next.map((b) => b.instanceId)).toEqual(['a', 'b']);
        });
    });

    describe('duplicateBlock', () => {
        test('клонирует блок сразу после оригинала с глубоким копированием данных', () => {
            const source = block('orig', 0, { tags: ['a'] });
            const { next, instanceId } = duplicateBlock([source], 'orig');
            expect(next.map((b) => b.instanceId)).toEqual(['orig', instanceId]);
            expect(next[1].data).not.toBe(source.data);
            expect(next[1].data).toEqual(source.data);
            expect(next[1].blockType).toBe('statement');
            expect(next[1].order).toBe(1);
        });

        test('неизвестный id — состав списка не меняется', () => {
            const input = [block('a', 0)];
            const { next, instanceId } = duplicateBlock(input, 'missing');
            expect(next.map((b) => b.instanceId)).toEqual(['a']);
            expect(instanceId).toBe('missing');
        });
    });

    describe('setBlockField / setBlockType', () => {
        test('меняет поле только у целевого блока', () => {
            const input = [block('a', 0, { subject: 'x' }), block('b', 1, { subject: 'y' })];
            const next = setBlockField(input, 'a', 'subject', 'z');
            expect(next[0].data.subject).toBe('z');
            expect(next[1].data.subject).toBe('y');
        });

        test('не создаёт новый объект блока, если значение не изменилось', () => {
            const input = [block('a', 0, { subject: 'x' })];
            const next = setBlockField(input, 'a', 'subject', 'x');
            expect(next[0]).toBe(input[0]);
        });

        test('меняет тип блока', () => {
            const input = [block('a', 0)];
            const next = setBlockType(input, 'a', 'experiment');
            expect(next[0].blockType).toBe('experiment');
            expect(setBlockType(input, 'a', 'statement')[0]).toBe(input[0]);
        });
    });
});
