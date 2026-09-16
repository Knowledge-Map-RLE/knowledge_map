import { useCallback, useEffect, useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import KPICard from '../../components/KPICard';
import { fetchExpenses, fetchExpenseSummary, createExpense, deleteExpense } from '../../../../services/api/admin';
import type { Expense, ExpenseSummary } from '../../model';
import ExpenseForm from './ExpenseForm';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');
const CATEGORY_LABELS: Record<string, string> = {
  infrastructure: 'Инфраструктура',
  ai_tokens: 'AI токены',
  acquiring: 'Эквайринг',
  advertising: 'Реклама',
  tax: 'Налоги',
  other: 'Прочее',
};

export default function ExpensesPage() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [summary, setSummary] = useState<ExpenseSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [exp, sum] = await Promise.all([
        fetchExpenses(),
        fetchExpenseSummary(),
      ]);
      setExpenses(exp);
      setSummary(sum);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreate = useCallback(async (data: Parameters<typeof createExpense>[0]) => {
    await createExpense(data);
    setShowForm(false);
    await loadData();
  }, [loadData]);

  const handleDelete = useCallback(async (uid: string) => {
    if (!confirm('Удалить расход?')) return;
    await deleteExpense(uid);
    await loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка расходов...</span>
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

  const summaryItems: { title: string; value: number }[] = summary
    ? [
        { title: 'Всего', value: summary.total_rubles },
        { title: 'Инфраструктура', value: summary.infrastructure_rubles },
        { title: 'AI токены', value: summary.ai_tokens_rubles },
        { title: 'Эквайринг', value: summary.acquiring_rubles },
        { title: 'Реклама', value: summary.advertising_rubles },
        { title: 'Налоги', value: summary.tax_rubles },
        { title: 'Прочее', value: summary.other_rubles },
        { title: 'Фиксированные', value: summary.fixed_rubles },
        { title: 'Переменные', value: summary.variable_rubles },
      ]
    : [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Расходы</h1>
        <button className={styles.adminBtn} onClick={() => setShowForm(true)}>
          <FaPlus style={{ marginRight: 6 }} /> Добавить
        </button>
      </div>

      {summaryItems.length > 0 && (
        <div className={styles.kpiGrid}>
          {summaryItems.map((item) => (
            <KPICard key={item.title} title={item.title} value={item.value} suffix=" ₽" />
          ))}
        </div>
      )}

      <div style={{ overflowX: 'auto' }}>
        <table className={styles.adminTable}>
          <thead>
            <tr>
              <th>Категория</th>
              <th>Описание</th>
              <th>Сумма</th>
              <th>Период</th>
              <th>Фикс.</th>
              <th>Повт.</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((e: Expense) => (
              <tr key={e.uid}>
                <td>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: '0.75rem',
                    background: '#374151',
                    color: '#d1d5db',
                  }}>
                    {CATEGORY_LABELS[e.category] ?? e.category}
                  </span>
                </td>
                <td>{e.description}</td>
                <td style={{ fontWeight: 600 }}>{fmt.format(Math.round(e.amount_rubles))} ₽</td>
                <td style={{ fontSize: '0.8rem', color: '#888' }}>
                  {new Date(e.period_start).toLocaleDateString('ru-RU')} — {new Date(e.period_end).toLocaleDateString('ru-RU')}
                </td>
                <td>{e.is_fixed ? '✓' : '—'}</td>
                <td>{e.is_recurring ? '✓' : '—'}</td>
                <td>
                  <button
                    className={`${styles.adminBtn} ${styles.adminBtnDanger}`}
                    style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                    onClick={() => handleDelete(e.uid)}
                  >
                    <FaTrash />
                  </button>
                </td>
              </tr>
            ))}
            {expenses.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#666' }}>
                  Нет расходов
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className={styles.modalOverlay} onClick={() => setShowForm(false)}>
          <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <h3>Новый расход</h3>
            <ExpenseForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />
          </div>
        </div>
      )}
    </div>
  );
}