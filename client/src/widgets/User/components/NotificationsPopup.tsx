import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getNotifications, markNotificationsRead, type NotificationItem } from '../../../services/api/social';
import { useToast } from '../../../shared/ui/Toast';
import s from './NotificationsPopup.module.css';

type TargetType = 'article' | 'statement' | 'user' | 'community';

const CHAT_TARGET_TYPES = new Set<string>(['article', 'statement', 'user', 'community']);

const TARGET_TYPE_LABELS: Record<string, string> = {
    article: 'Статья',
    statement: 'Триплет',
    user: 'Пользователь',
    community: 'Сообщество',
};

function formatTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const now = Date.now();
    const sameDay = new Date(now).toDateString() === d.toDateString();
    const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    if (sameDay) return time;
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) + ' ' + time;
}

export function NotificationsPopup({ onClose }: { onClose: () => void }) {
    const { error: toastError, success: toastSuccess } = useToast();
    const navigate = useNavigate();
    const [notifications, setNotifications] = useState<NotificationItem[]>([]);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await getNotifications();
            setNotifications(res.notifications ?? []);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки уведомлений');
        } finally {
            setLoading(false);
        }
    }, [toastError]);

    useEffect(() => {
        void load();
    }, [load]);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    const handleMarkAll = async () => {
        try {
            await markNotificationsRead();
            setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
            toastSuccess('Все уведомления прочитаны');
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка');
        }
    };

    const handleOpen = async (n: NotificationItem) => {
        if (!n.is_read) {
            try {
                await markNotificationsRead(n.uid);
                setNotifications((prev) => prev.map((x) => (x.uid === n.uid ? { ...x, is_read: true } : x)));
            } catch {
                /* игнорируем */
            }
        }
        onClose();
        if (CHAT_TARGET_TYPES.has(n.target_type) && n.target_uid) {
            navigate('/social_network', {
                state: {
                    chat: { type: n.target_type as TargetType, uid: n.target_uid, label: n.text },
                },
            });
        }
    };

    const unreadCount = notifications.filter((n) => !n.is_read).length;

    return (
        <>
            <div className={s.backdrop} onClick={onClose} />
            <div className={s.popup} role="dialog" aria-label="Уведомления">
                <div className={s.popupHeader}>
                    <div className={s.popupTitle}>
                        Уведомления
                        {unreadCount > 0 && <span className={s.badge}>{unreadCount} новых</span>}
                    </div>
                    <button className={s.markAll} onClick={() => void handleMarkAll()} disabled={unreadCount === 0}>
                        Прочитать все
                    </button>
                </div>
                {loading && <div className={s.state}>Загрузка…</div>}
                {!loading && notifications.length === 0 && (
                    <div className={s.state}>Уведомлений пока нет</div>
                )}
                <div className={s.list}>
                    {notifications.map((n) => (
                        <div
                            key={n.uid}
                            className={`${s.item} ${!n.is_read ? s.itemUnread : ''}`}
                            onClick={() => void handleOpen(n)}
                            role="button"
                        >
                            <div className={s.itemMain}>
                                <div className={s.itemText}>{n.text}</div>
                                <div className={s.itemMeta}>
                                    {n.target_type ? `${TARGET_TYPE_LABELS[n.target_type] ?? n.target_type} · ` : ''}
                                    {formatTime(n.created_at)}
                                </div>
                            </div>
                            {!n.is_read && <span className={s.dot} />}
                        </div>
                    ))}
                </div>
            </div>
        </>
    );
}
