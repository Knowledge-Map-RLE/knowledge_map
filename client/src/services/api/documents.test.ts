import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { clearToken, saveToken } from '../token';
import { uploadPdfForExtraction } from './documents';

class ProgressXhrMock {
    static latest: ProgressXhrMock;
    upload = { addEventListener: vi.fn() };
    status = 200;
    statusText = 'OK';
    responseText = JSON.stringify({ success: true, doc_id: 'doc-1' });
    headers: Record<string, string> = {};
    listeners = new Map<string, Array<() => void>>();
    body?: XMLHttpRequestBodyInit | null;

    constructor() {
        ProgressXhrMock.latest = this;
    }

    addEventListener(type: string, listener: () => void) {
        const listeners = this.listeners.get(type) ?? [];
        listeners.push(listener);
        this.listeners.set(type, listeners);
    }

    open() {}

    setRequestHeader(name: string, value: string) {
        this.headers[name.toLowerCase()] = value;
    }

    send(body?: XMLHttpRequestBodyInit | null) {
        this.body = body;
        this.listeners.get('load')?.forEach((listener) => listener());
    }
}

describe('PDF extraction upload authentication', () => {
    beforeEach(() => {
        clearToken();
        saveToken('test-jwt', false);
    });

    afterEach(() => {
        clearToken();
        vi.unstubAllGlobals();
    });

    test('sends the Bearer token with the upload that reports progress', async () => {
        vi.stubGlobal('XMLHttpRequest', ProgressXhrMock);
        const file = new File(['pdf'], 'document.pdf', { type: 'application/pdf' });

        await uploadPdfForExtraction(file, vi.fn());

        expect(ProgressXhrMock.latest.headers.authorization).toBe('Bearer test-jwt');
        expect(ProgressXhrMock.latest.headers['content-type']).toBeUndefined();
        expect(ProgressXhrMock.latest.body).toBeInstanceOf(FormData);
    });

    test('sends the Bearer token with the upload that does not report progress', async () => {
        const response = {
            ok: true,
            json: async () => ({ success: true, doc_id: 'doc-1' }),
            clone: () => response,
        };
        const fetchMock = vi.fn().mockResolvedValue(response);
        vi.stubGlobal('fetch', fetchMock);
        const file = new File(['pdf'], 'document.pdf', { type: 'application/pdf' });

        await uploadPdfForExtraction(file);

        const request = fetchMock.mock.calls[0][1] as RequestInit;
        const headers = new Headers(request.headers);
        expect(headers.get('Authorization')).toBe('Bearer test-jwt');
        expect(headers.has('Content-Type')).toBe(false);
        expect(request.body).toBeInstanceOf(FormData);
    });
});
