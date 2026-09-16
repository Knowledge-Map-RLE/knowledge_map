import { useCallback, useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import KPICard from '../../components/KPICard';
import { fetchSalesOverview, fetchSalesByPackage } from '../../../../services/api/admin';
import type { SalesOverview, PackageSales } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');

export default function SalesPage() {
  const [overview, setOverview] = useState<SalesOverview | null>(null);
  const [packages, setPackages] = useState<PackageSales[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, pk] = await Promise.all([
        fetchSalesOverview(),
        fetchSalesByPackage(),
      ]);
      setOverview(ov);
      setPackages(pk);
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
        <span className={styles.loadingText}>Загрузка продаж...</span>
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
      <h1>Продажи</h1>

      {overview && (
        <div className={styles.kpiGrid}>
          <KPICard title="Всего продаж" value={overview.total_sales_count} tooltip="Количество продаж" color="#3b82f6" />
          <KPICard title="Выручка" value={overview.total_revenue_rubles} suffix=" ₽" color="#22c55e" />
          <KPICard title="Средний чек" value={overview.average_check_rubles} suffix=" ₽" tooltip="Выручка / Продажи" color="#f59e0b" />
          <KPICard title="Возвраты" value={overview.refunds_count} suffix=" шт" color="#ef4444" />
          <KPICard title="Сумма возвратов" value={overview.refunds_amount_rubles} suffix=" ₽" color="#ef4444" />
          <KPICard title="Чистая выручка" value={overview.net_revenue_rubles} suffix=" ₽" color="#22c55e" />
        </div>
      )}

      {packages.length > 0 && (
        <div className={styles.grid2}>
          <div className={styles.chartContainer}>
            <h3>Продажи по пакетам</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={packages.map((p) => ({ name: p.plan_code, revenue: p.revenue_rubles }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="name" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  formatter={(value: number) => fmt.format(Math.round(value))}
                />
                <Bar dataKey="revenue" name="Выручка" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.card}>
            <h3>Детали по пакетам</h3>
            <table className={styles.adminTable}>
              <thead>
                <tr>
                  <th>Пакет</th>
                  <th>Продажи</th>
                  <th>Выручка</th>
                </tr>
              </thead>
              <tbody>
                {packages.map((p: PackageSales) => (
                  <tr key={p.plan_code}>
                    <td>{p.plan_code}</td>
                    <td>{fmt.format(p.sale_count)}</td>
                    <td>{fmt.format(Math.round(p.revenue_rubles))} ₽</td>
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