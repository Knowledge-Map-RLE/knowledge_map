import React from 'react';
import { describe, expect, test, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
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

// Гейт авторизации отключён: интерактивные тесты редактирования выполняются
// без залогиненного пользователя.
vi.mock('../../../../../shared/hooks/useRequireAuth', () => ({
    useRequireAuth: () => () => true,
}));

import WysiwygEditor from '../WysiwygEditor';
import type { ArticleBlockData } from '../../../model';

const ID_A = '00065966-ea98-8000-9000-00000000000a';
const ID_B = '00065966-ea98-8000-9000-00000000000b';

const initialBlocks: ArticleBlockData[] = [
    { instanceId: ID_A, blockType: 3, order: 0, data: { content: 'AAA' } },
    { instanceId: ID_B, blockType: 3, order: 1, data: { content: 'BBB' } },
];

// Редактор контролируемый: состояние блоков живёт снаружи (onApply),
// поэтому интерактивные тесты используют локальный state.
function EditorHarness() {
    const [blocks, setBlocks] = React.useState(initialBlocks);
    return (
        <AuthProvider>
            <ToastProvider>
                <WysiwygEditor blocks={blocks} statements={[]} articleUuid="doc" onApply={setBlocks} />
            </ToastProvider>
        </AuthProvider>
    );
}

function renderEditor() {
    return render(<EditorHarness />);
}

function contentValues(container: HTMLElement): string[] {
    return Array.from(container.querySelectorAll<HTMLTextAreaElement>('textarea[data-wy-field="content"]'))
        .map((el) => el.value);
}

describe('Вставка новых структурных строк', () => {
    test('hover-линия между строками показывает кнопку «+» с подсказкой; клик вставляет строку между ними', () => {
        const { container } = renderEditor();
        const zones = container.querySelectorAll('[data-wy-insert]');
        expect(zones.length).toBe(3);
        expect(container.querySelector(`[data-wy-insert] button`)).toBeNull();

        fireEvent.mouseEnter(zones[1]);
        const btn = zones[1].querySelector('button');
        expect(btn).not.toBeNull();
        expect(btn!.getAttribute('title')).toBe('Добавить новую строку');

        fireEvent.click(btn!);
        expect(contentValues(container)).toEqual(['AAA', '', 'BBB']);
    });

    test('hover-линия после последней строки вставляет строку в конец', () => {
        const { container } = renderEditor();
        const zones = container.querySelectorAll('[data-wy-insert]');
        fireEvent.mouseEnter(zones[zones.length - 1]);
        fireEvent.click(zones[zones.length - 1].querySelector('button')!);
        expect(contentValues(container)).toEqual(['AAA', 'BBB', '']);
    });

    test('клавиша B вне поля ввода вставляет строку в конец документа', () => {
        const { container } = renderEditor();
        fireEvent.keyDown(document.body, { key: 'b' });
        expect(contentValues(container)).toEqual(['AAA', 'BBB', '']);
    });

    test('клавиша A вне поля ввода вставляет строку в начало документа', () => {
        const { container } = renderEditor();
        fireEvent.keyDown(document.body, { key: 'a' });
        expect(contentValues(container)).toEqual(['', 'AAA', 'BBB']);
    });

    test('Jupyter-семантика: Esc снимает фокус с поля, B вставляет под текущей строкой', () => {
        const { container } = renderEditor();
        const first = container.querySelector<HTMLTextAreaElement>(`textarea[data-wy-line="${ID_A}"]`);
        fireEvent.focus(first!);
        fireEvent.keyDown(first!, { key: 'Escape' });
        expect(document.activeElement).not.toBe(first);
        fireEvent.keyDown(document.body, { key: 'b' });
        expect(contentValues(container)).toEqual(['AAA', '', 'BBB']);
    });

    test('клавиша B внутри поля ввода не перехватывается', () => {
        const { container } = renderEditor();
        const ta = container.querySelector<HTMLTextAreaElement>(`textarea[data-wy-line="${ID_A}"]`);
        fireEvent.keyDown(ta!, { key: 'b' });
        expect(contentValues(container)).toEqual(['AAA', 'BBB']);
    });
});
