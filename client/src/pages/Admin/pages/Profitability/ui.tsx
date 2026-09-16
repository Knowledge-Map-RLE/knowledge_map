import { useCallback, useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import KPICard from '../../components/KPICard';
import PeriodSelector from '../../components/PeriodSelector';
import { fetchDashboardSummary } from '../../../../services/api/admin';
import type { Period, DashboardSummary } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');
const COLORS = ['#3b82f6', '#ef4444', '#f59e0b', '#22c55e', '#8b5cf6', '#ec4899', '#6366f1'];

export default function ProfitabilityPage() {
  const [period, setPeriod] = useState<Period>('month');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (p: Period) => {
    setLoading(true);
    setError(null);
    try {
      setSummary(await fetchDashboardSummary(p));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(period);
  }, [period, loadData]);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка...</span>
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

  const costBreakdown = summary
    ? [
        { name: 'AI', value: summary.ai_cost_rubles },
        { name: 'Инфраструктура', value: summary.infrastructure_cost_rubles },
        { name: 'Налоги', value: summary.tax_rubles },
        { name: 'Эквайринг', value: summary.acquiring_rubles },
        { name: 'Реклама', value: summary.advertising_rubles },
        { name: 'Прочее', value: summary.other_costs_rubles },
      ].filter((c) => c.value > 0)
    : [];

  return (
    <div>
      <h1>Прибыльность</h1>
      <PeriodSelector value={period} onChange={setPeriod} />

      {summary && (
        <>
          <div className={styles.kpiGrid}>
            <KPICard title="Выручка" value={summary.revenue_rubles} suffix=" ₽" color="#3b82f6" />
            <KPICard title="Расходы" value={summary.expenses_rubles} suffix=" ₽" color="#ef4444" />
            <KPICard
              title="Прибыль"
              value={summary.profit_rubles}
              suffix=" ₽"
              color={summary.profit_rubles >= 0 ? '#22c55e' : '#ef4444'}
            />
            <KPICard
              title="Маржа"
              value={summary.margin_pct}
              suffix=" %"
              color={summary.margin_pct >= 0 ? '#22c55e' : '#ef4444'}
            />
          </div>

          <div className={styles.grid2}>
            <div className={styles.chartContainer}>
              <h3>Структура расходов</h3>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={costBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {costBreakdown.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                    formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className={styles.card}>
              <h3>Детализация расходов</h3>
              <table className={styles.adminTable}>
                <thead>
                  <tr>
                    <th>Категория</th>
                    <th>Сумма</th>
                    <th>Доля</th>
                  </tr>
                </thead>
                <tbody>
                  {costBreakdown.map((c) => (
                    <tr key={c.name}>
                      <td>{c.name}</td>
                      <td>{fmt.format(Math.round(c.value))} ₽</td>
                      <td>
                        {summary.expenses_rubles > 0 ? ((c.value / summary.expenses_rubles) * 100).toFixed(1) : 0}%
                      </td>
                    </tr>
                  ))}
                  <tr style={{ fontWeight: 700, borderTop: '1px solid #2a2d37' }}>
                    <td>Итого</td>
                    <td>{fmt.format(Math.round(summary.expenses_rubles))} ₽</td>
                    <td>100%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}