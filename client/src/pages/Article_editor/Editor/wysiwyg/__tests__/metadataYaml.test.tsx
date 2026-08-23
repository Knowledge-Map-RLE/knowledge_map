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

const META_ID = '00065966-ea98-8000-9000-000000000001';

const initialBlocks: ArticleBlockData[] = [
    {
        instanceId: META_ID,
        blockType: 1,
        order: 0,
        data: {
            doi: '10.1016/j.cmet.2024.01.001',
            title: 'Immunometabolic resistors of aging',
            authors: 'Ivanov A.\nPetrov B.',
        },
    },
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

describe('YAML-рендер строки «Метаданные» (T1)', () => {
    test('поля рендерятся внутри <pre> в виде «ключ: значение»', () => {
        const { container } = renderEditor();
        const pre = container.querySelector(`pre[data-wy-line="${META_ID}"]`);
        expect(pre).not.toBeNull();
        expect(pre!.textContent).toContain('doi:');
        expect(pre!.textContent).toContain('title:');
        expect(pre!.textContent).toContain('authors:');
    });

    test('title — многострочный textarea с содержимым', () => {
        const { container } = renderEditor();
        const title = container.querySelector<HTMLTextAreaElement>(`textarea[data-wy-field="title"]`);
        expect(title).not.toBeNull();
        expect(title!.value).toBe('Immunometabolic resistors of aging');
    });

    test('после pre идёт редактируемый h1 с названием; title из pre не удаляется', () => {
        const { container } = renderEditor();
        const pre = container.querySelector(`pre[data-wy-line="${META_ID}"]`);
        expect(pre!.textContent).toContain('title:');
        const heading = container.querySelector('h1');
        expect(heading).not.toBeNull();
        expect(heading!.textContent).toBe('Immunometabolic resistors of aging');
        expect(heading.getAttribute('contenteditable')).toBe('true');
    });

    test('правка h1 обновляет поле title в pre', () => {
        const { container } = renderEditor();
        const heading = container.querySelector('h1')!;
        heading.textContent = 'Новый заголовок';
        fireEvent.input(heading);
        const ta = container.querySelector<HTMLTextAreaElement>('textarea[data-wy-field="title"]');
        expect(ta!.value).toBe('Новый заголовок');
    });

    test('правка title в pre обновляет h1', () => {
        const { container } = renderEditor();
        const ta = container.querySelector<HTMLTextAreaElement>('textarea[data-wy-field="title"]')!;
        fireEvent.change(ta, { target: { value: 'Другое название' } });
        const heading = container.querySelector('h1')!;
        expect(heading.textContent).toBe('Другое название');
    });

    test('authors — отдельный input на каждого автора, с крестиками удаления и кнопкой добавления', () => {
        const { container } = renderEditor();
        const a0 = container.querySelector<HTMLInputElement>(`input[data-wy-field="authors#0"]`);
        const a1 = container.querySelector<HTMLInputElement>(`input[data-wy-field="authors#1"]`);
        expect(a0?.value).toBe('Ivanov A.');
        expect(a1?.value).toBe('Petrov B.');
        const seps = Array.from(container.querySelectorAll(`pre span`)).filter((s) => s.textContent === ',');
        expect(seps.length).toBeGreaterThanOrEqual(1);

        const removeButtons = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent === '×');
        expect(removeButtons.length).toBe(2);
        const addButton = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('+ Фамилия И.'));
        expect(addButton).toBeDefined();
    });

    test('кнопка добавления создаёт новый пустой input автора', () => {
        const { container } = renderEditor();
        const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('+ Фамилия И.'));
        expect(addBtn).toBeDefined();
        fireEvent.click(addBtn!);
        const a2 = container.querySelector<HTMLInputElement>('input[data-wy-field="authors#2"]');
        expect(a2).not.toBeNull();
        expect(a2?.value).toBe('');
    });

    test('крестик удаляет автора', () => {
        const { container } = renderEditor();
        const removeButtons = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent === '×');
        fireEvent.click(removeButtons[0]!);
        const a0 = container.querySelector<HTMLInputElement>('input[data-wy-field="authors#0"]');
        expect(a0).not.toBeNull();
        expect(a0!.value).toBe('Petrov B.');
    });
});
