import React, { useState, useEffect } from 'react';
import s from './ActionChainVisualization.module.css';

interface VerbData {
    verb: string;
    subject?: string;
    object?: string;
}

interface ActionChain {
    verb_data: VerbData[];
    relations: Array<{type: string; confidence: number}>;
    chain_length: number;
    avg_confidence: number;
}

export default function ActionChainVisualization() {
    const [chains, setChains] = useState<ActionChain[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadChains = async () => {
        setLoading(true);
        setError(null);

        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/action-chains/chains`);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setChains(data.chains || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadChains();
    }, []);

    const getSequenceTypeColor = (type: string) => {
        const colors: {[key: string]: string} = {
            'TEMPORAL_AFTER': '#3b82f6',
            'TEMPORAL_BEFORE': '#8b5cf6',
            'CAUSAL': '#ef4444',
            'PURPOSE': '#10b981',
            'RESULT': '#f59e0b',
            'COORDINATION': '#6b7280',
            'SEQUENTIAL': '#64748b',
        };
        return colors[type] || '#9ca3af';
    };

    const getSequenceTypeLabel = (type: string) => {
        const labels: {[key: string]: string} = {
            'TEMPORAL_AFTER': 'Затем',
            'TEMPORAL_BEFORE': 'До',
            'CAUSAL': 'Причина',
            'PURPOSE': 'Цель',
            'RESULT': 'Результат',
            'COORDINATION': 'Одновременно',
            'SEQUENTIAL': 'Последовательно',
        };
        return labels[type] || type;
    };

    return (
        <div className={s.container}>
            <div className={s.header}>
                <h4 className={s.title}>Визуализация цепочек</h4>
                <button
                    className={s.refreshButton}
                    onClick={loadChains}
                    disabled={loading}
                >
                    {loading ? 'Загрузка...' : 'Обновить'}
                </button>
            </div>

            {error && (
                <div className={s.error}>
                    <span>⚠</span> {error}
                </div>
            )}

            {chains.length === 0 && !loading && !error && (
                <div className={s.empty}>
                    Цепочки не найдены. Сначала постройте цепочки действий.
                </div>
            )}

            <div className={s.chainsList}>
                {chains.map((chain, idx) => (
                    <div key={idx} className={s.chainCard}>
                        <div className={s.chainHeader}>
                            <span className={s.chainLength}>Длина: {chain.chain_length}</span>
                            <span className={s.chainConfidence}>
                                Точность: {(chain.avg_confidence * 100).toFixed(0)}%
                            </span>
                        </div>

                        <div className={s.chainFlow}>
                            {chain.verb_data.map((verbData, verbIdx) => (
                                <React.Fragment key={verbIdx}>
                                    <div className={s.verbNodeWrapper}>
                                        {verbData.subject && (
                                            <div className={s.entityLabel}>
                                                <span className={s.entityRole}>Субъект:</span>
                                                <span className={s.entityText}>{verbData.subject}</span>
                                            </div>
                                        )}
                                        <div className={s.verbNode}>
                                            {verbData.verb}
                                        </div>
                                        {verbData.object && (
                                            <div className={s.entityLabel}>
                                                <span className={s.entityRole}>Объект:</span>
                                                <span className={s.entityText}>{verbData.object}</span>
                                            </div>
                                        )}
                                    </div>
                                    {verbIdx < chain.verb_data.length - 1 && chain.relations[verbIdx] && (
                                        <div
                                            className={s.relationArrow}
                                            style={{
                                                backgroundColor: getSequenceTypeColor(chain.relations[verbIdx].type)
                                            }}
                                        >
                                            <span className={s.relationLabel}>
                                                {getSequenceTypeLabel(chain.relations[verbIdx].type)}
                                            </span>
                                            <span className={s.arrowIcon}>→</span>
                                        </div>
                                    )}
                                </React.Fragment>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
