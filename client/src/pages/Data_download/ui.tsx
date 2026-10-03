import { useState, useCallback } from "react";
import { useTranslation } from 'react-i18next';
import Header from "../../widgets/Header";
import { useDataDownload } from "./hooks/useDataDownload";
import { useCitationDownload } from "./hooks/useCitationDownload";
import type { DataSourceStatus, DataSourceState, CitationSourceStatus, CitationSourceState, CitationTestResult } from "./model";
import styles from "./Data_download.module.css";

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

const citationStateIcons: Record<CitationSourceState, string> = {
    idle: "⏸",
    downloading: "📥",
    layouting: "📐",
    completed: "✅",
    error: "❌",
    paused: "⏸",
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
    const { t } = useTranslation();
    const isRunning =
        source.status === "downloading" || source.status === "starting" || source.status === "processing";
    const isIdle = source.status === "idle";

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h3 className={styles.sourceName}>{source.name}</h3>
                <span className={styles.sourceType}>
                    {source.source_type === "s3" ? t('dataDownload.sourceTypes.s3') : t('dataDownload.sourceTypes.ftp')}
                </span>
                <span className={styles.stateBadge}>
                    {stateIcons[source.status]} {t(`dataDownload.status.${source.status}`)}
                </span>
            </div>
            <div className={styles.progressArea}>
                <ProgressBar
                    label={t('dataDownload.progress.download')}
                    percent={source.progress_percent}
                    done={source.downloaded_files}
                    total={source.total_files}
                    currentFile={source.status === "downloading" ? source.current_file : undefined}
                />
                <ProgressBar
                    label={t('dataDownload.progress.processing')}
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
                    <button className={styles.startBtn} onClick={onStart}>{t('dataDownload.actions.start')}</button>
                )}
                {isRunning && (
                    <button className={styles.pauseBtn} onClick={onPause}>{t('dataDownload.actions.pause')}</button>
                )}
                <button className={styles.resetBtn} onClick={onReset}>{t('dataDownload.actions.reset')}</button>
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

const citationSourceTypes: Record<string, true> = {
    "api+bulk": true,
    "s3+api": true,
};

