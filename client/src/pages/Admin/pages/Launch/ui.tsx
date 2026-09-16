import { useCallback, useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchLaunchScenarios, calculateLaunch, saveLaunchParams } from '../../../../services/api/admin';
import type { LaunchScenario, LaunchCalculationResult } from '../../model';
import styles from '../../Admin.module.css';

const fmt = new Intl.NumberFormat('ru-RU');

interface LaunchForm {
  audience_size: string;
  conversion_rate_pct: string;
  avg_check_rubles: string;
  ai_cost_per_user_rubles: string;
  fixed_costs_rubles: string;
  cac_rubles: string;
}

const DEFAULT_FORM: LaunchForm = {
  audience_size: '100000',
  conversion_rate_pct: '5',
  avg_check_rubles: '3000',
  ai_cost_per_user_rubles: '500',
  fixed_costs_rubles: '50000',
  cac_rubles: '200',
};

export default function LaunchPage() {
  const [form, setForm] = useState<LaunchForm>(DEFAULT_FORM);
  const [scenarios, setScenarios] = useState<LaunchScenario[]>([]);
  const [result, setResult] = useState<LaunchCalculationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setScenarios(await fetchLaunchScenarios());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const parseAll = (): { valid: boolean; data?: { audience_size: number; conversion_rate: number; avg_check_rubles: number; ai_cost_per_user_rubles: number; fixed_costs_rubles: number; cac_rubles: number } } => {
    const audience_size = parseInt(form.audience_size, 10);
    const conversion_pct = parseFloat(form.conversion_rate_pct);
    const avg_check_rubles = parseFloat(form.avg_check_rubles);
    const ai_cost_per_user_rubles = parseFloat(form.ai_cost_per_user_rubles);
    const fixed_costs_rubles = parseFloat(form.fixed_costs_rubles);
    const cac_rubles = parseFloat(form.cac_rubles);
    if (!(audience_size > 0) || !(conversion_pct > 0) || !(avg_check_rubles > 0)) {
      return { valid: false };
    }
    return {
      valid: true,
      data: {
        audience_size,
        conversion_rate: conversion_pct / 100,
        avg_check_rubles,
        ai_cost_per_user_rubles,
        fixed_costs_rubles,
        cac_rubles,
      },
    };
  };

  const handleCalculate = async () => {
    const parsed = parseAll();
    if (!parsed.valid || !parsed.data) return;
    setCalculating(true);
    setError(null);
    try {
      setResult(await calculateLaunch(parsed.data));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка расчёта');
    } finally {
      setCalculating(false);
    }
  };

  const handleSaveParams = async () => {
    const parsed = parseAll();
    if (!parsed.valid || !parsed.data) return;
    setSaving(true);
    setError(null);
    try {
      await saveLaunchParams({ name: `Сценарий от ${new Date().toLocaleString('ru-RU')}`, params: parsed.data });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const setField = (key: keyof LaunchForm, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const resultChart = result
    ? [
        { name: 'Выручка', value: result.revenue_rubles },
        { name: 'AI Cost', value: result.ai_cost_rubles },
        { name: 'Расходы', value: result.expenses_rubles },
        { name: 'Прибыль', value: result.profit_rubles },
      ]
    : [];

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка сценариев...</span>
      </div>
    );
  }

  return (
    <div>
      <h1>Запуск</h1>

      {error && (
        <div style={{ padding: '8px 12px', background: '#7f1d1d', borderRadius: 4, marginBottom: 16, color: '#fca5a5', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      <div className={styles.card}>
        <h3>Параметры расчёта</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Аудитория</label>
            <input
              className={styles.adminInput}
              type="number"
              value={form.audience_size}
              onChange={(e) => setField('audience_size', e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Конверсия в покупку (%)</label>
            <input
              className={styles.adminInput}
              type="number"
              step="0.1"
              min="0.1"
              value={form.conversion_rate_pct}
              onChange={(e) => setField('conversion_rate_pct', e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Средний чек (₽)</label>
            <input
              className={styles.adminInput}
              type="number"
              value={form.avg_check_rubles}
              onChange={(e) => setField('avg_check_rubles', e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>AI Cost / покупатель (₽)</label>
            <input
              className={styles.adminInput}
              type="number"
              value={form.ai_cost_per_user_rubles}
              onChange={(e) => setField('ai_cost_per_user_rubles', e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Фикс. расходы (₽/мес)</label>
            <input
              className={styles.adminInput}
              type="number"
              value={form.fixed_costs_rubles}
              onChange={(e) => setField('fixed_costs_rubles', e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>CAC (₽)</label>
            <input
              className={styles.adminInput}
              type="number"
              value={form.cac_rubles}
              onChange={(e) => setField('cac_rubles', e.target.value)}
            />
          </div>
        </div>
        <div className={styles.formRow} style={{ marginTop: 16 }}>
          <button className={styles.adminBtn} onClick={handleCalculate} disabled={calculating}>
            {calculating ? 'Расчёт...' : 'Рассчитать'}
          </button>
          <button
            className={`${styles.adminBtn} ${styles.adminBtnSecondary}`}
            onClick={handleSaveParams}
            disabled={saving}
          >
            {saving ? 'Сохранение...' : 'Сохранить сценарий'}
          </button>
        </div>
      </div>

      {result && (
        <>
          <div className={styles.chartContainer} style={{ marginTop: 16 }}>
            <h3>Экономика запуска</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={resultChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2d37" />
                <XAxis dataKey="name" tick={{ fill: '#888', fontSize: 11 }} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1d27', border: '1px solid #2a2d37', borderRadius: 4 }}
                  formatter={(value: number) => `${fmt.format(Math.round(value))} ₽`}
                />
                <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={styles.card} style={{ marginTop: 16 }}>
            <table className={styles.adminTable}>
              <tbody>
                <tr>
                  <td>Аудитория</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(result.audience_size)}</td>
                  <td>Регистрации</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(result.registrations)}</td>
                  <td>Покупатели</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(result.buyers)}</td>
                  <td>Конверсия</td>
                  <td style={{ fontWeight: 600 }}>{(result.conversion_rate * 100).toFixed(1)}%</td>
                </tr>
                <tr>
                  <td>Выручка</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(Math.round(result.revenue_rubles))} ₽</td>
                  <td>AI Cost</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(Math.round(result.ai_cost_rubles))} ₽</td>
                  <td>Расходы</td>
                  <td style={{ fontWeight: 600 }}>{fmt.format(Math.round(result.expenses_rubles))} ₽</td>
                  <td>Прибыль</td>
                  <td className={result.profit_rubles >= 0 ? styles.positive : styles.negative} style={{ fontWeight: 600 }}>
                    {fmt.format(Math.round(result.profit_rubles))} ₽
                  </td>
                </tr>
                <tr>
                  <td colSpan={4}>Требуемый капитал</td>
                  <td colSpan={4} style={{ fontWeight: 600 }}>
                    {fmt.format(Math.round(result.required_capital_rubles))} ₽
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {scenarios.length > 0 && (
        <div className={styles.card} style={{ marginTop: 16 }}>
          <h3>Сохранённые сценарии</h3>
          <table className={styles.adminTable}>
            <thead>
              <tr>
                <th>Название</th>
                <th>Параметры</th>
                <th>Создан</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s: LaunchScenario) => (
                <tr key={s.uid}>
                  <td style={{ fontWeight: 600 }}>{s.name}</td>
                  <td style={{ fontSize: '0.75rem', color: '#888', whiteSpace: 'pre-wrap', maxWidth: 480 }}>
                    {Object.entries(s.params).map(([k, v]) => `${k}: ${typeof v === 'number' ? fmt.format(v) : String(v)}`).join(', ')}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: '#888' }}>
                    {s.created_at ? new Date(s.created_at).toLocaleDateString('ru-RU') : '—'}
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