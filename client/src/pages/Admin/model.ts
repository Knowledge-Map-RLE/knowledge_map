export type Period = 'day' | 'week' | 'month' | 'quarter' | 'year';

// ── Dashboard ────────────────────────────────────────────────────────────────

export interface DashboardSummary {
  period: string;
  start_date: string;
  end_date: string;
  revenue_rubles: number;
  expenses_rubles: number;
  ai_cost_rubles: number;
  infrastructure_cost_rubles: number;
  tax_rubles: number;
  acquiring_rubles: number;
  advertising_rubles: number;
  other_costs_rubles: number;
  profit_rubles: number;
  margin_pct: number;
  total_users: number;
  paying_users: number;
  active_users: number;
  average_check_rubles: number;
  ai_cost_per_paying_user: number;
  cac_rubles: number;
}

export interface ChartPoint {
  date: string;
  value: number;
}

export interface DashboardCharts {
  period: string;
  start_date: string;
  end_date: string;
  revenue_by_period: ChartPoint[];
  expenses_by_period: ChartPoint[];
  ai_cost_by_period: ChartPoint[];
  profit_by_period: ChartPoint[];
}

// ── Users ────────────────────────────────────────────────────────────────────

export interface AdminUserSummary {
  uid: string;
  plan_code: string;
  subscription_status: string;
  payment_count: number;
  total_payments_rubles: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  ai_cost_rubles: number;
  request_count: number;
  last_request: string | null;
}

