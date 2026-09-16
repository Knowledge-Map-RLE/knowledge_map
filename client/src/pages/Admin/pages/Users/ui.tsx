import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaSearch } from 'react-icons/fa';
import { fetchUsers } from '../../../../services/api/admin';
import type { AdminUserSummary, PaginatedUsers } from '../../model';
import styles from '../../Admin.module.css';

const PAGE_SIZE = 20;

const fmt = new Intl.NumberFormat('ru-RU');

export default function UsersPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<PaginatedUsers | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [planFilter, setPlanFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState<string>('');
  const [page, setPage] = useState(1);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchUsers({
        page,
        page_size: PAGE_SIZE,
        search: search || undefined,
        plan_code: planFilter || undefined,
        is_active: activeFilter === 'true' ? true : activeFilter === 'false' ? false : undefined,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [page, search, planFilter, activeFilter]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleSearchSubmit = () => {
    setPage(1);
    loadUsers();
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  if (loading && !data) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка пользователей...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorContainer}>
        <span className={styles.errorText}>{error}</span>
        <button className={styles.adminBtn} onClick={loadUsers}>Повторить</button>
      </div>
    );
  }

  return (
    <div>
      <h1>Пользователи</h1>

      <div className={styles.filtersBar}>
        <div style={{ position: 'relative', flex: '0 0 300px' }}>
          <FaSearch
            style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#666', fontSize: 14 }}
          />
          <input
            className={styles.adminInput}
            style={{ paddingLeft: 32, width: '100%' }}
            placeholder="Поиск по логину или UID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()}
          />
        </div>
        <select
          className={styles.adminSelect}
          value={planFilter}
          onChange={(e) => { setPlanFilter(e.target.value); setPage(1); }}
        >
          <option value="">Все планы</option>
          <option value="FREE">FREE</option>
          <option value="TOKENS_50M">TOKENS_50M</option>
          <option value="TOKENS_200M">TOKENS_200M</option>
        </select>
        <select
          className={styles.adminSelect}
          value={activeFilter}
          onChange={(e) => { setActiveFilter(e.target.value); setPage(1); }}
        >
          <option value="">Все статусы</option>
          <option value="true">Активные</option>
          <option value="false">Неактивные</option>
        </select>
      </div>

      {data && (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table className={`${styles.adminTable} ${styles.adminTableClickable}`}>
              <thead>
                <tr>
                  <th>UID</th>
                  <th>План</th>
                  <th>Статус подписки</th>
                  <th>Токены</th>
                  <th>AI Cost</th>
                  <th>Выручка</th>
                  <th>Прибыль</th>
                  <th>Последний запрос</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u: AdminUserSummary) => (
                  <tr key={u.uid} onClick={() => navigate(`/admin/users/${u.uid}`)}>
                    <td style={{ fontSize: '0.75rem', color: '#888' }}>{u.uid.slice(0, 8)}...</td>
                    <td>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: '0.75rem',
                        background: u.plan_code === 'FREE' ? '#374151' : '#1e3a5f',
                        color: u.plan_code === 'FREE' ? '#9ca3af' : '#60a5fa',
                      }}>
                        {u.plan_code}
                      </span>
                    </td>
                    <td>{u.subscription_status || '—'}</td>
                    <td>{fmt.format(u.total_tokens)}</td>
                    <td>{fmt.format(Math.round(u.ai_cost_rubles))} ₽</td>
                    <td>{fmt.format(Math.round(u.total_payments_rubles))} ₽</td>
                    <td className={(u.total_payments_rubles - u.ai_cost_rubles) >= 0 ? styles.positive : styles.negative}>
                      {fmt.format(Math.round(u.total_payments_rubles - u.ai_cost_rubles))} ₽
                    </td>
                    <td style={{ color: '#888', fontSize: '0.8rem' }}>
                      {u.last_request ? new Date(u.last_request).toLocaleDateString('ru-RU') : '—'}
                    </td>
                  </tr>
                ))}
                {data.users.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                      Нет пользователей
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button
                className={`${styles.pageBtn} ${page <= 1 ? styles.pageBtnDisabled : ''}`}
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ← Назад
              </button>
              <span style={{ color: '#888', fontSize: '0.8rem' }}>
                {page} / {totalPages}
              </span>
              <button
                className={`${styles.pageBtn} ${page >= totalPages ? styles.pageBtnDisabled : ''}`}
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
