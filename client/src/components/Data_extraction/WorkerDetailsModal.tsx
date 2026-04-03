import React, { useEffect, useState, useCallback } from 'react';

const WORKER_STATUS_URL = '/api/worker';

interface ArticleProgress {
    pmcid: string;
    doc_id: string | null;
    state: string;
    retry_count: number;
    error_msg: string | null;
    updated_at: string | null;
    done_at: string | null;
}

interface DetailsResponse {
    articles: ArticleProgress[];
    total: number;
}

interface StatusSummary {
    total: number;
    done: number;
    failed: number;
    in_progress: number;
    pending: number;
    percent: number;
    status: string;
    started_at: string | null;
}

const STATE_LABELS: Record<string, string> = {
    pending: 'Ожидает',
    ingesting: 'Загрузка',
    awaiting_markdown: 'Конвертация',
    annotating: 'Аннотирование',
    extracting: 'Извлечение действий',
    reviewing: 'Авто-ревью',
    done: 'Готово',
    failed: 'Ошибка',
};

const STATE_COLORS: Record<string, string> = {
    done: '#16a34a',
    failed: '#dc2626',
    ingesting: '#d97706',
    awaiting_markdown: '#d97706',
    annotating: '#2563eb',
    extracting: '#7c3aed',
    reviewing: '#0891b2',
    pending: '#9ca3af',
};

interface Props {
    onClose: () => void;
}

