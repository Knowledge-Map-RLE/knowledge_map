import React, { useEffect, useState, useCallback } from 'react';
import s from './Document_downloader_ui.module.css';
import WorkerDetailsModal from './WorkerDetailsModal';

const WORKER_STATUS_URL = '/api/worker';
const POLL_INTERVAL_MS = 3000;

interface WorkerStatus {
    total: number;
    done: number;
    failed: number;
    in_progress: number;
    pending: number;
    percent: number;
    status: string;
    started_at: string | null;
}

const WorkerStatusIndicator: React.FC = () => {
    const [workerStatus, setWorkerStatus] = useState<WorkerStatus | null>(null);
    const [isReachable, setIsReachable] = useState(false);
    const [showModal, setShowModal] = useState(false);

    const fetchStatus = useCallback(async () => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 2000);
        try {
            const res = await fetch(`${WORKER_STATUS_URL}/status`, { signal: controller.signal });
            if (res.ok) {
                const data: WorkerStatus = await res.json();
                setWorkerStatus(data);
                setIsReachable(true);
            } else {
                setIsReachable(false);
            }
        } catch {
            setIsReachable(false);
        } finally {
            clearTimeout(timer);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const id = setInterval(fetchStatus, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [fetchStatus]);

    const isActive = isReachable && workerStatus && workerStatus.total > 0;
    const percent = workerStatus?.percent ?? 0;

    return (
        <div className={s.workerBlock}>
            <div className={s.workerHeader}>
                <button className={s.workerTitleBtn} onClick={() => setShowModal(true)}>
                    Пакетная загрузка
                </button>
                {isActive ? (
                    <span className={s.workerPercent}>{percent}%</span>
                ) : (
                    <span className={s.workerStatusBadge}>
                        {isReachable ? 'Запущен' : 'Не запущен'}
                    </span>
                )}
            </div>

            <div className={s.workerProgressBar}>
                <div
                    className={s.workerProgressFill}
                    style={{ width: `${isActive ? percent : 0}%` }}
                />
            </div>

            {isActive && workerStatus && (
                <div className={s.workerCounts}>
                    <span className={s.countDone}>✓ {workerStatus.done}</span>
                    <span className={s.countInProgress}>⟳ {workerStatus.in_progress}</span>
                    <span className={s.countFailed}>✗ {workerStatus.failed}</span>
                    <span className={s.countPending}>◯ {workerStatus.pending}</span>
                </div>
            )}

            {!isActive && !isReachable && (
                <p className={s.workerHint}>
                    Запустите worker_article_to_knowledge_map/start.ps1
                </p>
            )}

            {showModal && <WorkerDetailsModal onClose={() => setShowModal(false)} />}
        </div>
    );
};

export default WorkerStatusIndicator;
