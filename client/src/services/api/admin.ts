import { getToken } from '../token';
import type {
  DashboardSummary,
  DashboardCharts,
  UserDetail,
  UserUsageResponse,
  UserPaymentsResponse,
  PaginatedUsers,
  TokenOverview,
  TokenCostBreakdown,
  TokenAnomaliesResponse,
  AnomalyUser,
  SalesOverview,
  SalesByPackageResponse,
  PackageSales,
  ExpensesResponse,
  Expense,
  ExpenseSummary,
  ProvidersResponse,
  AIProvider,
  ProviderCreateRequest,
  ProviderUpdateRequest,
  ProviderPricesResponse,
  PriceVersion,
  PriceVersionCreateRequest,
  FinancialPlan,
  PlanVsFactResponse,
  StagesResponse,
  StrategyStage,
  CapitalCalculation,
  UnitEconomicsResponse,
  UnitEconomics,
  BreakevenResult,
  LaunchScenariosResponse,
  LaunchScenario,
  LaunchCalculationResult,
  AuditLogResponse,
  Period,
  UserFilters,
} from '../../pages/Admin/model';

const API_BASE = '/api/admin';

async function adminFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set('Accept', 'application/json');
    const token = getToken();
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    if (init?.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }
    const url = `${API_BASE}${path}`;
    const response = await fetch(url, { ...init, headers });
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
    if (response.status === 204) {
        return undefined as T;
    }
    return response.json() as Promise<T>;
}

function buildQueryString(params: Record<string, unknown>): string {
    const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
    if (entries.length === 0) return '';
    const qs = entries
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&');
    return `?${qs}`;
}

// ── Dashboard ────────────────────────────────────────────────────────────────

export function fetchDashboardSummary(period: Period = 'month'): Promise<DashboardSummary> {
    const qs = buildQueryString({ period });
    return adminFetchJson<DashboardSummary>(`/dashboard/summary${qs}`);
}

export function fetchDashboardCharts(period: Period = 'month'): Promise<DashboardCharts> {
    const qs = buildQueryString({ period });
    return adminFetchJson<DashboardCharts>(`/dashboard/charts${qs}`);
}

// ── Users ─────────────────────────────────────────────────────────────────────

export function fetchUsers(filters: UserFilters = {}): Promise<PaginatedUsers> {
    const qs = buildQueryString(filters as Record<string, unknown>);
    return adminFetchJson<PaginatedUsers>(`/users${qs}`);
}

export function fetchUserDetail(uid: string): Promise<UserDetail> {
    return adminFetchJson<UserDetail>(`/users/${encodeURIComponent(uid)}`);
}

export function fetchUserUsage(uid: string, limit = 100): Promise<UserUsageResponse> {
    const qs = buildQueryString({ limit });
    return adminFetchJson<UserUsageResponse>(`/users/${encodeURIComponent(uid)}/usage${qs}`);
}

export function fetchUserPayments(uid: string, limit = 100): Promise<UserPaymentsResponse> {
    const qs = buildQueryString({ limit });
    return adminFetchJson<UserPaymentsResponse>(`/users/${encodeURIComponent(uid)}/payments${qs}`);
}

// ── Tokens ─────────────────────────────────────────────────────────────────────

export function fetchTokenOverview(): Promise<TokenOverview> {
    return adminFetchJson<TokenOverview>('/tokens/overview');
}

export function fetchTokenCostBreakdown(): Promise<TokenCostBreakdown> {
    return adminFetchJson<TokenCostBreakdown>('/tokens/cost');
}

export function fetchTokenAnomalies(zThreshold = 2.0): Promise<AnomalyUser[]> {
    const qs = buildQueryString({ z_threshold: zThreshold });
    return adminFetchJson<TokenAnomaliesResponse>(`/tokens/anomalies${qs}`).then((r) => r.anomalies);
}

// ── Sales ──────────────────────────────────────────────────────────────────────

export function fetchSalesOverview(): Promise<SalesOverview> {
    return adminFetchJson<SalesOverview>('/sales/overview');
}

export function fetchSalesByPackage(): Promise<PackageSales[]> {
    return adminFetchJson<SalesByPackageResponse>('/sales/by-package').then((r) => r.by_package);
}

// ── Expenses ───────────────────────────────────────────────────────────────────

export function fetchExpenses(filters?: Partial<Expense>): Promise<Expense[]> {
    const qs = filters ? buildQueryString(filters as Record<string, unknown>) : '';
    return adminFetchJson<ExpensesResponse>(`/expenses${qs}`).then((r) => r.expenses);
}

