import { describe, expect, test } from 'vitest';
import type { ArticleBlockData } from '../../../model';
import {
    blockLabel,
    buildBlockTree,
    buildRefIndex,
    isUuid,
    resolveChainText,
    sortBlocksByOrder,
} from '../resolveTree';

const META = '11111111-1111-1111-1111-111111111111';
const STEP_A = '22222222-2222-2222-2222-222222222222';
const STEP_B = '33333333-3333-3333-3333-333333333333';
const FINDING = '44444444-4444-4444-4444-444444444444';

const mk = (
    instanceId: string,
    blockType: string,
    data: Record<string, unknown>,
    order: number,
): ArticleBlockData => ({
    instanceId,
    blockType,
    data: data as ArticleBlockData['data'],
    order,
});

const experiment = (): ArticleBlockData[] => [
    mk(STEP_B, 'experiment_step', { stepName: 'Взвешивание' }, 3),
    mk(META, 'experiment', { experimentName: 'Эксперимент', steps: JSON.stringify([STEP_A, STEP_B]), findings: JSON.stringify([FINDING]) }, 0),
    mk(FINDING, 'finding', { parameter: 'Масса снизилась' }, 4),
    mk(STEP_A, 'experiment_step', { stepName: 'Кормление' }, 2),
];

describe('isUuid', () => {
    test('распознаёт UUID и отклоняет остальное', () => {
        expect(isUuid(META)).toBe(true);
        expect(isUuid('abc123')).toBe(false);
        expect(isUuid('')).toBe(false);
    });
});

describe('sortBlocksByOrder', () => {
    test('восстанавливает порядок документа по order', () => {
        const sorted = sortBlocksByOrder(experiment());
        expect(sorted.map((b) => b.instanceId)).toEqual([META, STEP_A, STEP_B, FINDING]);
    });
});

describe('buildBlockTree', () => {
    test('строит parent/children/depth из полей steps/findings (uuid-list)', () => {
        const tree = buildBlockTree(experiment());

        expect(tree.parentOf.get(STEP_A)).toBe(META);
        expect(tree.parentOf.get(STEP_B)).toBe(META);
        expect(tree.parentOf.get(FINDING)).toBe(META);
        expect(tree.parentOf.get(META)).toBeNull();

        expect(tree.childrenOf.get(META)).toEqual([STEP_A, STEP_B, FINDING]);
        expect(tree.childrenOf.get(STEP_A)).toBeUndefined();

        expect(tree.depthOf.get(META)).toBe(0);
        expect(tree.depthOf.get(STEP_A)).toBe(1);
        expect(tree.depthOf.get(FINDING)).toBe(1);
    });

    test('игнорирует ссылки на несуществующие блоки и само-ссылки', () => {
        const blocks = [
            mk(META, 'experiment', { steps: JSON.stringify(['deadbeef-dead-dead-dead-deaddeadbeef', META]) }, 0),
        ];
        const tree = buildBlockTree(blocks);
        expect(tree.parentOf.get(META)).toBeNull();
        expect(tree.childrenOf.size).toBe(0);
    });

    test('первое родство выигрывает при конфликте родителей', () => {
        const blocks = [
            mk(META, 'experiment', { steps: JSON.stringify([STEP_A]) }, 0),
            mk('55555555-5555-5555-5555-555555555555', 'experiment', { steps: JSON.stringify([STEP_A]) }, 1),
            mk(STEP_A, 'experiment_step', {}, 2),
        ];
        const tree = buildBlockTree(blocks);
        expect(tree.parentOf.get(STEP_A)).toBe(META);
    });
});

describe('blockLabel', () => {
    test('для триплета собирает «субъект → предикат → объект»', () => {
        const b = mk('t1', 'statement', { subject: 'Метформин', predicate: 'снижает', object: 'массу' }, 0);
        expect(blockLabel(b)).toBe('Метформин → снижает → массу');
    });

    test('частично заполненный триплет использует ? для пустых частей', () => {
        const b = mk('t1', 'statement', { subject: '', predicate: '', object: 'объект' }, 0);
        expect(blockLabel(b)).toBe('? → объект');
    });

    test('без триплетных полей берёт первое заполненное текстовое поле типа', () => {
        const b = mk('e1', 'experiment', { experimentName: 'Эксперимент' }, 0);
        expect(blockLabel(b)).toBe('Эксперимент');
    });

    test('пустой блок — имя типа', () => {
        const b = mk('m1', 'metadata', {}, 0);
        expect(blockLabel(b)).toBe('Метаданные');
    });
});

