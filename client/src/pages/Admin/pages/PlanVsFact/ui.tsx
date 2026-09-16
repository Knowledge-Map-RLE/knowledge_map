import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchPlanVsFact } from '../../../../services/api/admin';
import type { PlanVsFactResponse, PlanVsFactItem } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');

export default function PlanVsFactPage() {
  const [data, setData] = useState<PlanVsFactResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchPlanVsFact());
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
        <span className={styles.loadingText}>Загрузка...</span>
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

  const items = data?.items ?? [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>План → Факт</h1>
        <Link className={styles.adminBtn} to="/admin/plan/editor">
          Открыть редактор плана
        </Link>
      </div>

      {data && (
        <div style={{ color: '#888', fontSize: '0.8rem', marginBottom: 16 }}>
          План: {data.plan_name} · Версия {data.plan_version}
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className={styles.adminTable}>
          <thead>
            <tr>
              <th>Метрика</th>
              <th>План</th>
              <th>Факт</th>
              <th>Отклонение</th>
              <th>Отклонение %</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item: PlanVsFactItem) => (
              <tr key={item.metric_name}>
                <td style={{ fontWeight: 600 }} title={item.metric_label}>
                  {item.metric_label}
                </td>
                <td>{fmt.format(Math.round(item.plan_value))} {item.unit === '%' ? '%' : ''}</td>
                <td>{fmt.format(Math.round(item.fact_value))} {item.unit === '%' ? '%' : ''}</td>
                <td className={item.deviation_abs >= 0 ? styles.positive : styles.negative}>
                  {item.deviation_abs >= 0 ? '+' : ''}{fmt.format(Math.round(item.deviation_abs))}
                </td>
                <td className={item.deviation_pct >= 0 ? styles.positive : styles.negative}>
                  {item.deviation_pct >= 0 ? '+' : ''}{item.deviation_pct.toFixed(1)}%
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                  Нет данных плана
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}