import React from 'react';
import { describe, expect, test, vi } from 'vitest';
import { render } from '@testing-library/react';
import RefChip from '../RefChip';
import type { UuidRef } from '../WysiwygContext';

const GRP_YOUNG = '00065966-ea98-83eb-a060-d391f64300f7';

const refs: UuidRef[] = [
    { id: 'doc', label: 'doc' },
    { id: GRP_YOUNG, label: 'A. russatus young', blockType: 55 },
];

const noop = vi.fn();

describe('RefChip изолированно', () => {
    test('резолвит существующий id в label', () => {
        const { container } = render(
            <RefChip
                lineId="l1"
                fieldKey="f#0g"
                value={GRP_YOUNG}
                field={{ key: 'experimentalPairs', label: 'Группы', inputType: 'pair-list' }}
                refs={refs}
                onChange={noop}
                onJumpTo={noop}
            />,
        );
        const input = container.querySelector('input');
        console.log('ISOLATED VALUE:', input?.value);
        expect(input?.value).toBe('A. russatus young');
    });
});
