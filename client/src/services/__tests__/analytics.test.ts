import { describe, expect, test, beforeEach, vi } from 'vitest';

const h = vi.hoisted(() => {
    const adds: Record<string, ReturnType<typeof vi.fn>> = {};
    const meter = {
        createCounter: (name: string) => {
            if (!adds[name]) {
                adds[name] = vi.fn();
            }
            return { add: adds[name] };
        },
    };
    return { adds, meter };
});

vi.mock('@opentelemetry/api', () => ({
    metrics: { getMeter: () => h.meter },
}));

import { reportPageView, resetAnalyticsState } from '../analytics';

const PAGE_VIEWS = 'km_web_page_views_total';
const VISITS = 'km_web_visits_total';
const UNIQUE = 'km_web_unique_visitors_daily_total';

describe('analytics counters (OTel)', () => {
    beforeEach(() => {
        h.adds[PAGE_VIEWS]?.mockClear();
        h.adds[VISITS]?.mockClear();
        h.adds[UNIQUE]?.mockClear();
        localStorage.clear();
        resetAnalyticsState();
    });

    test('reportPageView увеличивает счётчик просмотров с атрибутами маршрута', () => {
        reportPageView('/km');
        expect(h.adds[PAGE_VIEWS]).toHaveBeenCalledTimes(1);
        expect(h.adds[PAGE_VIEWS].mock.calls[0][0]).toBe(1);
        expect(h.adds[PAGE_VIEWS].mock.calls[0][1]).toEqual({
            route: '/km',
            referrer_domain: 'direct',
            authenticated: false,
        });
    });

    test('повторный отчёт того же маршрута (StrictMode) не дублирует просмотр', () => {
        reportPageView('/km');
        reportPageView('/km');
        expect(h.adds[PAGE_VIEWS]).toHaveBeenCalledTimes(1);
    });

    test('посещение засчитывается один раз на запуск браузера', () => {
        reportPageView('/');
        reportPageView('/km');
        reportPageView('/science_articles');
        expect(h.adds[VISITS]).toHaveBeenCalledTimes(1);
        expect(h.adds[PAGE_VIEWS]).toHaveBeenCalledTimes(3);
    });

    test('уникальный посетитель не засчитывается повторно в пределах суток', () => {
        const today = new Date().toISOString().slice(0, 10);
        localStorage.setItem('km_visitor_day', today);

        reportPageView('/');
        resetAnalyticsState();
        reportPageView('/km');

        expect(h.adds[UNIQUE]).toHaveBeenCalledTimes(0);
    });

    test('уникальный посетитель засчитывается при смене календарного дня', () => {
        localStorage.setItem('km_visitor_day', '2000-01-01');

        reportPageView('/');
        resetAnalyticsState();
        // Новые сутки: дата в хранилище снова устарела.
        localStorage.setItem('km_visitor_day', '2000-01-01');
        reportPageView('/km');

        expect(h.adds[UNIQUE]).toHaveBeenCalledTimes(2);
        expect(h.adds[UNIQUE].mock.calls[0][0]).toBe(1);
        expect(h.adds[UNIQUE].mock.calls[1][0]).toBe(1);
    });
});