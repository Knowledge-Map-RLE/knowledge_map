import { useState, useCallback } from "react";
import Header from "../../widgets/Header";
import { useDataDownload } from "./hooks/useDataDownload";
import { useCitationDownload } from "./hooks/useCitationDownload";
import type { DataSourceStatus, DataSourceState, CitationSourceStatus, CitationSourceState, CitationTestResult } from "./model";
import styles from "./Data_download.module.css";

const stateLabels: Record<DataSourceState, string> = {
    idle: "Ожидание",
    starting: "Запуск...",
    downloading: "Загрузка",
    paused: "Приостановлено",
    stopped: "Остановлено",
    processing: "Обработка",
    completed: "Завершено",
    error: "Ошибка",
};

const stateIcons: Record<DataSourceState, string> = {
    idle: "⏸",
    starting: "🔄",
    downloading: "📥",
    paused: "⏸",
    stopped: "⏹",
    processing: "⚙️",
    completed: "✅",
    error: "❌",
};

const citationStateLabels: Record<CitationSourceState, string> = {
    idle: "Ожидание",
    downloading: "Загрузка",
    layouting: "Укладка графа",
    completed: "Завершено",
    error: "Ошибка",
    paused: "Приостановлено",
};

const citationStateIcons: Record<CitationSourceState, string> = {
    idle: "⏸",
    downloading: "📥",
    layouting: "📐",
    completed: "✅",
    error: "❌",
    paused: "⏸",
};

const sourceTypeIcons: Record<string, string> = {
    "ftp": "📡 FTP",
    "s3": "🪣 S3 (Open Data)",
    "api+bulk": "🌐 API + Dump",
    "s3+api": "🪣 S3 + API",
};

// ── Shared Components ────────────────────────────────────────────────────

interface ProgressBarProps {
    label: string;
    percent: number;
    done: number;
    total: number;
    currentFile?: string;
    accent?: boolean;
}

const ProgressBar: React.FC<ProgressBarProps> = ({ label, percent, done, total, currentFile, accent }) => {
    const clamped = Math.min(100, Math.max(0, percent));
    return (
        <div className={styles.progressContainer}>
            <div className={styles.progressRow}>
                <span className={styles.progressLabel}>{label}</span>
                <span className={styles.progressText}>
                    {clamped.toFixed(1)}% ({done.toLocaleString()} / {total.toLocaleString()})
                </span>
            </div>
            <div className={styles.progressBar}>
                <div
                    className={`${styles.progressFill} ${accent ? styles.progressFillAccent : ""}`}
                    style={{ width: `${clamped}%` }}
                />
            </div>
            {currentFile && <span className={styles.currentFile}>{currentFile}</span>}
        </div>
    );
};

// ── PubMed Source Card ───────────────────────────────────────────────────

interface SourceCardProps {
    source: DataSourceStatus;
    onStart: () => void;
    onPause: () => void;
    onReset: () => void;
}

