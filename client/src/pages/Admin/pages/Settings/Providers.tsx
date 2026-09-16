import { useCallback, useEffect, useState } from 'react';
import { FaPlus, FaEdit } from 'react-icons/fa';
import { fetchProviders, createProvider, updateProvider, fetchProviderPrices, createPriceVersion } from '../../../../services/api/admin';
import type { AIProvider, PriceVersion } from '../../model';
import styles from '../../Admin.module.css';

export default function ProvidersPage() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [prices, setPrices] = useState<Record<string, PriceVersion[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<AIProvider | null>(null);
  const [showPriceForm, setShowPriceForm] = useState<string | null>(null);

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

  const handleCreateProvider = async (data: { name: string; display_name: string; base_url?: string }) => {
    await createProvider(data);
    setShowForm(false);
    await loadData();
  };

  const handleToggleActive = async (provider: AIProvider) => {
    await updateProvider(provider.uid, { is_active: !provider.is_active });
    await loadData();
  };

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
        <span className={styles.loadingText}>Загрузка провайдеров...</span>
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>AI Провайдеры</h1>
        <button className={styles.adminBtn} onClick={() => { setEditingProvider(null); setShowForm(true); }}>
          <FaPlus style={{ marginRight: 6 }} /> Добавить
        </button>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className={styles.adminTable}>
          <thead>
            <tr>
              <th>Название</th>
              <th>Статус</th>
              <th>API Base</th>
              <th>Версии цен</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p: AIProvider) => (
              <tr key={p.uid}>
                <td style={{ fontWeight: 600 }}>{p.display_name || p.name}</td>
                <td>
                  <button
                    onClick={() => handleToggleActive(p)}
                    style={{
                      padding: '2px 10px',
                      borderRadius: 4,
                      fontSize: '0.75rem',
                      border: 'none',
                      cursor: 'pointer',
                      background: p.is_active ? '#166534' : '#7f1d1d',
                      color: p.is_active ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {p.is_active ? 'Активен' : 'Отключён'}
                  </button>
                </td>
                <td style={{ fontSize: '0.8rem', color: '#888' }}>{p.base_url || '—'}</td>
                <td>{(prices[p.uid] ?? []).length}</td>
                <td>
                  <button
                    className={styles.adminBtn}
                    style={{ padding: '4px 8px', fontSize: '0.75rem', marginRight: 4 }}
                    onClick={() => { setEditingProvider(p); setShowForm(true); }}
                  >
                    <FaEdit />
                  </button>
                  <button
                    className={`${styles.adminBtn} ${styles.adminBtnSecondary}`}
                    style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                    onClick={() => setShowPriceForm(showPriceForm === p.uid ? null : p.uid)}
                  >
                    + Цена
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {providers.map((p) => (
        prices[p.uid] && prices[p.uid].length > 0 && (
          <div key={`prices-${p.uid}`} className={styles.card} style={{ marginTop: 12 }}>
            <h3>{p.display_name || p.name} — Версии цен</h3>
            <table className={styles.adminTable}>
              <thead>
                <tr>
                  <th>Модель</th>
                  <th>Input ₽/1M</th>
                  <th>Output ₽/1M</th>
                  <th>Cache ₽/1M</th>
                  <th>Действует с</th>
                  <th>Действует до</th>
                  <th>Активна</th>
                </tr>
              </thead>
              <tbody>
                {prices[p.uid].map((pv: PriceVersion) => (
                  <tr key={pv.uid}>
                    <td>{pv.model}</td>
                    <td>{pv.input_price_per_million.toFixed(4)}</td>
                    <td>{pv.output_price_per_million.toFixed(4)}</td>
                    <td>{pv.cache_input_price_per_million != null ? pv.cache_input_price_per_million.toFixed(4) : '—'}</td>
                    <td>{pv.valid_from ? new Date(pv.valid_from).toLocaleDateString('ru-RU') : '—'}</td>
                    <td>{pv.valid_to ? new Date(pv.valid_to).toLocaleDateString('ru-RU') : '—'}</td>
                    <td>{pv.is_active ? '✓' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ))}

      {showForm && (
        <ProviderForm
          provider={editingProvider}
          onSubmit={handleCreateProvider}
          onCancel={() => { setShowForm(false); setEditingProvider(null); }}
        />
      )}

      {showPriceForm && (
        <PriceVersionForm
          onSubmit={async (data) => {
            await createPriceVersion(showPriceForm, data);
            setShowPriceForm(null);
            await loadData();
          }}
          onCancel={() => setShowPriceForm(null)}
        />
      )}
    </div>
  );
}

function ProviderForm({
  provider,
  onSubmit,
  onCancel,
}: {
  provider: AIProvider | null;
  onSubmit: (data: { name: string; display_name: string; base_url?: string }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(provider?.name ?? '');
  const [displayName, setDisplayName] = useState(provider?.display_name ?? '');
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? '');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit({ name, display_name: displayName || name, base_url: baseUrl });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <h3>{provider ? 'Редактировать провайдера' : 'Новый провайдер'}</h3>
        <form className={styles.adminForm} onSubmit={handleSubmit}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Название (код)</label>
            <input className={styles.adminInput} value={name} onChange={(e) => setName(e.target.value)} required disabled={!!provider} />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Отображаемое имя</label>
            <input className={styles.adminInput} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>API Base URL</label>
            <input className={styles.adminInput} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com" />
          </div>
          <div className={styles.formRow}>
            <button className={styles.adminBtn} type="submit" disabled={submitting}>
              {submitting ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button className={`${styles.adminBtn} ${styles.adminBtnSecondary}`} type="button" onClick={onCancel}>Отмена</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PriceVersionForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (data: {
    model: string;
    input_price_per_million: number;
    output_price_per_million: number;
    cache_input_price_per_million?: number;
    is_active?: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [model, setModel] = useState('');
  const [priceInput, setPriceInput] = useState('');
  const [priceOutput, setPriceOutput] = useState('');
  const [cacheInput, setCacheInput] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit({
        model,
        input_price_per_million: parseFloat(priceInput) || 0,
        output_price_per_million: parseFloat(priceOutput) || 0,
        cache_input_price_per_million: cacheInput ? parseFloat(cacheInput) || 0 : undefined,
        is_active: true,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <h3>Новая версия цен</h3>
        <form className={styles.adminForm} onSubmit={handleSubmit}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Модель</label>
            <input className={styles.adminInput} value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat" required />
          </div>
          <div className={styles.formRow}>
            <div className={styles.formGroup} style={{ flex: 1 }}>
              <label className={styles.formLabel}>Input ₽/1M</label>
              <input className={styles.adminInput} type="number" step="any" value={priceInput} onChange={(e) => setPriceInput(e.target.value)} required />
            </div>
            <div className={styles.formGroup} style={{ flex: 1 }}>
              <label className={styles.formLabel}>Output ₽/1M</label>
              <input className={styles.adminInput} type="number" step="any" value={priceOutput} onChange={(e) => setPriceOutput(e.target.value)} required />
            </div>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Cache Input ₽/1M (опционально)</label>
            <input className={styles.adminInput} type="number" step="any" value={cacheInput} onChange={(e) => setCacheInput(e.target.value)} placeholder="Например 1.15" />
          </div>
          <div className={styles.formRow}>
            <button className={styles.adminBtn} type="submit" disabled={submitting}>
              {submitting ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button className={`${styles.adminBtn} ${styles.adminBtnSecondary}`} type="button" onClick={onCancel}>Отмена</button>
          </div>
        </form>
      </div>
    </div>
  );
}