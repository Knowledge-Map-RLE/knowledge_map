import { describe, expect, test, vi, beforeEach, afterAll } from 'vitest';
import { reportPageVisit } from '../analytics';
import { httpClient } from '../httpClient';

vi.mock('../httpClient', () => ({
    httpClient: {
        post: vi.fn(),
    },
}));

const postMock = vi.mocked(httpClient.post);

const REFERRER_DESCRIPTOR = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(document),
    'referrer',
);

function setReferrer(value: string) {
    Object.defineProperty(document, 'referrer', {
        value,
        configurable: true,
    });
}

beforeEach(() => {
    postMock.mockReset();
});

afterAll(() => {
    if (REFERRER_DESCRIPTOR) {
        Object.defineProperty(document, 'referrer', REFERRER_DESCRIPTOR);
    }
});

describe('reportPageVisit', () => {
    test('отправляет page-view с маршрутом и referrer direct', async () => {
        setReferrer('');
        postMock.mockResolvedValue({} as Response);

        await reportPageVisit('/km');

        expect(postMock).toHaveBeenCalledTimes(1);
        expect(postMock).toHaveBeenCalledWith('/api/analytics/page-view', {
            route: '/km',
            referrer: 'direct',
        });
    });

    test('извлекает только домен из document.referrer', async () => {
        setReferrer('https://example.com/some/path?q=1');
        postMock.mockResolvedValue({} as Response);

        await reportPageVisit('/science_articles');

        expect(postMock).toHaveBeenCalledWith('/api/analytics/page-view', {
            route: '/science_articles',
            referrer: 'example.com',
        });
    });

    test('ошибка сети не выбрасывает исключение', async () => {
        setReferrer('');
        postMock.mockRejectedValue(new Error('network down'));

        await expect(reportPageVisit('/km')).resolves.toBeUndefined();
    });
});