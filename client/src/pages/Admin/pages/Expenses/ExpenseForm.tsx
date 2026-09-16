import { useState } from 'react';
import styles from '../../Admin.module.css';

interface ExpenseFormProps {
  onSubmit: (data: {
    category: string;
    description: string;
    amount_kopecks: number;
    period_start: string;
    period_end: string;
    is_fixed: boolean;
    is_recurring: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}

const CATEGORIES = [
  { value: 'infrastructure', label: 'Инфраструктура' },
  { value: 'ai_tokens', label: 'AI токены' },
  { value: 'acquiring', label: 'Эквайринг' },
  { value: 'advertising', label: 'Реклама' },
  { value: 'tax', label: 'Налоги' },
  { value: 'other', label: 'Прочее' },
];

export default function ExpenseForm({ onSubmit, onCancel }: ExpenseFormProps) {
  const [category, setCategory] = useState(CATEGORIES[0].value);
  const [description, setDescription] = useState('');
  const [amountRubles, setAmountRubles] = useState('');
  const [periodStart, setPeriodStart] = useState(() => new Date().toISOString().slice(0, 10));
  const [periodEnd, setPeriodEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [isFixed, setIsFixed] = useState(false);
  const [isRecurring, setIsRecurring] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const rubles = parseFloat(amountRubles);
    if (!description || isNaN(rubles) || rubles < 0) return;
    setSubmitting(true);
    try {
      await onSubmit({
        category,
        description,
        amount_kopecks: Math.round(rubles * 100),
        period_start: periodStart,
        period_end: periodEnd,
        is_fixed: isFixed,
        is_recurring: isRecurring,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className={styles.adminForm} onSubmit={handleSubmit}>
      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Категория</label>
        <select
          className={styles.adminSelect}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Описание</label>
        <input
          className={styles.adminInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Описание расхода"
          required
        />
      </div>

      <div className={styles.formGroup}>
        <label className={styles.formLabel}>Сумма (₽)</label>
        <input
          className={styles.adminInput}
          type="number"
          value={amountRubles}
          onChange={(e) => setAmountRubles(e.target.value)}
          placeholder="0"
          min="0"
          step="0.01"
          required
        />
      </div>

      <div className={styles.formRow}>
        <div className={styles.formGroup} style={{ flex: 1 }}>
          <label className={styles.formLabel}>Начало периода</label>
          <input
            className={styles.adminInput}
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
          />
        </div>
        <div className={styles.formGroup} style={{ flex: 1 }}>
          <label className={styles.formLabel}>Конец периода</label>
          <input
            className={styles.adminInput}
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
          />
        </div>
      </div>

      <div className={styles.formRow}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: '0.875rem' }}>
          <input type="checkbox" checked={isFixed} onChange={(e) => setIsFixed(e.target.checked)} />
          Фиксированный
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: '0.875rem' }}>
          <input type="checkbox" checked={isRecurring} onChange={(e) => setIsRecurring(e.target.checked)} />
          Повторяющийся
        </label>
      </div>

      <div className={styles.formRow}>
        <button className={styles.adminBtn} type="submit" disabled={submitting}>
          {submitting ? 'Сохранение...' : 'Сохранить'}
        </button>
        <button className={`${styles.adminBtn} ${styles.adminBtnSecondary}`} type="button" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  );
}