const WorkerDetailsModal: React.FC<Props> = ({ onClose }) => {
    const [summary, setSummary] = useState<StatusSummary | null>(null);
    const [articles, setArticles] = useState<ArticleProgress[]>([]);
    const [logs, setLogs] = useState<string[]>([]);
    const [search, setSearch] = useState('');
    const [showLogs, setShowLogs] = useState(false);

    const fetchData = useCallback(async () => {
        try {
            const [sumRes, detRes, logRes] = await Promise.all([
                fetch(`${WORKER_STATUS_URL}/status`),
                fetch(`${WORKER_STATUS_URL}/status/details?limit=500`),
                fetch(`${WORKER_STATUS_URL}/status/logs?n=100`),
            ]);
            if (sumRes.ok) setSummary(await sumRes.json());
            if (detRes.ok) {
                const d: DetailsResponse = await detRes.json();
                setArticles(d.articles);
            }
            if (logRes.ok) {
                const l = await logRes.json();
                setLogs(l.logs || []);
            }
        } catch {
            // worker not running
        }
    }, []);

    useEffect(() => {
        fetchData();
        const id = setInterval(fetchData, 5000);
        return () => clearInterval(id);
    }, [fetchData]);

    const filtered = search.length >= 2
        ? articles.filter(a =>
            a.pmcid.toLowerCase().includes(search.toLowerCase()) ||
            (a.doc_id || '').toLowerCase().includes(search.toLowerCase()) ||
            (a.error_msg || '').toLowerCase().includes(search.toLowerCase())
        )
        : articles;

    return (
        <div
            style={{
                position: 'fixed', inset: 0, zIndex: 9999,
                background: 'rgba(0,0,0,0.5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onClick={e => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div style={{
                background: '#fff', borderRadius: 10, width: 780, maxHeight: '88vh',
                display: 'flex', flexDirection: 'column', boxShadow: '0 8px 40px rgba(0,0,0,0.25)',
                overflow: 'hidden',
            }}>
                {/* Header */}
                <div style={{
                    padding: '14px 20px', borderBottom: '1px solid #e5e7eb',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}>
                    <div>
                        <span style={{ fontWeight: 700, fontSize: 15 }}>Пакетная загрузка статей</span>
                        {summary && (
                            <span style={{ marginLeft: 10, fontSize: 12, color: '#6b7280' }}>
                                Запрос: aging · Всего: {summary.total}
                            </span>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#6b7280', lineHeight: 1 }}
                    >×</button>
                </div>

                {/* Summary stats */}
                {summary && (
                    <div style={{
                        display: 'flex', gap: 16, padding: '12px 20px',
                        borderBottom: '1px solid #f3f4f6', flexWrap: 'wrap',
                    }}>
                        <Stat label="Готово" value={summary.done} color="#16a34a" />
                        <Stat label="В работе" value={summary.in_progress} color="#d97706" />
                        <Stat label="Ожидает" value={summary.pending} color="#9ca3af" />
                        <Stat label="Ошибок" value={summary.failed} color="#dc2626" />
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{
                                flex: 1, height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden',
                            }}>
                                <div style={{
                                    height: '100%', width: `${summary.percent}%`,
                                    background: '#2563eb', borderRadius: 4, transition: 'width 0.5s',
                                }} />
                            </div>
                            <span style={{ fontSize: 13, fontWeight: 600, color: '#2563eb', minWidth: 36 }}>
                                {summary.percent}%
                            </span>
                        </div>
                    </div>
                )}

                {/* Search */}
                <div style={{ padding: '8px 20px', borderBottom: '1px solid #f3f4f6' }}>
                    <input
                        type="text"
                        placeholder="Поиск по PMCID или ошибке..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        style={{
                            width: '100%', padding: '5px 10px', border: '1px solid #d1d5db',
                            borderRadius: 6, fontSize: 12, outline: 'none',
                        }}
                    />
                </div>

                {/* Article table */}
                <div style={{ flex: 1, overflow: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                                <th style={thStyle}>PMCID</th>
                                <th style={thStyle}>Статус</th>
                                <th style={thStyle}>Попытки</th>
                                <th style={thStyle}>Обновлено</th>
                                <th style={thStyle}>Ошибка</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map(a => (
                                <tr key={a.pmcid} style={{ borderBottom: '1px solid #f3f4f6' }}>
                                    <td style={tdStyle}>
                                        <a
                                            href={`https://www.ncbi.nlm.nih.gov/pmc/articles/${a.pmcid}/`}
                                            target="_blank" rel="noreferrer"
                                            style={{ color: '#2563eb', textDecoration: 'none' }}
                                        >
                                            {a.pmcid}
                                        </a>
                                    </td>
                                    <td style={tdStyle}>
                                        <span style={{
                                            color: STATE_COLORS[a.state] || '#6b7280',
                                            fontWeight: a.state === 'done' || a.state === 'failed' ? 600 : 400,
                                        }}>
                                            {STATE_LABELS[a.state] || a.state}
                                        </span>
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'center', color: a.retry_count > 0 ? '#d97706' : '#9ca3af' }}>
                                        {a.retry_count}
                                    </td>
                                    <td style={{ ...tdStyle, color: '#9ca3af' }}>
                                        {a.updated_at ? new Date(a.updated_at).toLocaleTimeString() : '—'}
                                    </td>
                                    <td style={{ ...tdStyle, color: '#dc2626', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                        title={a.error_msg || ''}>
                                        {a.error_msg || ''}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {filtered.length === 0 && (
                        <p style={{ textAlign: 'center', color: '#9ca3af', padding: 20, fontSize: 12 }}>
                            Нет данных
                        </p>
                    )}
                </div>

                {/* Logs section */}
                <div style={{ borderTop: '1px solid #e5e7eb' }}>
                    <button
                        onClick={() => setShowLogs(v => !v)}
                        style={{
                            width: '100%', padding: '8px 20px', background: '#f9fafb',
                            border: 'none', cursor: 'pointer', textAlign: 'left',
                            fontSize: 12, color: '#6b7280', fontWeight: 500,
                        }}
                    >
                        {showLogs ? '▼' : '▶'} Логи ({logs.length})
                    </button>
                    {showLogs && (
                        <div style={{
                            maxHeight: 160, overflow: 'auto', background: '#1e1e1e',
                            padding: '8px 12px', fontFamily: 'monospace', fontSize: 11,
                        }}>
                            {logs.slice().reverse().map((line, i) => (
                                <div key={i} style={{ color: '#d4d4d4', marginBottom: 2 }}>{line}</div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const thStyle: React.CSSProperties = {
    padding: '6px 12px', textAlign: 'left', fontWeight: 600,
    color: '#6b7280', fontSize: 11, whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
    padding: '5px 12px', verticalAlign: 'middle',
};

const Stat: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
    <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
        <div style={{ fontSize: 11, color: '#6b7280' }}>{label}</div>
    </div>
);

export default WorkerDetailsModal;