const SourceCard: React.FC<SourceCardProps> = ({ source, onStart, onPause, onReset }) => {
    const isRunning =
        source.status === "downloading" || source.status === "starting" || source.status === "processing";
    const isIdle = source.status === "idle";

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h3 className={styles.sourceName}>{source.name}</h3>
                <span className={styles.sourceType}>
                    {source.source_type === "s3" ? "🪣 S3 (Open Data)" : "📡 FTP"}
                </span>
                <span className={styles.stateBadge}>
                    {stateIcons[source.status]} {stateLabels[source.status]}
                </span>
            </div>
            <div className={styles.progressArea}>
                <ProgressBar
                    label="Загрузка"
                    percent={source.progress_percent}
                    done={source.downloaded_files}
                    total={source.total_files}
                    currentFile={source.status === "downloading" ? source.current_file : undefined}
                />
                <ProgressBar
                    label="Обработка"
                    percent={source.processing_percent}
                    done={source.processed_files}
                    total={source.processing_total}
                    currentFile={source.processing_current_file}
                    accent
                />
            </div>
            <div className={styles.ftpUrl}>
                <a
                    href={source.source_type === "s3" ? `#${source.ftp_url}` : `https://${source.ftp_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.ftpLink}
                >
                    {source.ftp_url}
                </a>
            </div>
            {source.error_message && (
                <div className={styles.errorMessage}>{source.error_message}</div>
            )}
            <div className={styles.actions}>
                {(isIdle || source.status === "paused" || source.status === "stopped" || source.status === "completed" || source.status === "error") && (
                    <button className={styles.startBtn} onClick={onStart}>▶ Старт</button>
                )}
                {isRunning && (
                    <button className={styles.pauseBtn} onClick={onPause}>⏸ Пауза</button>
                )}
                <button className={styles.resetBtn} onClick={onReset}>↻ Сброс</button>
            </div>
        </div>
    );
};

// ── Citation Source Card ─────────────────────────────────────────────────

interface CitationCardProps {
    source: CitationSourceStatus;
    onStart: (maxFiles?: number) => void;
    onResume: () => void;
    onPause: () => void;
    onReset: () => void;
    onTest: () => void;
    testResult: CitationTestResult | null;
    testing: boolean;
}

const citationSourceTypes: Record<string, string> = {
    "api+bulk": "🌐 API + Dump",
    "s3+api": "🪣 S3 + API",
};

const CitationSourceCard: React.FC<CitationCardProps> = ({ source, onStart, onResume, onPause, onReset, onTest, testResult, testing }) => {
    const [maxFiles, setMaxFiles] = useState("");
    const isRunning = source.status === "downloading" || source.status === "layouting";
    const isPaused = source.status === "paused";
    const canStart = source.status === "idle" || source.status === "completed" || source.status === "error";

    const parseMaxFiles = (): number | undefined => {
        const value = parseInt(maxFiles, 10);
        return isNaN(value) || value <= 0 ? undefined : value;
    };

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h3 className={styles.sourceName}>{source.name}</h3>
                <span className={styles.sourceType}>
                    {citationSourceTypes[source.source_type] || source.source_type}
                </span>
                <span className={styles.stateBadge}>
                    {citationStateIcons[source.status]} {citationStateLabels[source.status]}
                </span>
            </div>

            <p className={styles.sourceDescription}>{source.description}</p>

            <div className={styles.progressArea}>
                <ProgressBar
                    label="Edges загружено"
                    percent={source.progress_percent}
                    done={source.downloaded_edges}
                    total={source.total_edges}
                    accent
                />
            </div>

            {source.error_message && (
                <div className={styles.errorMessage}>{source.error_message}</div>
            )}

            <div className={styles.fileLimitRow}>
                <label className={styles.fileLimitLabel} htmlFor={`limit-${source.key}`}>
                    Лимит файлов:
                </label>
                <input
                    id={`limit-${source.key}`}
                    className={styles.fileLimitInput}
                    type="number"
                    min={1}
                    placeholder="все"
                    value={maxFiles}
                    onChange={(e) => setMaxFiles(e.target.value)}
                    disabled={isRunning}
                />
            </div>

            {testResult && (
                <div className={styles.testResult}>
                    <div className={styles.testTitle}>Тест API ({testResult.sample_size} DOI):</div>
                    <div className={styles.testRow}>
                        <span>Найдено edges: <strong>{testResult.edges_found}</strong></span>
                        <span>Время: <strong>{testResult.elapsed_seconds}с</strong></span>
                    </div>
                    {testResult.estimated_total_edges && (
                        <div className={styles.testRow}>
                            <span>Оценка edges: <strong>{testResult.estimated_total_edges.toLocaleString()}</strong></span>
                            {testResult.estimated_time_seconds && (
                                <span>~{Math.round(testResult.estimated_time_seconds / 3600)}ч загрузки</span>
                            )}
                        </div>
                    )}
                    {testResult.errors.length > 0 && (
                        <div className={styles.testErrors}>
                            {testResult.errors.map((e, i) => <div key={i}>{e}</div>)}
                        </div>
                    )}
                </div>
            )}

            <div className={styles.actions}>
                {canStart && (
                    <>
                        <button className={styles.startBtn} onClick={() => onStart(parseMaxFiles())}>▶ Старт</button>
                        <button
                            className={styles.testBtn}
                            onClick={onTest}
                            disabled={testing}
                        >
                            {testing ? "⏳ Тест..." : "🧪 Тест API"}
                        </button>
                    </>
                )}
                {isPaused && (
                    <button className={styles.startBtn} onClick={onResume}>▶ Продолжить</button>
                )}
                {isRunning && (
                    <button className={styles.pauseBtn} onClick={onPause}>⏸ Пауза</button>
                )}
                <button className={styles.resetBtn} onClick={onReset}>↻ Сброс</button>
            </div>
        </div>
    );
};

// ── DOI Lookup ───────────────────────────────────────────────────────────

interface DoiLookupProps {
    onLoadDoi: (doi: string) => Promise<any>;
}

const DoiLookup: React.FC<DoiLookupProps> = ({ onLoadDoi }) => {
    const [doi, setDoi] = useState("");
    const [result, setResult] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const handleLoad = useCallback(async () => {
        if (!doi.trim()) return;
        setLoading(true);
        try {
            const r = await onLoadDoi(doi.trim());
            setResult(r);
        } finally {
            setLoading(false);
        }
    }, [doi, onLoadDoi]);

    return (
        <div className={styles.doiLookup}>
            <h3 className={styles.doiLookupTitle}>Поиск по DOI</h3>
            <div className={styles.doiInputRow}>
                <input
                    className={styles.doiInput}
                    type="text"
                    placeholder="10.1038/s41586-020-2649-2"
                    value={doi}
                    onChange={(e) => setDoi(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLoad()}
                />
                <button
                    className={styles.startBtn}
                    onClick={handleLoad}
                    disabled={loading || !doi.trim()}
                >
                    {loading ? "⏳..." : "🔍 Найти"}
                </button>
            </div>
            {result && (
                <div className={styles.doiResult}>
                    <div className={styles.testRow}>
                        <span>DOI: <strong>{result.doi}</strong></span>
                        <span>Raw edges: <strong>{result.total_edges_raw}</strong></span>
                        <span>Уникальных: <strong>{result.unique_edges}</strong></span>
                        <span>Записано: <strong>{result.written_ops}</strong></span>
                    </div>
                    {result.sources && Object.entries(result.sources).map(([k, v]: [string, any]) => (
                        <div key={k} className={styles.testRow}>
                            <span>{k}: {v.edges} edges ({v.status})</span>
                        </div>
                    ))}
                    {result.layout && (
                        <div className={styles.testRow}>
                            <span>Укладка: <strong>{result.layout.updated}</strong> узлов обновлено</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

// ── Main Page ────────────────────────────────────────────────────────────

const DataDownloadUI: React.FC = () => {
    const {
        sources: pubmedSources,
        loading: pubmedLoading,
        error: pubmedError,
        isConnected,
        startDownload,
        pauseDownload,
        resetDownload,
    } = useDataDownload();

    const {
        sources: citationSources,
        loading: citationLoading,
        error: citationError,
        startLoad,
        pauseLoad,
        resumeLoad,
        resetLoad,
        testSource,
        loadByDoi,
    } = useCitationDownload();

    const [testResults, setTestResults] = useState<Record<string, CitationTestResult | null>>({});
    const [testingKey, setTestingKey] = useState<string | null>(null);

    const handleTest = useCallback(async (key: string) => {
        setTestingKey(key);
        try {
            const result = await testSource(key);
            setTestResults((prev) => ({ ...prev, [key]: result }));
        } finally {
            setTestingKey(null);
        }
    }, [testSource]);

    const isLoading = pubmedLoading || citationLoading;
    const errorMsg = pubmedError || citationError;

    if (isLoading) {
        return (
            <div className={styles.container}>
                <Header showSearch={true} className={styles.header} />
                <div className={styles.loading}>Загрузка...</div>
            </div>
        );
    }

    if (errorMsg) {
        return (
            <div className={styles.container}>
                <Header showSearch={true} className={styles.header} />
                <div className={styles.error}>Ошибка: {errorMsg}</div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <div className={styles.titleRow}>
                    <h1 className={styles.title}>Загрузка данных</h1>
                    <span className={`${styles.connectionStatus} ${isConnected ? styles.connected : styles.disconnected}`}>
                        {isConnected ? "🟢 Подключено" : "🔴 Отключено"}
                    </span>
                </div>

                {/* ── PubMed Sources ──────────────────────────────────── */}
                <div className={styles.sectionHeader}>
                    <h2 className={styles.sectionTitle}>PubMed / PMC</h2>
                    <span className={styles.sectionBadge}>Статьи</span>
                </div>
                <p className={styles.description}>
                    Загрузка научных статей из PubMed и PubMed Central (FTP/S3).
                </p>
                <div className={styles.sourcesList}>
                    {pubmedSources.map((source) => (
                        <SourceCard
                            key={source.name}
                            source={source}
                            onStart={() => startDownload(source.name)}
                            onPause={() => pauseDownload(source.name)}
                            onReset={() => resetDownload(source.name)}
                        />
                    ))}
                </div>
                {pubmedSources.length === 0 && (
                    <div className={styles.empty}>
                        Источники PubMed не найдены. Нажмите кнопку для инициализации.
                    </div>
                )}

                {/* ── Citation Graph Sources ──────────────────────────── */}
                <div className={styles.sectionDivider} />
                <div className={styles.sectionHeader}>
                    <h2 className={styles.sectionTitle}>Цитатный граф (DOI)</h2>
                    <span className={styles.sectionBadge}>Зависимости</span>
                </div>
                <p className={styles.description}>
                    Данные о цитированиях и ссылках между документами (DOI). Источники:
                    OpenCitations, OpenAlex, Crossref, DataCite.
                </p>
                <div className={styles.sourcesList}>
                    {citationSources.map((source) => (
                        <CitationSourceCard
                            key={source.key}
                            source={source}
                            onStart={(maxFiles) => startLoad(source.key, maxFiles)}
                            onResume={() => resumeLoad(source.key)}
                            onPause={() => pauseLoad(source.key)}
                            onReset={() => resetLoad(source.key)}
                            onTest={() => handleTest(source.key)}
                            testResult={testResults[source.key] ?? null}
                            testing={testingKey === source.key}
                        />
                    ))}
                </div>
                {citationSources.length === 0 && (
                    <div className={styles.empty}>
                        Источники цитат не найдены. Нажмите кнопку для инициализации.
                    </div>
                )}

                {/* ── DOI Lookup ──────────────────────────────────────── */}
                <div className={styles.sectionDivider} />
                <DoiLookup onLoadDoi={loadByDoi} />
            </main>
        </div>
    );
};

export default DataDownloadUI;
