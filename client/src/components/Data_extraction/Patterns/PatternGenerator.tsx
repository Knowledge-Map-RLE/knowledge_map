import React, { useState } from 'react';
import s from './PatternGenerator.module.css';
import ActionChainBuilder from './ActionChainBuilder';

interface PatternStatistics {
    patterns: number;
    properties: number;
    relationships: number;
}

interface ProgressUpdate {
    total: number;
    processed: number;
    percentage: number;
    stage: 'clearing' | 'creating_patterns' | 'creating_relationships' | 'complete' | 'error';
    message: string;
    statistics?: PatternStatistics;
}

export default function PatternGenerator() {
    const [isGenerating, setIsGenerating] = useState(false);
    const [progress, setProgress] = useState<ProgressUpdate | null>(null);
    const [statistics, setStatistics] = useState<PatternStatistics | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleGeneratePatterns = async () => {
        setIsGenerating(true);
        setError(null);
        setProgress(null);

        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/generate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    batch_size: 100,
                    clear_existing: true
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
                            setIsGenerating(false);
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
            setIsGenerating(false);
        }
    };

    const handleLoadStatistics = async () => {
        try {
            const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
            const response = await fetch(`${apiBaseUrl}/api/data_extraction/patterns/statistics`);

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
            case 'clearing':
                return 'Очистка существующих паттернов...';
            case 'creating_patterns':
                return 'Создание паттернов...';
            case 'creating_relationships':
                return 'Создание связей между паттернами...';
            case 'complete':
                return 'Готово!';
            default:
                return stage;
        }
    };

    return (
        <div className={s.container}>
            <div className={s.header}>
                <h2 className={s.title}>Паттерны</h2>
                <div className={s.actions}>
                    <button
                        className={s.button}
                        onClick={handleLoadStatistics}
                        disabled={isGenerating}
                    >
                        Обновить статистику
                    </button>
                    <button
                        className={`${s.button} ${s.primaryButton}`}
                        onClick={handleGeneratePatterns}
                        disabled={isGenerating}
                    >
                        {isGenerating ? 'Генерация...' : 'Сгенерировать паттерны'}
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
                    <div className={s.progressBar}>
                        <div
                            className={s.progressFill}
                            style={{ width: `${progress.percentage}%` }}
                        />
                    </div>
                    <div className={s.progressText}>
                        {progress.processed} / {progress.total} ({progress.percentage}%)
                    </div>
                    <div className={s.progressMessage}>
                        {progress.message}
                    </div>
                </div>
            )}

            {statistics && (
                <div className={s.statistics}>
                    <h3 className={s.statisticsTitle}>Статистика</h3>
                    <div className={s.statisticsGrid}>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Паттерны</div>
                            <div className={s.statValue}>{statistics.patterns.toLocaleString()}</div>
                        </div>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Свойства</div>
                            <div className={s.statValue}>{statistics.properties.toLocaleString()}</div>
                        </div>
                        <div className={s.statItem}>
                            <div className={s.statLabel}>Связи</div>
                            <div className={s.statValue}>{statistics.relationships.toLocaleString()}</div>
                        </div>
                    </div>
                </div>
            )}

            <ActionChainBuilder />
        </div>
    );
}