describe('buildRefIndex / resolveChainText', () => {
    test('chainText разворачивает цепочку «родитель → … → блок» через метки', () => {
        const blocks = experiment();
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);

        expect(index.get(STEP_A)?.label).toBe('Кормление');
        expect(resolveChainText(STEP_A, tree, index)).toBe(
            'Эксперимент → Кормление',
        );
        expect(resolveChainText(META, tree, index)).toBe('Эксперимент');
    });

    test('неизвестный id — возвращает сам id', () => {
        const blocks = experiment();
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        expect(resolveChainText('unknown-id', tree, index)).toBe('unknown-id');
    });

    test('первый по order блок вне дерева имеет chainText = label, а не голый instanceId', () => {
        // Регрессия: chainText считался до наполнения индекса, из-за чего
        // блоки, идущие раньше родителей (или вовсе вне дерева — T55/T18),
        // получали chainText в виде голого UUID.
        const blocks: ArticleBlockData[] = [
            { instanceId: 'grp-1', blockType: 'animal_group', order: 0, data: { groupName: 'A. russatus young' } },
            ...experiment(),
        ];
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        expect(index.get('grp-1')?.chainText).toBe('A. russatus young');
        expect(index.get(META)?.chainText).toBe('Эксперимент');
    });
});

describe('buildRefIndex / резолв UUID в subject/object (T4/T2)', () => {
    const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    const B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
    const X = '11111111-1111-4111-8111-111111111111';
    const Y = '22222222-2222-4222-8222-222222222222';

    test('T4-триплет с UUID в subject/object резолвится в человекочитаемую метку', () => {
        // B — целевой блок «Метформин»; A — T4 «{B} снижает массу».
        const blocks: ArticleBlockData[] = [
            mk(B, 'statement', { subject: 'Метформин', predicate: 'является', object: 'лекарством' }, 0),
            mk(A, 'statement', { subject: B, predicate: 'снижает', object: 'массу' }, 1),
        ];
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        expect(index.get(B)?.label).toBe('Метформин → является → лекарством');
        expect(index.get(A)?.label).toBe('Метформин → является → лекарством → снижает → массу');
    });

    test('T2 «Цель исследования» с uuid-ref субъектом/объектом резолвится', () => {
        const blocks: ArticleBlockData[] = [
            mk(X, 'impact_goal', { cell: 'гепатоцит' }, 0),
            mk(Y, 'intervention', { intervention: 'рапамицин' }, 1),
            mk(A, 'goal', { subject: X, predicate: 'цель — изучить', object: Y }, 2),
        ];
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        expect(index.get(A)?.label).toBe('гепатоцит → цель — изучить → рапамицин');
    });

    test('защита от циклов: A↔B не зацикливается и завершается', () => {
        const blocks: ArticleBlockData[] = [
            mk(A, 'statement', { subject: B, predicate: 'влияет', object: 'сам' }, 0),
            mk(B, 'statement', { subject: A, predicate: 'отвечает', object: 'второму' }, 1),
        ];
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        // Метки вычислены без бесконечной рекурсии.
        expect(index.get(A)?.label).toBeTruthy();
        expect(index.get(B)?.label).toBeTruthy();
    });

    test('не-UUID значения не трогаются', () => {
        const blocks: ArticleBlockData[] = [
            mk(A, 'statement', { subject: 'глюкоза', predicate: 'повышает', object: 'инсулин' }, 0),
        ];
        const tree = buildBlockTree(blocks);
        const index = buildRefIndex(blocks, tree);
        expect(index.get(A)?.label).toBe('глюкоза → повышает → инсулин');
    });
});
