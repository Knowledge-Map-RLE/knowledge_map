import React, { useState } from 'react';
import s from './ActionChainBuilder.module.css';
import ActionChainVisualization from './ActionChainVisualization';

interface ActionChainStatistics {
    total_verbs: number;
    action_sequences: number;
    entity_links: number;
    total_sequences: number;
    sequence_types: Array<{type: string; count: number}>;
    avg_confidence: number;
}

interface ProgressUpdate {
    stage: string;
    message: string;
    processed?: number;
    total?: number;
    percentage?: number;
    sequences_found?: number;
    total_verbs?: number;
    statistics?: ActionChainStatistics;
}

export default function ActionChainBuilder() {
    const [isBuilding, setIsBuilding] = useState(false);
    const [progress, setProgress] = useState<ProgressUpdate | null>(null);
    const [statistics, setStatistics] = useState<ActionChainStatistics | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleClearChains = async () => {
        if (!window.confirm('Вы уверены, что хотите удалить все цепочки действий?')) {
            return;
        }

        setError(null);
        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/action-chains/clear`, {
                method: 'DELETE',
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            setStatistics(null);
            setProgress(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        }
    };

    const handleBuildChains = async () => {
        setIsBuilding(true);
        setError(null);
        setProgress(null);

        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/action-chains/build`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    clear_existing: false  // Don't clear - update instead
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                throw new Error('No response body');
            }

            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    break;
                }

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.substring(6));

                        if (data.stage === 'error') {
                            setError(data.message);
                            setIsBuilding(false);
                            return;
                        }

                        setProgress(data);

                        if (data.stage === 'complete' && data.statistics) {
                            setStatistics(data.statistics);
                        }
                    }
                }
            }

        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setIsBuilding(false);
        }
    };

    const handleLoadStatistics = async () => {
        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/action-chains/statistics`);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setStatistics(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        }
    };

    const getStageLabel = (stage: string) => {
        switch (stage) {
            case 'cleared':
                return 'Очищены существующие цепочки';
            case 'extracting_verbs':
                return 'Извлечение глаголов...';
            case 'extracted_verbs':
                return 'Глаголы извлечены';
            case 'analyzing_pairs':
                return 'Анализ связей между глаголами...';
            case 'creating_relationships':
                return 'Создание связей в базе данных...';
            case 'linking_entities':
                return 'Связывание одинаковых объектов...';
            case 'complete':
                return 'Готово!';
            default:
                return stage;
        }
    };

    return (
        <div className={s.container}>
            <div className={s.header}>
                <h3 className={s.title}>Цепочки действий</h3>
                <div className={s.actions}>
                    <button
                        className={s.button}
                        onClick={handleLoadStatistics}
                        disabled={isBuilding}
                    >
                        Обновить статистику
                    </button>
                    <button
                        className={`${s.button} ${s.dangerButton}`}
                        onClick={handleClearChains}
                        disabled={isBuilding}
                    >
                        Удалить цепочки
                    </button>
                    <button
                        className={`${s.button} ${s.primaryButton}`}
                        onClick={handleBuildChains}
                        disabled={isBuilding}
                    >
                        {isBuilding ? 'Построение...' : 'Построить цепочки'}
                    </button>
                </div>
            </div>

            {error && (
                <div className={s.error}>
                    <span className={s.errorIcon}>⚠</span>
                    {error}
                </div>
            )}

            {progress && (
                <div className={s.progressSection}>
                    <div className={s.progressLabel}>
                        {getStageLabel(progress.stage)}
                    </div>

                    {progress.percentage !== undefined && (
                        <>
                            <div className={s.progressBar}>
                                <div
                                    className={s.progressFill}
                                    style={{ width: `${progress.percentage}%` }}
                                />
                            </div>
                            <div className={s.progressText}>
                                {progress.processed} / {progress.total} ({progress.percentage}%)
                                {progress.sequences_found !== undefined && (
                                    <span className={s.foundBadge}>
                                        Найдено: {progress.sequences_found}
                                    </span>
                                )}
                            </div>
                        </>
                    )}

                    <div className={s.progressMessage}>
                        {progress.message}
                    </div>
                </div>
            )}

            {statistics && (
                <div className={s.statistics}>
                    <h4 className={s.statisticsTitle}>Статистика</h4>
                    <div className={s.statisticsGrid}>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Глаголы</div>
                            <div className={s.statValue}>{statistics.total_verbs.toLocaleString()}</div>
                        </div>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Цепочки</div>
                            <div className={s.statValue}>{statistics.action_sequences.toLocaleString()}</div>
                        </div>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Связи объектов</div>
                            <div className={s.statValue}>{statistics.entity_links.toLocaleString()}</div>
                        </div>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Средняя точность</div>
                            <div className={s.statValue}>{(statistics.avg_confidence * 100).toFixed(0)}%</div>
                        </div>
                    </div>

                    {statistics.sequence_types && statistics.sequence_types.length > 0 && (
                        <div className={s.sequenceTypes}>
                            <h5 className={s.sequenceTypesTitle}>Типы связей:</h5>
                            <div className={s.sequenceTypesList}>
                                {statistics.sequence_types.map((st, idx) => (
                                    <div key={idx} className={s.sequenceTypeItem}>
                                        <span className={s.sequenceTypeName}>{st.type}</span>
                                        <span className={s.sequenceTypeCount}>{st.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {statistics && statistics.action_sequences > 0 && (
                <ActionChainVisualization />
            )}
        </div>
    );
}
