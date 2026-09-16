import { useCallback, useEffect, useState } from 'react';
import { fetchFinancialPlan, saveFinancialPlan } from '../../../../services/api/admin';
import styles from '../../Admin.module.css';

const PLAN_FIELDS: { key: string; label: string; hint: string }[] = [
  { key: 'target_users', label: 'Целевое кол-во пользователей', hint: 'Месячная цель по регистрации' },
  { key: 'target_paying_users', label: 'Целевое кол-во платящих', hint: 'Месячная цель по платящим' },
  { key: 'avg_tokens_per_user', label: 'Средние токены на пользователя', hint: 'Input + Output' },
  { key: 'price_50m', label: 'Цена пакета 50M (₽)', hint: 'Текущая цена' },
  { key: 'price_200m', label: 'Цена пакета 200M (₽)', hint: 'Текущая цена' },
  { key: 'ai_cost_per_1m_tokens', label: 'AI Cost за 1M токенов (₽)', hint: 'Средняя стоимость' },
  { key: 'infra_cost_monthly', label: 'Инфраструктура (₽/мес)', hint: 'Серверы, S3, CDN' },
  { key: 'advertising_budget', label: 'Бюджет рекламы (₽/мес)', hint: 'Плановый расход' },
  { key: 'tax_rate', label: 'Ставка налога (%)', hint: 'НДС + налог на прибыль' },
  { key: 'acquiring_rate', label: 'Ставка эквайринга (%)', hint: 'Комиссия платёжной системы' },
  { key: 'conversion_reg_to_paying', label: 'Конверсия регистрация → платящий (%)', hint: 'Целевая' },
  { key: 'monthly_churn_rate', label: 'Отток пользователей (%/мес)', hint: 'Потеря в месяц' },
];

export default function PlanEditor() {
  const [planName, setPlanName] = useState('');
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await fetchFinancialPlan();
      setPlanName(p.name);
      const mapped: Record<string, string> = {};
      for (const field of PLAN_FIELDS) {
        mapped[field.key] = String(p.data[field.key] ?? '');
      }
      setFormData(mapped);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleChange = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const numericData: Record<string, number> = {};
      for (const field of PLAN_FIELDS) {
        const val = parseFloat(formData[field.key]);
        numericData[field.key] = isNaN(val) ? 0 : val;
      }
      await saveFinancialPlan({ name: planName, data: numericData });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка финансового плана...</span>
      </div>
    );
  }

  return (
    <div>
      <h2>Редактор финансового плана</h2>

      {error && (
        <div style={{ padding: '8px 12px', background: '#7f1d1d', borderRadius: 4, marginBottom: 16, color: '#fca5a5', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: '8px 12px', background: '#166534', borderRadius: 4, marginBottom: 16, color: '#86efac', fontSize: '0.85rem' }}>
          План сохранён
        </div>
      )}

      <div className={styles.card}>
        <div className={styles.formGroup} style={{ marginBottom: 16 }}>
          <label className={styles.formLabel}>Название плана</label>
          <input
            className={styles.adminInput}
            value={planName}
            onChange={(e) => setPlanName(e.target.value)}
            placeholder="Например: План Q1 2026"
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {PLAN_FIELDS.map((field) => (
            <div key={field.key} className={styles.formGroup}>
              <label className={styles.formLabel}>{field.label}</label>
              <input
                className={styles.adminInput}
                type="number"
                value={formData[field.key] ?? ''}
                onChange={(e) => handleChange(field.key, e.target.value)}
                placeholder={field.hint}
                step="any"
              />
              <span style={{ fontSize: '0.7rem', color: '#666' }}>{field.hint}</span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 16 }}>
          <button className={styles.adminBtn} onClick={handleSave} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить план'}
          </button>
        </div>
      </div>
    </div>
  );
}
