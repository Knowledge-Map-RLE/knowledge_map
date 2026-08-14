import { getToken } from '../token';

/**
 * Billing — отдельный микросервис, проксируется по относительному пути
 * /billing/* (vite-proxy в dev, nginx location /billing/ в проде).
 * Поэтому здесь НЕ используется VITE_API_BASE_URL (он указывает на main API).
 */
async function billingFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set('Accept', 'application/json');
    const token = getToken();
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    if (init?.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(path, { ...init, headers });
    if (!response.ok) {
        const errorBody = await response.text().catch(() => '');
        let detail = `HTTP ${response.status} ${response.statusText}`;
        try {
            const errorJson = JSON.parse(errorBody);
            detail = errorJson.detail || errorJson.message || detail;
        } catch {
            if (errorBody) detail = errorBody.slice(0, 500);
        }
        throw new Error(detail);
    }
    return response.json() as Promise<T>;
}

/** Тариф. price — рубли (для отображения). */
export interface BillingPlan {
    code: string;
    name: string;
    price: number;
    price_kopecks: number;
    currency: string;
    period: string;
    credit_limit: number;
    sort_order: number;
}

export interface SubscriptionState {
    active: boolean;
    plan_code: string;
    status: string | null;
    current_period_start: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    credits: {
        balance: number;
        limit: number;
    };
}

export interface CheckoutResult {
    payment_uid: string;
    confirmation_url: string;
}

/** Список доступных тарифов. */
export function fetchPlans(): Promise<BillingPlan[]> {
    return billingFetchJson<BillingPlan[]>('/billing/plans');
}

/** Текущее состояние подписки и баланс кредитов. */
export function fetchSubscription(): Promise<SubscriptionState> {
    return billingFetchJson<SubscriptionState>('/billing/subscription');
}

/** Создание платежа (чекаута) в ЮKassa. */
export function createCheckout(planCode: string): Promise<CheckoutResult> {
    return billingFetchJson<CheckoutResult>('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ plan_code: planCode }),
    });
}

/** Отмена подписки с конца оплаченного периода. */
export function cancelSubscription(): Promise<{ status: string }> {
    return billingFetchJson<{ status: string }>('/billing/subscription/cancel', {
        method: 'POST',
        body: JSON.stringify({}),
    });
}