export interface PaginatedUsers {
  users: AdminUserSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserDetail {
  uid: string;
  plan_code: string;
  subscription_status: string;
  total_payments_count: number;
  total_payments_rubles: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  ai_cost_rubles: number;
  revenue_rubles: number;
  profit_rubles: number;
  request_count: number;
  last_ai_request: string | null;
}

export interface UserUsageRecord {
  created_at: string | null;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  cost_rubles: number;
}

export interface UserUsageResponse {
  uid: string;
  usage: UserUsageRecord[];
}

export interface UserPayment {
  uid: string;
  amount_kopecks: number;
  amount_rubles: number;
  status: string;
  plan_code: string;
  created_at: string | null;
}

export interface UserPaymentsResponse {
  uid: string;
  payments: UserPayment[];
}

export interface UserFilters {
  page?: number;
  page_size?: number;
  search?: string;
  plan_code?: string;
  has_payments?: boolean;
  min_tokens?: number;
  max_tokens?: number;
  is_active?: boolean;
  min_cost?: number;
  max_cost?: number;
}

// ── Tokens ────────────────────────────────────────────────────────────────────

export interface TokenOverview {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cached_tokens: number;
  total_tokens: number;
  input_share_pct: number;
  output_share_pct: number;
  cache_share_pct: number;
  avg_per_user: number;
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  total_ai_cost_rubles: number;
}

export interface TokenCostBreakdown {
  total_input_tokens: number;
  total_output_tokens: number;
  total_cached_tokens: number;
  total_tokens: number;
  input_price_per_token: number;
  output_price_per_token: number;
  cache_price_per_token: number;
  input_cost_rubles: number;
  output_cost_rubles: number;
  cache_cost_rubles: number;
  total_cost_rubles: number;
}

export interface AnomalyUser {
  uid: string;
  total_tokens: number;
  ai_cost_rubles: number;
  z_score: number;
}

export interface TokenAnomaliesResponse {
  anomalies: AnomalyUser[];
  z_threshold: number;
}

// ── Sales ────────────────────────────────────────────────────────────────────

export interface SalesOverview {
  total_sales_count: number;
  total_revenue_rubles: number;
  average_check_rubles: number;
  refunds_count: number;
  refunds_amount_rubles: number;
  net_revenue_rubles: number;
}

export interface PackageSales {
  plan_code: string;
  sale_count: number;
  total_kopecks: number;
  revenue_rubles: number;
}

export interface SalesByPackageResponse {
  by_package: PackageSales[];
}

// ── Expenses ──────────────────────────────────────────────────────────────────

export interface Expense {
  uid: string;
  category: string;
  subcategory: string;
  description: string;
  amount_kopecks: number;
  amount_rubles: number;
  currency: string;
  period_start: string;
  period_end: string;
  is_recurring: boolean;
  is_fixed: boolean;
  source: string;
  created_by_uid: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExpensesResponse {
  expenses: Expense[];
}

export interface ExpenseSummary {
  total_rubles: number;
  infrastructure_rubles: number;
  ai_tokens_rubles: number;
  acquiring_rubles: number;
  advertising_rubles: number;
  tax_rubles: number;
  other_rubles: number;
  fixed_rubles: number;
  variable_rubles: number;
}

// ── Providers ─────────────────────────────────────────────────────────────────

export interface AIProvider {
  uid: string;
  name: string;
  display_name: string;
  base_url: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProvidersResponse {
  providers: AIProvider[];
}

export interface PriceVersion {
  uid: string;
  provider_uid: string;
  model: string;
  input_price_per_million: number;
  output_price_per_million: number;
  cache_input_price_per_million: number | null;
  currency: string;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface ProviderPricesResponse {
  provider_uid: string;
  prices: PriceVersion[];
}

export interface ProviderCreateRequest {
  name: string;
  display_name: string;
  base_url?: string;
}

export interface ProviderUpdateRequest {
  display_name?: string;
  base_url?: string;
  is_active?: boolean;
}

export interface PriceVersionCreateRequest {
  model: string;
  input_price_per_million: number;
  output_price_per_million: number;
  cache_input_price_per_million?: number;
  currency?: string;
  is_active?: boolean;
}

// ── Financial Plan ────────────────────────────────────────────────────────────

export interface FinancialPlan {
  uid: string;
  version: number;
  name: string;
  data: Record<string, unknown>;
  is_active: boolean;
  created_by_uid: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface PlanVsFactItem {
  metric_name: string;
  metric_label: string;
  plan_value: number;
  fact_value: number;
  deviation_abs: number;
  deviation_pct: number;
  formula: string;
  unit: string;
}

export interface PlanVsFactSummary {
  total_metrics: number;
  better_than_plan: number;
  worse_than_plan: number;
  on_plan: number;
  anomalies_count: number;
}

export interface PlanVsFactResponse {
  plan_name: string;
  plan_version: number;
  items: PlanVsFactItem[];
  summary: PlanVsFactSummary;
}

// ── Strategy ──────────────────────────────────────────────────────────────────

export interface StrategyStage {
  uid: string;
  user_count: number;
  stage_name: string;
  data: Record<string, unknown>;
  created_by_uid: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface StagesResponse {
  stages: StrategyStage[];
}

export interface CapitalCalculation {
  min_capital_rubles: number;
  base_capital_rubles: number;
  conservative_capital_rubles: number;
  monthly_fixed_costs_rubles: number;
  months_to_breakeven: number;
  max_negative_cashflow_rubles: number;
}

// ── Unit Economics ────────────────────────────────────────────────────────────

export interface UnitEconomics {
  plan_code: string;
  plan_name: string;
  tokens_granted: number;
  price_rubles: number;
  ai_cost_rubles: number;
  tax_rubles: number;
  acquiring_rubles: number;
  cac_rubles: number;
  contribution_profit_rubles: number;
  contribution_margin_pct: number;
}

export interface UnitEconomicsResponse {
  packages: UnitEconomics[];
}

export interface BreakevenResult {
  fixed_costs_rubles: number;
  ai_cost_per_user_rubles: number;
  avg_check_rubles: number;
  contribution_profit_rubles: number;
  breakeven_users: number;
  avg_tokens_per_package: number;
}

// ── Launch ────────────────────────────────────────────────────────────────────

export interface LaunchScenario {
  uid: string;
  name: string;
  params: Record<string, unknown>;
  created_by_uid: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface LaunchScenariosResponse {
  scenarios: LaunchScenario[];
}

export interface LaunchCalculationResult {
  audience_size: number;
  conversion_rate: number;
  visitors: number;
  registrations: number;
  buyers: number;
  revenue_rubles: number;
  ai_cost_rubles: number;
  expenses_rubles: number;
  profit_rubles: number;
  required_capital_rubles: number;
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  uid: string;
  admin_uid: string;
  action: string;
  entity_type: string;
  entity_uid: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string | null;
}

export interface AuditLogResponse {
  entries: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}