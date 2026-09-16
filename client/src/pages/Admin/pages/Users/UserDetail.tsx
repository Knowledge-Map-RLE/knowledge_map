import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FaArrowLeft } from 'react-icons/fa';
import KPICard from '../../components/KPICard';
import { fetchUserDetail, fetchUserUsage, fetchUserPayments } from '../../../../services/api/admin';
import type { UserDetail, UserUsageRecord, UserPayment } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');

export default function UserDetailPage() {
  const { uid } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [usage, setUsage] = useState<UserUsageRecord[]>([]);
  const [payments, setPayments] = useState<UserPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'usage' | 'payments'>('usage');

  const loadData = useCallback(async () => {
    if (!uid) return;
    setLoading(true);
    setError(null);
    try {
      const [detail, usageData, paymentsData] = await Promise.all([
        fetchUserDetail(uid),
        fetchUserUsage(uid),
        fetchUserPayments(uid),
      ]);
      setUser(detail);
      setUsage(usageData.usage);
      setPayments(paymentsData.payments);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [uid]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка профиля...</span>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className={styles.errorContainer}>
        <span className={styles.errorText}>{error || 'Пользователь не найден'}</span>
        <button className={styles.adminBtn} onClick={() => navigate('/admin/users')}>Назад</button>
      </div>
    );
  }

  return (
    <div>
      <a className={styles.backLink} onClick={() => navigate('/admin/users')} style={{ cursor: 'pointer' }}>
        <FaArrowLeft /> К списку пользователей
      </a>

      <h1>{user.uid}</h1>
      <div style={{ color: '#888', fontSize: '0.8rem', marginBottom: 16 }}>
        UID: {user.uid} · План: {user.plan_code} · Статус подписки: {user.subscription_status || '—'}
      </div>

      <div className={styles.kpiGrid}>
        <KPICard title="Токены" value={user.total_tokens} tooltip="Всего использовано токенов" />
        <KPICard
          title="AI Cost"
          value={user.ai_cost_rubles}
          suffix=" ₽"
          tooltip="Стоимость AI-вызовов"
          color="#f59e0b"
        />
        <KPICard
          title="Выручка"
          value={user.revenue_rubles}
          suffix=" ₽"
          tooltip="Общая выручка с пользователя"
          color="#3b82f6"
        />
        <KPICard
          title="Прибыль"
          value={user.profit_rubles}
          suffix=" ₽"
          color={user.profit_rubles >= 0 ? '#22c55e' : '#ef4444'}
        />
      </div>

      <div className={styles.tabsBar}>
        <button
          className={`${styles.tabBtn} ${activeTab === 'usage' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveTab('usage')}
        >
          История использования
        </button>
        <button
          className={`${styles.tabBtn} ${activeTab === 'payments' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveTab('payments')}
        >
          Платежи
        </button>
      </div>

      {activeTab === 'usage' && (
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.adminTable}>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Input</th>
                <th>Output</th>
                <th>Cache</th>
                <th>Всего</th>
                <th>Стоимость</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((r: UserUsageRecord, i: number) => (
                <tr key={`${r.created_at}-${i}`}>
                  <td>{r.created_at ? new Date(r.created_at).toLocaleString('ru-RU') : '—'}</td>
                  <td>{fmt.format(r.input_tokens)}</td>
                  <td>{fmt.format(r.output_tokens)}</td>
                  <td>{fmt.format(r.cached_tokens)}</td>
                  <td>{fmt.format(r.total_tokens)}</td>
                  <td>{fmt.format(Math.round(r.cost_rubles))} ₽</td>
                </tr>
              ))}
              {usage.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                    Нет данных об использовании
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'payments' && (
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.adminTable}>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Сумма</th>
                <th>Статус</th>
                <th>Пакет</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p: UserPayment) => (
                <tr key={p.uid}>
                  <td>{p.created_at ? new Date(p.created_at).toLocaleString('ru-RU') : '—'}</td>
                  <td>{fmt.format(Math.round(p.amount_rubles))} ₽</td>
                  <td>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: '0.75rem',
                      background: p.status === 'SUCCEEDED' ? '#166534' : p.status === 'REFUNDED' ? '#7f1d1d' : '#374151',
                      color: p.status === 'SUCCEEDED' ? '#22c55e' : p.status === 'REFUNDED' ? '#ef4444' : '#9ca3af',
                    }}>
                      {p.status || '—'}
                    </span>
                  </td>
                  <td>{p.plan_code || '—'}</td>
                </tr>
              ))}
              {payments.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                    Нет платежей
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}