export function createExpense(data: {
    category: string;
    subcategory?: string;
    description: string;
    amount_kopecks: number;
    currency?: string;
    period_start: string;
    period_end: string;
    is_recurring?: boolean;
    is_fixed?: boolean;
    source?: string;
}): Promise<void> {
    return adminFetchJson<void>('/expenses', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function updateExpense(uid: string, data: Partial<Expense>): Promise<void> {
    return adminFetchJson<void>(`/expenses/${encodeURIComponent(uid)}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

export function deleteExpense(uid: string): Promise<void> {
    return adminFetchJson<void>(`/expenses/${encodeURIComponent(uid)}`, {
        method: 'DELETE',
    });
}

export function fetchExpenseSummary(): Promise<ExpenseSummary> {
    return adminFetchJson<ExpenseSummary>('/expenses/summary');
}

// ── Providers ──────────────────────────────────────────────────────────────────

export async function fetchProviders(): Promise<AIProvider[]> {
    const res = await adminFetchJson<ProvidersResponse>('/providers');
    return res.providers;
}

export function createProvider(data: ProviderCreateRequest): Promise<void> {
    return adminFetchJson<void>('/providers', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function updateProvider(uid: string, data: ProviderUpdateRequest): Promise<void> {
    return adminFetchJson<void>(`/providers/${encodeURIComponent(uid)}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

export async function fetchProviderPrices(uid: string): Promise<PriceVersion[]> {
    const res = await adminFetchJson<ProviderPricesResponse>(`/providers/${encodeURIComponent(uid)}/prices`);
    return res.prices;
}

export function createPriceVersion(providerUid: string, data: PriceVersionCreateRequest): Promise<void> {
    return adminFetchJson<void>(`/providers/${encodeURIComponent(providerUid)}/prices`, {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

// ── Financial Plan ─────────────────────────────────────────────────────────────

export function fetchFinancialPlan(): Promise<FinancialPlan> {
    return adminFetchJson<FinancialPlan>('/plan');
}

export function saveFinancialPlan(data: { name: string; data: Record<string, number> }): Promise<void> {
    return adminFetchJson<void>('/plan', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export async function fetchPlanVsFact(): Promise<PlanVsFactResponse> {
    return adminFetchJson<PlanVsFactResponse>('/plan/plan-vs-fact');
}

// ── Strategy ───────────────────────────────────────────────────────────────────

export async function fetchStages(): Promise<StrategyStage[]> {
    const res = await adminFetchJson<StagesResponse>('/strategy/stages');
    return res.stages;
}

export function saveStage(data: { user_count: number; stage_name: string; data: Record<string, unknown> }): Promise<void> {
    return adminFetchJson<void>('/strategy/stages', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function fetchCapitalCalculation(): Promise<CapitalCalculation> {
    return adminFetchJson<CapitalCalculation>('/strategy/capital');
}

// ── Unit Economics ─────────────────────────────────────────────────────────────

export async function fetchUnitEconomics(): Promise<UnitEconomics[]> {
    const res = await adminFetchJson<UnitEconomicsResponse>('/unit-economics');
    return res.packages;
}

export async function fetchBreakeven(): Promise<BreakevenResult> {
    return adminFetchJson<BreakevenResult>('/unit-economics/breakeven');
}

// ── Launch ─────────────────────────────────────────────────────────────────────

export async function fetchLaunchScenarios(): Promise<LaunchScenario[]> {
    const res = await adminFetchJson<LaunchScenariosResponse>('/launch/scenarios');
    return res.scenarios;
}

export function saveLaunchParams(data: { name: string; params: Record<string, unknown> }): Promise<void> {
    return adminFetchJson<void>('/launch/params', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function calculateLaunch(data: {
    audience_size: number;
    conversion_rate: number;
    avg_check_rubles: number;
    ai_cost_per_user_rubles: number;
    fixed_costs_rubles?: number;
    cac_rubles?: number;
}): Promise<LaunchCalculationResult> {
    return adminFetchJson<LaunchCalculationResult>('/launch/calculate', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

// ── Audit ──────────────────────────────────────────────────────────────────────

export function fetchAuditLog(params?: { page?: number; page_size?: number; admin_uid?: string; action?: string }): Promise<AuditLogResponse> {
    const qs = params ? buildQueryString(params as Record<string, unknown>) : '';
    return adminFetchJson<AuditLogResponse>(`/audit${qs}`);
}