/**
 * Собственные счётчики посещаемости на OpenTelemetry (cookieless).
 *
 * Метрики экспортируются тем же MeterProvider, что и в telemetry.ts:
 * браузер → Alloy (:4318) → Prometheus (remote_write) → Grafana.
 *
 * Счётчики:
 * - km_web_page_views_total — просмотры страниц (по маршруту SPA);
 * - km_web_visits_total — посещения (один запуск браузера = одно посещение);
 * - km_web_unique_visitors_daily_total — примерное число уникальных
 *   посетителей в день (без cookie, по localStorage-флагу даты).
 *
 * Управление: VITE_OTEL_ENABLED=false выключает экспорт; при отключённой
 * телеметрии глобальный метр — no-op, счётчики безопасно молчат.
 */

import { metrics } from '@opentelemetry/api';
import type { Counter } from '@opentelemetry/api';

const SERVICE_NAME = 'knowledge-map-web';
const UNIQUE_DAY_KEY = 'km_visitor_day';

let pageViewsCounter: Counter | null = null;
let visitsCounter: Counter | null = null;
let uniqueVisitorsCounter: Counter | null = null;
let visitReported = false;
let lastPath = '';

function ensureCounters() {
    if (!pageViewsCounter) {
        const meter = metrics.getMeter(SERVICE_NAME);
        pageViewsCounter = meter.createCounter('km_web_page_views_total', {
            description: 'Page views by SPA route',
            unit: '1',
        });
        visitsCounter = meter.createCounter('km_web_visits_total', {
            description: 'Visits (one per browser boot)',
            unit: '1',
        });
        uniqueVisitorsCounter = meter.createCounter('km_web_unique_visitors_daily_total', {
            description: 'Approximate unique visitors per day (cookieless)',
            unit: '1',
        });
    }
    return { pageViewsCounter, visitsCounter, uniqueVisitorsCounter };
}

function referrerDomain(): string {
    try {
        const url = new URL(document.referrer);
        return url.hostname || 'direct';
    } catch {
        return 'direct';
    }
}

/** Уникальные посетители в день: не чаще одного инкремента на браузер в сутки. */
function reportUniqueVisitorIfNewDay(counter: Counter): void {
    try {
        const today = new Date().toISOString().slice(0, 10);
        if (localStorage.getItem(UNIQUE_DAY_KEY) === today) {
            return;
        }
        localStorage.setItem(UNIQUE_DAY_KEY, today);
        counter.add(1);
    } catch {
        // localStorage недоступен — засчитываем уникального посетителя раз за сессию.
        counter.add(1);
    }
}

export function reportPageView(path: string, opts: { authenticated?: boolean } = {}): boolean {
    const { authenticated = false } = opts;

    // Повторные срабатывания (например, StrictMode в dev) не дублируют просмотр.
    if (lastPath === path) {
        return false;
    }
    lastPath = path;

    const { pageViewsCounter, visitsCounter, uniqueVisitorsCounter } = ensureCounters();

    pageViewsCounter!.add(1, {
        route: path,
        referrer_domain: referrerDomain(),
        authenticated,
    });

    if (!visitReported) {
        visitReported = true;
        visitsCounter!.add(1);
        reportUniqueVisitorIfNewDay(uniqueVisitorsCounter!);
    }
    return true;
}

/** Сбрасывает состояние воркера метрик (используется в тестах). */
export function resetAnalyticsState(): void {
    visitReported = false;
    lastPath = '';
}