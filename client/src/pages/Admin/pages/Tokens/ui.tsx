import { useCallback, useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import KPICard from '../../components/KPICard';
import { fetchTokenOverview, fetchTokenCostBreakdown, fetchTokenAnomalies } from '../../../../services/api/admin';
import type { TokenOverview, TokenCostBreakdown, AnomalyUser } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');
const COLORS = ['#3b82f6', '#f59e0b', '#22c55e', '#ef4444', '#8b5cf6'];

export default function TokensPage() {
  const [overview, setOverview] = useState<TokenOverview | null>(null);
  const [cost, setCost] = useState<TokenCostBreakdown | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, cst, an] = await Promise.all([
        fetchTokenOverview(),
        fetchTokenCostBreakdown(),
        fetchTokenAnomalies(),
      ]);
      setOverview(ov);
      setCost(cst);
      setAnomalies(an);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка аналитики токенов...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorContainer}>
        <span className={styles.errorText}>{error}</span>
        <button className={styles.adminBtn} onClick={loadData}>Повторить</button>
      </div>
    );
  }

  const pieData = overview
    ? [
        { name: 'Input', value: overview.total_input_tokens },
        { name: 'Output', value: overview.total_output_tokens },
        { name: 'Cache', value: overview.total_cached_tokens },
      ]
    : [];

  return (
    <div>
      <h1>Токены</h1>

      {overview && (
        <>
          <div className={styles.kpiGrid}>
            <KPICard title="Input токены" value={overview.total_input_tokens} tooltip="Входные токены" color="#3b82f6" />
            <KPICard title="Output токены" value={overview.total_output_tokens} tooltip="Выходные токены" color="#f59e0b" />
            <KPICard title="Cache токены" value={overview.total_cached_tokens} tooltip="Кэшированные токены" color="#22c55e" />
            <KPICard title="Всего токенов" value={overview.total_tokens} />
            <KPICard title="Input доля" value={overview.input_share_pct} suffix=" %" tooltip="Доля input-токенов" />
            <KPICard title="Output доля" value={overview.output_share_pct} suffix=" %" tooltip="Доля output-токенов" />
            <KPICard title="В среднем на пользователя" value={overview.avg_per_user} />
            <KPICard title="P50" value={overview.p50} tooltip="Медиана токенов на запрос" />
            <KPICard title="P90" value={overview.p90} />
            <KPICard title="P95" value={overview.p95} />
            <KPICard title="P99" value={overview.p99} />
            <KPICard
              title="Общая стоимость AI"
              value={overview.total_ai_cost_rubles}
              suffix=" ₽"
              color="#ef4444"
            />
          </div>

          <div className={styles.grid2}>
            <div className={styles.chartContainer}>
              <h3>Структура токенов</h3>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {pieData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                    formatter={(value: number) => fmt.format(value)}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {cost && (
              <div className={styles.card}>
                <h3>Стоимость по типам</h3>
                <table className={styles.adminTable}>
                  <thead>
                    <tr>
                      <th>Тип</th>
                      <th>Стоимость</th>
                      <th>Доля</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Input</td>
                      <td>{fmt.format(Math.round(cost.input_cost_rubles))} ₽</td>
                      <td>{cost.total_cost_rubles > 0 ? ((cost.input_cost_rubles / cost.total_cost_rubles) * 100).toFixed(1) : 0}%</td>
                    </tr>
                    <tr>
                      <td>Output</td>
                      <td>{fmt.format(Math.round(cost.output_cost_rubles))} ₽</td>
                      <td>{cost.total_cost_rubles > 0 ? ((cost.output_cost_rubles / cost.total_cost_rubles) * 100).toFixed(1) : 0}%</td>
                    </tr>
                    <tr>
                      <td>Cache</td>
                      <td>{fmt.format(Math.round(cost.cache_cost_rubles))} ₽</td>
                      <td>{cost.total_cost_rubles > 0 ? ((cost.cache_cost_rubles / cost.total_cost_rubles) * 100).toFixed(1) : 0}%</td>
                    </tr>
                    <tr style={{ fontWeight: 700 }}>
                      <td>Итого</td>
                      <td>{fmt.format(Math.round(cost.total_cost_rubles))} ₽</td>
                      <td>100%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {anomalies.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h2>Аномальные пользователи</h2>
          <div style={{ overflowX: 'auto' }}>
            <table className={styles.adminTable}>
              <thead>
                <tr>
                  <th>UID</th>
                  <th>Токены</th>
                  <th>AI Cost</th>
                  <th>Отклонение (σ)</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((a: AnomalyUser) => (
                  <tr key={a.uid}>
                    <td style={{ fontSize: '0.75rem', color: '#888' }}>{a.uid.slice(0, 8)}...</td>
                    <td>{fmt.format(a.total_tokens)}</td>
                    <td>{fmt.format(Math.round(a.ai_cost_rubles))} ₽</td>
                    <td className={styles.negative}>{a.z_score.toFixed(1)}σ</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}