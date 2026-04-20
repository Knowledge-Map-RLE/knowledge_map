import Header from "../../widgets/Header";
import { useDataDownload } from "./hooks/useDataDownload";
import { DataSourceStatus, DataSourceState } from "./model";
import styles from "./Data_download.module.css";

const stateLabels: Record<DataSourceState, string> = {
    idle: "Ожидание",
    starting: "Запуск...",
    downloading: "Загрузка",
    paused: "Приостановлено",
    completed: "Завершено",
    error: "Ошибка",
};

const stateIcons: Record<DataSourceState, string> = {
    idle: "⏸",
    starting: "🔄",
    downloading: "📥",
    paused: "⏸",
    completed: "✅",
    error: "❌",
};

interface SourceCardProps {
    source: DataSourceStatus;
    onStart: () => void;
    onPause: () => void;
    onReset: () => void;
}

const SourceCard: React.FC<SourceCardProps> = ({ source, onStart, onPause, onReset }) => {
    const isRunning = source.status === "downloading" || source.status === "starting";
    const isCompleted = source.status === "completed";
    const isIdle = source.status === "idle";

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <h3 className={styles.sourceName}>{source.name}</h3>
                <span className={styles.stateBadge}>
                    {stateIcons[source.status]} {stateLabels[source.status]}
                </span>
            </div>

            <div className={styles.progressContainer}>
                <div className={styles.progressBar}>
                    <div
                        className={styles.progressFill}
                        style={{ width: `${source.progress_percent}%` }}
                    />
                </div>
                <span className={styles.progressText}>
                    {source.progress_percent.toFixed(1)}% ({source.downloaded_files} / {source.total_files})
                </span>
                {source.current_file && (
                    <span className={styles.currentFile}>
                        📄 {source.current_file}
                    </span>
                )}
            </div>

            <div className={styles.ftpUrl}>
                <a
                    href={`https://${source.ftp_url}`}
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
                {(source.status === "paused" || source.status === "completed" || source.status === "error") && (
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
                <Header showSearch={false} />
                <div className={styles.loading}>Загрузка...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.container}>
                <Header showSearch={false} />
                <div className={styles.error}>Ошибка: {error}</div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <Header showSearch={false} />
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