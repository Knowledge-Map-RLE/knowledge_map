import { useCallback, useEffect, useState } from 'react';
import { fetchProviders, fetchProviderPrices } from '../../../../services/api/admin';
import type { AIProvider, PriceVersion } from '../../model';
import styles from '../../Admin.module.css';

interface PlanPricing {
  name: string;
  code: string;
  price: number;
  tokens: number;
}

const PLANS: PlanPricing[] = [
  { name: 'Free', code: 'FREE', price: 0, tokens: 0 },
  { name: '50M токенов', code: 'TOKENS_50M', price: 2000, tokens: 50_000_000 },
  { name: '200M токенов', code: 'TOKENS_200M', price: 8000, tokens: 200_000_000 },
];

const fmt = new Intl.NumberFormat('ru-RU');

export default function PricingPage() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [prices, setPrices] = useState<Record<string, PriceVersion[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const provs = await fetchProviders();
      setProviders(provs);
      const pricesMap: Record<string, PriceVersion[]> = {};
      await Promise.all(
        provs.map(async (p) => {
          try {
            pricesMap[p.uid] = await fetchProviderPrices(p.uid);
          } catch {
            pricesMap[p.uid] = [];
          }
        })
      );
      setPrices(pricesMap);
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
        <span className={styles.loadingText}>Загрузка тарифов...</span>
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
      <h1>Тарифы</h1>

      <div className={styles.card}>
        <h3>Планы пользователей</h3>
        <table className={styles.adminTable}>
          <thead>
            <tr>
              <th>План</th>
              <th>Код</th>
              <th>Цена</th>
              <th>Токены</th>
              <th>Цена за 1M токенов</th>
            </tr>
          </thead>
          <tbody>
            {PLANS.map((plan) => (
              <tr key={plan.code}>
                <td style={{ fontWeight: 600 }}>{plan.name}</td>
                <td>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: '0.75rem',
                    background: plan.code === 'FREE' ? '#374151' : '#1e3a5f',
                    color: plan.code === 'FREE' ? '#9ca3af' : '#60a5fa',
                  }}>
                    {plan.code}
                  </span>
                </td>
                <td>{plan.price > 0 ? `${fmt.format(plan.price)} ₽` : 'Бесплатно'}</td>
                <td>{plan.tokens > 0 ? fmt.format(plan.tokens) : '—'}</td>
                <td>
                  {plan.tokens > 0
                    ? `${(plan.price / (plan.tokens / 1_000_000)).toFixed(2)} ₽`
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {providers.length > 0 && (
        <div className={styles.card} style={{ marginTop: 16 }}>
          <h3>Активные цены провайдеров (AI Cost)</h3>
          <table className={styles.adminTable}>
            <thead>
              <tr>
                <th>Провайдер</th>
                <th>Модель</th>
                <th>Input ₽/1M</th>
                <th>Output ₽/1M</th>
                <th>С</th>
                <th>По</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) =>
                (prices[p.uid] ?? [])
                  .filter((pv) => pv.is_active)
                  .map((pv) => (
                    <tr key={pv.uid}>
                      <td>{p.display_name || p.name}</td>
                      <td>{pv.model}</td>
                      <td>{pv.input_price_per_million.toFixed(4)}</td>
                      <td>{pv.output_price_per_million.toFixed(4)}</td>
                      <td style={{ fontSize: '0.8rem', color: '#888' }}>
                        {pv.valid_from ? new Date(pv.valid_from).toLocaleDateString('ru-RU') : '—'}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: '#888' }}>
                        {pv.valid_to ? new Date(pv.valid_to).toLocaleDateString('ru-RU') : '—'}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
