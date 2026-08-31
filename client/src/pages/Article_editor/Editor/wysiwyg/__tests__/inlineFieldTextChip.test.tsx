import React from 'react';
import { describe, expect, test, vi } from 'vitest';
import { render } from '@testing-library/react';
import InlineField from '../InlineField';
import { WysiwygApiContext, type WysiwygApi } from '../WysiwygContext';
import type { UuidRef } from '../WysiwygContext';

const METFORMIN = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const refs: UuidRef[] = [
    { id: METFORMIN, label: 'Метформин', blockType: 4 },
];

function makeApi(): WysiwygApi {
    return {
        refs,
        setField: vi.fn(),
        requestFocus: vi.fn(),
        insertBelow: vi.fn(),
        removeLine: vi.fn(),
        duplicateLine: vi.fn(),
        moveLine: vi.fn(),
        jumpToLine: vi.fn(),
        openSlashMenu: vi.fn(),
        fieldKeyDown: vi.fn(),
        beginFieldEdit: vi.fn(),
        appendChildLine: vi.fn(),
        showUids: false,
    };
}

function renderInline(value: string) {
    const api = makeApi();
    return {
        api,
        ...render(
            <WysiwygApiContext.Provider value={api}>
                <InlineField
                    lineId="l1"
                    field={{ key: 'subject', label: 'Субъект', inputType: 'text' }}
                    value={value}
                />
            </WysiwygApiContext.Provider>,
        ),
    };
}

describe('InlineField text-поле с UUID (T4)', () => {
    test('значение-УУИД рендерится через чип как человекочитаемая метка', () => {
        const { container } = renderInline(METFORMIN);
        const input = container.querySelector('input');
        expect(input?.value).toBe('Метформин');
    });

    test('обычный текст остаётся text-инпутом как есть', () => {
        const { container } = renderInline('Метформин');
        const input = container.querySelector('input');
        expect(input?.value).toBe('Метформин');
    });
});
