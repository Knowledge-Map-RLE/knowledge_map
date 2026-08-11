import { useCallback, useEffect, useState } from 'react';
import {
    getTrends,
    type TrendItem,
} from '../../../services/api/social';
import { useToast } from '../../../shared/ui/Toast';
import { MdChatBubbleOutline } from 'react-icons/md';
import { TARGET_TYPE_LABELS, type ChatTarget } from '../model';
import s from '../Social_network.module.css';

interface TrendsPanelProps {
    onOpenChat: (target: ChatTarget) => void;
}

export function TrendsPanel({ onOpenChat }: TrendsPanelProps) {
    const { error: toastError } = useToast();
    const [trends, setTrends] = useState<TrendItem[]>([]);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await getTrends(8);
            const map = new Map<string, TrendItem>();
            for (const t of [...res.by_comments, ...res.by_likes]) {
                const key = `${t.target_type}|${t.target_uid}`;
                const prev = map.get(key);
                map.set(key, prev ? { ...prev, count: prev.count + t.count } : t);
            }
            setTrends([...map.values()].sort((a, b) => b.count - a.count).slice(0, 8));
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки трендов');
        } finally {
            setLoading(false);
        }
    }, [toastError]);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <div className={s.panel}>
            <div className={s.panelSection}>
                <div className={s.panelTitle}>Тренды</div>
                {loading && <div className={s.hint}>Загрузка…</div>}
                {!loading && trends.length === 0 && <div className={s.hint}>Пока нет трендов</div>}
                {trends.map((t) => (
                    <div key={`${t.target_type}|${t.target_uid}`} className={s.cardRow}>
                        <div className={s.cardMain}>
                            <div className={s.cardName}>{t.label}</div>
                            <div className={s.cardSub}>
                                {TARGET_TYPE_LABELS[t.target_type]} · {t.count}
                            </div>
                        </div>
                        <button
                            className={s.ghostBtn}
                            onClick={() => onOpenChat({ type: t.target_type, uid: t.target_uid, label: t.label })}
                        >
                            <MdChatBubbleOutline />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
}
