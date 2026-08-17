import Header from "../../widgets/Header";
import { useDataDownload } from "./hooks/useDataDownload";
import type { DataSourceStatus, DataSourceState } from "./model";
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

interface SourceCardProps {
    source: DataSourceStatus;
    onStart: () => void;
    onPause: () => void;
    onReset: () => void;
}

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
                    {clamped.toFixed(1)}% ({done} / {total})
                </span>
            </div>
            <div className={styles.progressBar}>
                <div
                    className={`${styles.progressFill} ${accent ? styles.progressFillAccent : ""}`}
                    style={{ width: `${clamped}%` }}
                />
            </div>
            {currentFile && <span className={styles.currentFile}>📄 {currentFile}</span>}
        </div>
    );
};

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
                {source.source_type === "s3" ? (
                    <span className={styles.ftpLink}>{source.ftp_url}</span>
                ) : (
                    <a
                        href={`https://${source.ftp_url}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.ftpLink}
                    >
                        {source.ftp_url}
                    </a>
                )}
            </div>

            {source.error_message && (
                <div className={styles.errorMessage}>{source.error_message}</div>
            )}

            <div className={styles.actions}>
                {isIdle && (
                    <button className={styles.startBtn} onClick={onStart}>
                        ▶ Старт
                    </button>
                )}
                {isRunning && (
                    <button className={styles.pauseBtn} onClick={onPause}>
                        ⏸ Пауза
                    </button>
                )}
                {(source.status === "paused" ||
                    source.status === "stopped" ||
                    source.status === "completed" ||
                    source.status === "error") && (
                    <button className={styles.startBtn} onClick={onStart}>
                        ▶ Старт
                    </button>
                )}
                <button className={styles.resetBtn} onClick={onReset}>
                    ↻ Сброс
                </button>
            </div>
        </div>
    );
};

const DataDownloadUI: React.FC = () => {
    const {
        sources,
        loading,
        error,
        isConnected,
        startDownload,
        pauseDownload,
        resetDownload,
    } = useDataDownload();

    if (loading) {
        return (
            <div className={styles.container}>
                <Header showSearch={true} className={styles.header} />
                <div className={styles.loading}>Загрузка...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.container}>
                <Header showSearch={true} className={styles.header} />
                <div className={styles.error}>Ошибка: {error}</div>
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

                <p className={styles.description}>
                    Загрузка научных статей из внешних источников в базу данных Knowledge Map.
                </p>

                <div className={styles.sourcesList}>
                    {sources.map((source) => (
                        <SourceCard
                            key={source.name}
                            source={source}
                            onStart={() => startDownload(source.name)}
                            onPause={() => pauseDownload(source.name)}
                            onReset={() => resetDownload(source.name)}
                        />
                    ))}
                </div>

                {sources.length === 0 && (
                    <div className={styles.empty}>
                        Источники данных не найдены. Нажмите кнопку ниже для инициализации.
                    </div>
                )}
            </main>
        </div>
    );
};

export default DataDownloadUI;