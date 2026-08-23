import React from 'react';
import { describe, expect, test, vi } from 'vitest';
import { render } from '@testing-library/react';
import { AuthProvider } from '../../../../../entities/auth';
import { ToastProvider } from '../../../../../shared/ui/Toast';

vi.mock('@tanstack/react-virtual', () => ({
    useVirtualizer: (opts: { count?: number }) => {
        const count = opts?.count ?? 0;
        return {
            getVirtualItems: () => Array.from({ length: count }, (_, i) => ({ index: i, key: String(i), start: i * 34, size: 34 })),
            getTotalSize: () => count * 34,
            measureElement: () => () => {},
            scrollToIndex: () => {},
            resizeItem: () => {},
        };
    },
}));

import WysiwygEditor from '../WysiwygEditor';
import type { ArticleBlockData } from '../../../model';

const GRP_YOUNG = '00065966-ea98-83eb-a060-d391f64300f7';
const EXP_ID = '00065966-ea98-85fd-a828-18b8bf095810';

const blocks: ArticleBlockData[] = [
    {
        instanceId: GRP_YOUNG,
        blockType: 55,
        order: 0,
        data: { groupName: 'A. russatus young', purpose: 'baseline young control', conditions: '0.5 years, non-SPF', n: 23 },
    },
    {
        instanceId: EXP_ID,
        blockType: 14,
        order: 1,
        data: {
            experimentName: 'Behavioral phenotyping',
            experimentalPairs: JSON.stringify([{ groupRef: GRP_YOUNG, interventionRef: '' }]),
        },
    },
];

describe('pair-list резолв ссылок в чипах', () => {
    test('groupRef, указывающий на существующий T55, показывает метку группы, а не UUID', () => {
        const { container } = render(
            <AuthProvider>
                <ToastProvider>
                    <WysiwygEditor
                        blocks={blocks}
                        statements={[]}
                        articleUuid="000657ba-aec6-8a11-9c5c-986526539651"
                        onApply={vi.fn()}
                    />
                </ToastProvider>
            </AuthProvider>,
        );
        const grpChip = container.querySelector<HTMLInputElement>('input[data-wy-field="experimentalPairs#0g"]');
        expect(grpChip).not.toBeNull();
        expect(grpChip!.value).toBe('A. russatus young');
        expect(grpChip!.value).not.toBe(GRP_YOUNG);
    });

    test('пустой interventionRef остаётся пустым слотом без UUID', () => {
        const { container } = render(
            <AuthProvider>
                <ToastProvider>
                    <WysiwygEditor
                        blocks={blocks}
                        statements={[]}
                        articleUuid="000657ba-aec6-8a11-9c5c-986526539651"
                        onApply={vi.fn()}
                    />
                </ToastProvider>
            </AuthProvider>,
        );
        const ivChip = container.querySelector<HTMLInputElement>('input[data-wy-field="experimentalPairs#0i"]');
        expect(ivChip).not.toBeNull();
        expect(ivChip!.value).toBe('');
    });
});
