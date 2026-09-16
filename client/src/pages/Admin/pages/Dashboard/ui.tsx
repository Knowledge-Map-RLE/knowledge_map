import { useCallback, useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import PeriodSelector from '../../components/PeriodSelector';
import KPICard from '../../components/KPICard';
import { fetchDashboardSummary, fetchDashboardCharts } from '../../../../services/api/admin';
import type { Period, DashboardSummary, DashboardCharts } from '../../model';
import styles from '../../Admin.module.css';

const CHART_COLORS = {
  revenue: '#3b82f6',
  expenses: '#ef4444',
  aiCost: '#f59e0b',
  profit: '#22c55e',
};

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>('month');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [charts, setCharts] = useState<DashboardCharts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (p: Period) => {
    setLoading(true);
    setError(null);
    try {
      const [s, c] = await Promise.all([
        fetchDashboardSummary(p),
        fetchDashboardCharts(p),
      ]);
      setSummary(s);
      setCharts(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(period);
  }, [period, loadData]);

  const handlePeriodChange = (p: Period) => setPeriod(p);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка дашборда...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorContainer}>
        <span className={styles.errorText}>{error}</span>
        <button className={styles.adminBtn} onClick={() => loadData(period)}>Повторить</button>
      </div>
    );
  }

  const fmt = new Intl.NumberFormat('ru-RU');

  return (
    <div>
      <h1>Обзор</h1>
      <PeriodSelector value={period} onChange={handlePeriodChange} />

      {summary && (
        <div className={styles.kpiGrid}>
          <KPICard
            title="Выручка"
            value={summary.revenue_rubles}
            suffix=" ₽"
            tooltip="Общая выручка за период"
            color="#3b82f6"
          />
          <KPICard
            title="Расходы"
            value={summary.expenses_rubles}
            suffix=" ₽"
            tooltip="Все расходы за период"
            color="#ef4444"
          />
          <KPICard
            title="AI Cost"
            value={summary.ai_cost_rubles}
            suffix=" ₽"
            tooltip="Стоимость вызовов AI-моделей"
            color="#f59e0b"
          />
          <KPICard
            title="Инфраструктура"
            value={summary.infrastructure_cost_rubles}
            suffix=" ₽"
            tooltip="Серверы, хранение, сеть"
          />
          <KPICard
            title="Налоги"
            value={summary.tax_rubles}
            suffix=" ₽"
            tooltip="НДС, налог на прибыль"
          />
          <KPICard
            title="Эквайринг"
            value={summary.acquiring_rubles}
            suffix=" ₽"
            tooltip="Комиссия платёжной системы (~2%)"
          />
          <KPICard
            title="Реклама"
            value={summary.advertising_rubles}
            suffix=" ₽"
            tooltip="Расходы на привлечение"
          />
          <KPICard
            title="Прочие расходы"
            value={summary.other_costs_rubles}
            suffix=" ₽"
          />
          <KPICard
            title="Прибыль"
            value={summary.profit_rubles}
            suffix=" ₽"
            tooltip="Выручка − Расходы"
            color={summary.profit_rubles >= 0 ? '#22c55e' : '#ef4444'}
          />
          <KPICard
            title="Маржа"
            value={summary.margin_pct}
            suffix=" %"
            tooltip="Прибыль / Выручка × 100"
            color={summary.margin_pct >= 0 ? '#22c55e' : '#ef4444'}
          />
          <KPICard
            title="Пользователи"
            value={summary.total_users}
            tooltip="Всего зарегистрированных"
          />
          <KPICard
            title="Платящие"
            value={summary.paying_users}
            tooltip="Пользователи с активным планом"
          />
          <KPICard
            title="Активные"
            value={summary.active_users}
            tooltip="Пользователи за период"
          />
          <KPICard
            title="Средний чек"
            value={summary.average_check_rubles}
            suffix=" ₽"
            tooltip="Выручка / Платящие"
          />
          <KPICard
            title="AI Cost / User"
            value={summary.ai_cost_per_paying_user}
            suffix=" ₽"
            tooltip="AI Cost / Платящие"
          />
          <KPICard
            title="CAC"
            value={summary.cac_rubles}
            suffix=" ₽"
            tooltip="Реклама / Новые платящие"
          />
        </div>
      )}

      {charts && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div className={styles.chartContainer}>
            <h3>Выручка</h3>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={charts.revenue_by_period}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  labelStyle={{ color: '#ccc' }}
                  formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                />
                <Area type="monotone" dataKey="value" stroke={CHART_COLORS.revenue} fill={CHART_COLORS.revenue} fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.chartContainer}>
            <h3>Расходы</h3>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={charts.expenses_by_period}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  labelStyle={{ color: '#ccc' }}
                  formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                />
                <Area type="monotone" dataKey="value" stroke={CHART_COLORS.expenses} fill={CHART_COLORS.expenses} fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.chartContainer}>
            <h3>AI Cost</h3>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={charts.ai_cost_by_period}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  labelStyle={{ color: '#ccc' }}
                  formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                />
                <Area type="monotone" dataKey="value" stroke={CHART_COLORS.aiCost} fill={CHART_COLORS.aiCost} fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.chartContainer}>
            <h3>Прибыль</h3>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={charts.profit_by_period}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  labelStyle={{ color: '#ccc' }}
                  formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                />
                <Area type="monotone" dataKey="value" stroke={CHART_COLORS.profit} fill={CHART_COLORS.profit} fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