const CitationSourceCard: React.FC<CitationCardProps> = ({ source, onStart, onResume, onPause, onReset, onTest, testResult, testing }) => {
    const { t } = useTranslation();
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
                    {citationSourceTypes[source.source_type] ? t(`dataDownload.sourceTypes.${source.source_type}`) : source.source_type}
                </span>
                <span className={styles.stateBadge}>
                    {citationStateIcons[source.status]} {t(`dataDownload.status.${source.status}`)}
                </span>
            </div>

            <p className={styles.sourceDescription}>{source.description}</p>

            <div className={styles.progressArea}>
                <ProgressBar
                    label={t('dataDownload.progress.edgesLoaded')}
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
                    {t('dataDownload.citations.fileLimit')}
                </label>
                <input
                    id={`limit-${source.key}`}
                    className={styles.fileLimitInput}
                    type="number"
                    min={1}
                    placeholder={t('dataDownload.citations.allFiles')}
                    value={maxFiles}
                    onChange={(e) => setMaxFiles(e.target.value)}
                    disabled={isRunning}
                />
            </div>

            {testResult && (
                <div className={styles.testResult}>
                    <div className={styles.testTitle}>{t('dataDownload.citations.apiTest', { count: testResult.sample_size })}</div>
                    <div className={styles.testRow}>
                        <span>{t('dataDownload.citations.edgesFound')}: <strong>{testResult.edges_found}</strong></span>
                        <span>{t('dataDownload.citations.elapsed')}: <strong>{testResult.elapsed_seconds}{t('dataDownload.citations.seconds')}</strong></span>
                    </div>
                    {testResult.estimated_total_edges && (
                        <div className={styles.testRow}>
                            <span>{t('dataDownload.citations.estimatedEdges')}: <strong>{testResult.estimated_total_edges.toLocaleString()}</strong></span>
                            {testResult.estimated_time_seconds && (
                                <span>{t('dataDownload.citations.estimatedHours', { hours: Math.round(testResult.estimated_time_seconds / 3600) })}</span>
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
                        <button className={styles.startBtn} onClick={() => onStart(parseMaxFiles())}>{t('dataDownload.actions.start')}</button>
                        <button
                            className={styles.testBtn}
                            onClick={onTest}
                            disabled={testing}
                        >
                            {testing ? t('dataDownload.citations.testing') : t('dataDownload.citations.testApi')}
                        </button>
                    </>
                )}
                {isPaused && (
                    <button className={styles.startBtn} onClick={onResume}>{t('dataDownload.actions.resume')}</button>
                )}
                {isRunning && (
                    <button className={styles.pauseBtn} onClick={onPause}>{t('dataDownload.actions.pause')}</button>
                )}
                <button className={styles.resetBtn} onClick={onReset}>{t('dataDownload.actions.reset')}</button>
            </div>
        </div>
    );
};

// ── DOI Lookup ───────────────────────────────────────────────────────────

interface DoiLookupProps {
    onLoadDoi: (doi: string) => Promise<any>;
}

const DoiLookup: React.FC<DoiLookupProps> = ({ onLoadDoi }) => {
    const { t } = useTranslation();
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
            <h3 className={styles.doiLookupTitle}>{t('dataDownload.doi.title')}</h3>
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
                    {loading ? t('dataDownload.doi.loading') : t('dataDownload.doi.find')}
                </button>
            </div>
            {result && (
                <div className={styles.doiResult}>
                    <div className={styles.testRow}>
                        <span>DOI: <strong>{result.doi}</strong></span>
                        <span>{t('dataDownload.doi.rawEdges')}: <strong>{result.total_edges_raw}</strong></span>
                        <span>{t('dataDownload.doi.unique')}: <strong>{result.unique_edges}</strong></span>
                        <span>{t('dataDownload.doi.written')}: <strong>{result.written_ops}</strong></span>
                    </div>
                    {result.sources && Object.entries(result.sources).map(([k, v]: [string, any]) => (
                        <div key={k} className={styles.testRow}>
                            <span>{k}: {v.edges} edges ({v.status})</span>
                        </div>
                    ))}
                    {result.layout && (
                        <div className={styles.testRow}>
                            <span>{t('dataDownload.doi.layout')}: <strong>{result.layout.updated}</strong> {t('dataDownload.doi.nodesUpdated')}</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

// ── Main Page ────────────────────────────────────────────────────────────

const DataDownloadUI: React.FC = () => {
    const { t } = useTranslation();
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
                <div className={styles.loading}>{t('dataDownload.status.loading')}</div>
            </div>
        );
    }

    if (errorMsg) {
        return (
            <div className={styles.container}>
                <Header showSearch={true} className={styles.header} />
                <div className={styles.error}>{t('dataDownload.status.error', { error: errorMsg })}</div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <div className={styles.titleRow}>
                    <h1 className={styles.title}>{t('dataDownload.title')}</h1>
                    <span className={`${styles.connectionStatus} ${isConnected ? styles.connected : styles.disconnected}`}>
                        {isConnected ? t('dataDownload.status.connected') : t('dataDownload.status.disconnected')}
                    </span>
                </div>

                {/* ── PubMed Sources ──────────────────────────────────── */}
                <div className={styles.sectionHeader}>
                    <h2 className={styles.sectionTitle}>PubMed / PMC</h2>
                    <span className={styles.sectionBadge}>{t('dataDownload.articles.badge')}</span>
                </div>
                <p className={styles.description}>
                    {t('dataDownload.articles.description')}
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
                        {t('dataDownload.articles.empty')}
                    </div>
                )}

                {/* ── Citation Graph Sources ──────────────────────────── */}
                <div className={styles.sectionDivider} />
                <div className={styles.sectionHeader}>
                    <h2 className={styles.sectionTitle}>{t('dataDownload.citations.title')}</h2>
                    <span className={styles.sectionBadge}>{t('dataDownload.citations.badge')}</span>
                </div>
                <p className={styles.description}>
                    {t('dataDownload.citations.description')}
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
                        {t('dataDownload.citations.empty')}
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
