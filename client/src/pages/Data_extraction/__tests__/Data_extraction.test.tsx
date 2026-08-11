import React from 'react';
import { describe, expect, test, beforeEach, afterEach, vi } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../../entities/auth';
import { ToastProvider } from '../../../shared/ui/Toast';
import Data_extraction from '../index';

const okJson = (body: unknown) => ({
    ok: true,
    status: 200,
    clone: () => okJson(body),
    text: async () => JSON.stringify(body),
    json: async () => body,
});

const listResponse = (documents: unknown[]) => ({
    success: true,
    documents,
    total_count: documents.length,
});

const renderPage = async () => {
    await act(async () => {
        render(
            <MemoryRouter>
                <AuthProvider>
                    <ToastProvider>
                        <Data_extraction />
                    </ToastProvider>
                </AuthProvider>
            </MemoryRouter>,
        );
    });
};

const docWithFiles = (uid: string, title: string, hasMarkdown: boolean, pdf = `/files/${uid}.pdf`) => ({
    doc_id: uid,
    files: { pdf },
    has_markdown: hasMarkdown,
    title,
});

/** Мок XMLHttpRequest: по умолчанию завершается ошибкой сети. */
class MockXHR {
    upload = { addEventListener: () => {} };
    status = 0;
    statusText = '';
    responseText = '';
    private handlers: Record<string, Array<(event?: Event) => void>> = {};

    addEventListener(type: string, handler: (event?: Event) => void) {
        (this.handlers[type] ||= []).push(handler);
    }

    open() {}

    send() {
        queueMicrotask(() => {
            (this.handlers['error'] || []).forEach((handler) => handler(new Event('error')));
        });
    }
}

describe('Data_extraction Component', () => {
    beforeEach(() => {
        const fetchMock = vi.fn();
        fetchMock.mockResolvedValue(okJson(listResponse([])));
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('XMLHttpRequest', MockXHR);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    test('рендерится корректно', async () => {
        await renderPage();

        expect(screen.getByText('КАРТА ЗНАНИЙ')).toBeInTheDocument();
        expect(screen.getByText('Загруженные документы')).toBeInTheDocument();
        expect(screen.getByText('Перетащите PDF или нажмите для выбора')).toBeInTheDocument();
        expect(screen.getByText('Аннотатор')).toBeInTheDocument();
        expect(screen.getByText('Исходный PDF')).toBeInTheDocument();
        expect(screen.getByText('Паттерны')).toBeInTheDocument();
    });

    test('отображает область загрузки файлов', async () => {
        await renderPage();

        const fileInput = document.querySelector('input[type="file"]');
        expect(fileInput).toBeInTheDocument();
        expect(fileInput).toHaveAttribute('accept', '.pdf');
    });

    test('загружает список документов', async () => {
        (fetch as Mock).mockResolvedValueOnce(
            okJson(listResponse([
                docWithFiles('doc1', 'Test Paper', false),
                docWithFiles('doc2', 'Second Paper', true),
            ])),
        );

        await renderPage();

        await waitFor(() => {
            expect(screen.getByText('Test Paper')).toBeInTheDocument();
            expect(screen.getByText('Second Paper')).toBeInTheDocument();
        });
    });

    test('показывает статус документов', async () => {
        (fetch as Mock).mockResolvedValueOnce(
            okJson(listResponse([
                docWithFiles('doc1', 'Annotated Doc', true),
                docWithFiles('doc2', 'Ready Doc', false),
            ])),
        );

        await renderPage();

        await waitFor(() => {
            expect(screen.getByText('Аннотирован')).toBeInTheDocument();
            expect(screen.getByText('Готов к аннотированию')).toBeInTheDocument();
        });
    });

    test('позволяет выбрать документ и показывает PDF', async () => {
        (fetch as Mock)
            .mockResolvedValueOnce(
                okJson(listResponse([docWithFiles('doc1', 'Test Paper', true)])),
            )
            .mockResolvedValueOnce(okJson({ pdf_url: '/files/doc1.pdf' }));

        await renderPage();

        const documentItem = await screen.findByText('Test Paper');
        fireEvent.click(documentItem);

        await waitFor(() => {
            const iframe = document.querySelector('iframe');
            expect(iframe).toBeInTheDocument();
            expect(iframe).toHaveAttribute('src', expect.stringContaining('/files/doc1.pdf'));
        });
    });

    test('показывает ошибку для не-PDF файлов', async () => {
        await renderPage();

        const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
        const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

        fireEvent.change(fileInput, { target: { files: [file] } });

        expect(screen.getByText('Пожалуйста, выберите PDF файл')).toBeInTheDocument();
    });

    test('показывает ошибки загрузки', async () => {
        await renderPage();

        const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
        const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

        fireEvent.change(fileInput, { target: { files: [file] } });

        await waitFor(() => {
            expect(screen.getByText('Ошибка загрузки файла')).toBeInTheDocument();
        });
    });

    test('показывает состояние загрузки', async () => {
        await renderPage();

        const file = new File(['test pdf content'], 'test.pdf', { type: 'application/pdf' });
        const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

        fireEvent.change(fileInput, { target: { files: [file] } });

        expect(screen.getByText('Загрузка файла...')).toBeInTheDocument();

        await act(async () => {});
    });
});
