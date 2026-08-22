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
    full_text_count: 0,
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

const docWithFiles = (uid: string, title: string, status: string, isProcessed?: boolean, pdf = `/files/${uid}.pdf`) => ({
    doc_id: uid,
    files: { pdf },
    has_markdown: status === 'annotated',
    has_full_text: status === 'annotated',
    processing_status: status,
    is_processed: isProcessed ?? status === 'annotated',
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
        expect(screen.getByText('Документы')).toBeInTheDocument();
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
                docWithFiles('doc1', 'Test Paper', 'ready_for_annotation'),
                docWithFiles('doc2', 'Second Paper', 'annotated'),
            ])),
        );

        await renderPage();

        await waitFor(() => {
            expect(screen.getByText('Test Paper')).toBeInTheDocument();
            expect(screen.getByText('Second Paper')).toBeInTheDocument();
        });
    });

    test('показывает статусы из сервера', async () => {
        (fetch as Mock).mockResolvedValueOnce(
            okJson(listResponse([
                docWithFiles('doc1', 'Annotated Doc', 'annotated'),
                docWithFiles('doc2', 'Ready Doc', 'ready_for_annotation'),
                docWithFiles('doc3', 'Saved But Invalid', 'ready_for_annotation', false),
            ])),
        );

        await renderPage();

        await waitFor(() => {
            // Статус берётся с сервера, а не вычисляется из has_markdown:
            // документ с сохранённым (но невалидным) markdown не «Аннотирован».
            expect(screen.getByText('Аннотирован')).toBeInTheDocument();
            expect(screen.getAllByText('Готов к аннотированию')).toHaveLength(2);
        });
    });

    test('позволяет выбрать документ и показывает PDF', async () => {
        (fetch as Mock)
            .mockResolvedValueOnce(
                okJson(listResponse([docWithFiles('doc1', 'Test Paper', 'annotated')])),
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
