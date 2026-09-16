import { useCallback, useEffect, useState } from 'react';
import KPICard from '../../components/KPICard';
import { fetchStages, fetchCapitalCalculation } from '../../../../services/api/admin';
import type { StrategyStage, CapitalCalculation } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');

export default function StrategyPage() {
  const [stages, setStages] = useState<StrategyStage[]>([]);
  const [capital, setCapital] = useState<CapitalCalculation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, cap] = await Promise.all([
        fetchStages(),
        fetchCapitalCalculation(),
      ]);
      setStages(st);
      setCapital(cap);
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
        <span className={styles.loadingText}>Загрузка стратегии...</span>
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
      <h1>Стратегия</h1>

      {capital && (
        <div className={styles.kpiGrid}>
          <KPICard title="Минимум" value={capital.min_capital_rubles} suffix=" ₽" tooltip="Минимальный стартовый капитал" color="#ef4444" />
          <KPICard title="Базовый" value={capital.base_capital_rubles} suffix=" ₽" tooltip="Базовый капитал (+30%)" color="#f59e0b" />
          <KPICard title="Консервативный" value={capital.conservative_capital_rubles} suffix=" ₽" tooltip="Консервативный капитал (+50%)" color="#3b82f6" />
          <KPICard title="Фикс. расходы" value={capital.monthly_fixed_costs_rubles} suffix=" ₽/мес" color="#ef4444" />
          <KPICard title="Срок до Break-even" value={capital.months_to_breakeven} suffix=" мес" color="#22c55e" />
          <KPICard title="Макс. минус cashflow" value={capital.max_negative_cashflow_rubles} suffix=" ₽" color="#ef4444" />
        </div>
      )}

      {stages.length > 0 && (
        <div style={{ marginTop: 16, overflowX: 'auto' }}>
          <table className={styles.adminTable}>
            <thead>
              <tr>
                <th>Этап</th>
                <th>Пользователи</th>
                <th>Параметры</th>
              </tr>
            </thead>
            <tbody>
              {stages.map((s: StrategyStage) => (
                <tr key={s.uid}>
                  <td style={{ fontWeight: 600 }}>{s.stage_name}</td>
                  <td>{fmt.format(s.user_count)}</td>
                  <td style={{ fontSize: '0.75rem', color: '#888', whiteSpace: 'pre-wrap', maxWidth: 480 }}>
                    {Object.entries(s.data).map(([k, v]) => `${k}: ${typeof v === 'number' ? fmt.format(v) : String(v)}`).join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}