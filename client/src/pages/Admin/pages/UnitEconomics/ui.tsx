import { useCallback, useEffect, useState } from 'react';
import KPICard from '../../components/KPICard';
import { fetchUnitEconomics, fetchBreakeven } from '../../../../services/api/admin';
import type { UnitEconomics as UnitEconomicsType, BreakevenResult } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');
const fmtDecimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

export default function UnitEconomicsPage() {
  const [data, setData] = useState<UnitEconomicsType[]>([]);
  const [breakeven, setBreakeven] = useState<BreakevenResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [result, be] = await Promise.all([
        fetchUnitEconomics(),
        fetchBreakeven(),
      ]);
      setData(result);
      setBreakeven(be);
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
        <span className={styles.loadingText}>Загрузка unit economics...</span>
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

  return (
    <div>
      <h1>Unit Economics</h1>

      {breakeven && (
        <div className={styles.kpiGrid}>
          <KPICard title="Фикс. расходы" value={breakeven.fixed_costs_rubles} suffix=" ₽" />
          <KPICard title="AI cost / user" value={breakeven.ai_cost_per_user_rubles} suffix=" ₽" />
          <KPICard title="Средний чек" value={breakeven.avg_check_rubles} suffix=" ₽" />
          <KPICard title="Маржинальная прибыль" value={breakeven.contribution_profit_rubles} suffix=" ₽/пользователь" color="#22c55e" />
          <KPICard title="Break-even" value={breakeven.breakeven_users} suffix=" пользователей" color="#f59e0b" />
        </div>
      )}

      <div style={{ marginTop: 16, overflowX: 'auto' }}>
        <table className={styles.adminTable}>
          <thead>
            <tr>
              <th>Пакет</th>
              <th>Код</th>
              <th>Токены</th>
              <th>Цена</th>
              <th>AI Cost</th>
              <th>Налог</th>
              <th>Эквайринг</th>
              <th>CAC</th>
              <th>Вклад</th>
              <th>Маржа</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row: UnitEconomicsType) => (
              <tr key={row.plan_code}>
                <td style={{ fontWeight: 600 }}>{row.plan_name}</td>
                <td>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: '0.75rem',
                    background: '#1e3a5f',
                    color: '#60a5fa',
                  }}>
                    {row.plan_code}
                  </span>
                </td>
                <td>{row.tokens_granted > 0 ? fmt.format(row.tokens_granted) : '—'}</td>
                <td>{fmt.format(Math.round(row.price_rubles))} ₽</td>
                <td>{fmt.format(Math.round(row.ai_cost_rubles))} ₽</td>
                <td>{fmt.format(Math.round(row.tax_rubles))} ₽</td>
                <td>{fmt.format(Math.round(row.acquiring_rubles))} ₽</td>
                <td>{row.cac_rubles > 0 ? fmt.format(Math.round(row.cac_rubles)) : '—'} ₽</td>
                <td className={row.contribution_profit_rubles >= 0 ? styles.positive : styles.negative}>
                  {fmt.format(Math.round(row.contribution_profit_rubles))} ₽
                </td>
                <td className={row.contribution_margin_pct >= 0 ? styles.positive : styles.negative}>
                  {fmtDecimal.format(row.contribution_margin_pct)}%
                </td>
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td colSpan={10} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data.length > 0 && (
        <div className={styles.card} style={{ marginTop: 16 }}>
          <h3>Окупаемость CAC</h3>
          <div className={styles.kpiGrid}>
            {data.filter((r) => r.price_rubles > 0).map((row) => {
              const breakEvenUnits = row.contribution_profit_rubles > 0
                ? Math.ceil(row.cac_rubles / row.contribution_profit_rubles)
                : Infinity;
              return (
                <div key={`be-${row.plan_code}`} className={styles.kpiCard}>
                  <div className={styles.kpiTitle}>{row.plan_name}</div>
                  <div className={styles.kpiValue}>
                    {breakEvenUnits === Infinity ? '∞' : fmt.format(breakEvenUnits)}
                  </div>
                  <div className={styles.kpiTooltip}>
                    продаж для окупаемости CAC ({fmt.format(Math.round(row.cac_rubles))} ₽)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}