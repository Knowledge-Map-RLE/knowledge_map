import { useCallback, useEffect, useState } from 'react';
import {
    MdReply,
    MdExpandMore,
    MdExpandLess,
} from 'react-icons/md';
import { useToast } from '../../../shared/ui/Toast';
import {
    listFeedbackTickets,
    getFeedbackTicket,
    sendFeedbackMessage,
    updateTicketStatus,
    uploadFeedbackImage,
    feedbackImageUrl,
    type FeedbackTicket,
    type FeedbackMessage,
    type FeedbackStatus,
    STATUS_COLORS,
    STATUS_LABELS,
} from '../../../services/api/feedback';
import s from './FeedbackAdminPanel.module.css';

const ALL_STATUSES: FeedbackStatus[] = ['new', 'in_development', 'resolved', 'rejected'];

function formatTimestamp(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

export function FeedbackAdminPanel() {
    const { error: toastError, success: toastSuccess } = useToast();

    const [tickets, setTickets] = useState<FeedbackTicket[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState<string>('');

    const [expandedUid, setExpandedUid] = useState<string | null>(null);
    const [messages, setMessages] = useState<Record<string, FeedbackMessage[]>>({});
    const [replyText, setReplyText] = useState<Record<string, string>>({});
    const [sendingMap, setSendingMap] = useState<Record<string, boolean>>({});
    const [pendingImages, setPendingImages] = useState<Record<string, { s3Key: string; uploading: boolean }[]>>({});

    const loadTickets = useCallback(async () => {
        setLoading(true);
        try {
            const res = await listFeedbackTickets({
                status: statusFilter || undefined,
                limit: 100,
            });
            setTickets(res.tickets ?? []);
            setTotal(res.total ?? 0);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки обращений');
        } finally {
            setLoading(false);
        }
    }, [statusFilter, toastError]);

    useEffect(() => {
        void loadTickets();
    }, [loadTickets]);

    const loadExpanded = useCallback(async (uid: string) => {
        try {
            const res = await getFeedbackTicket(uid);
            setMessages((prev) => ({ ...prev, [uid]: res.messages ?? [] }));
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки чата');
        }
    }, [toastError]);

    const handleToggle = useCallback((ticket: FeedbackTicket) => {
        setExpandedUid((prev) => {
            const next = prev === ticket.uid ? null : ticket.uid;
            if (next) void loadExpanded(next);
            return next;
        });
    }, [loadExpanded]);

    const handleStatusChange = useCallback(async (ticketUid: string, status: FeedbackStatus) => {
        try {
            await updateTicketStatus(ticketUid, status);
            setTickets((prev) =>
                prev.map((t) => (t.uid === ticketUid ? { ...t, status } : t)),
            );
            toastSuccess('Статус обновлён');
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка смены статуса');
        }
    }, [toastError, toastSuccess]);

    const handleSendReply = useCallback(async (ticketUid: string) => {
        const text = (replyText[ticketUid] ?? '').trim();
        const imgs = pendingImages[ticketUid] ?? [];
        const uploadedKeys = imgs.filter((i) => i.s3Key).map((i) => i.s3Key);
        if (!text && uploadedKeys.length === 0) return;

        setSendingMap((prev) => ({ ...prev, [ticketUid]: true }));
        try {
            const res = await sendFeedbackMessage(ticketUid, text, uploadedKeys, 'admin');
            setMessages((prev) => ({
                ...prev,
                [ticketUid]: [...(prev[ticketUid] ?? []), res.message],
            }));
            setReplyText((prev) => ({ ...prev, [ticketUid]: '' }));
            setPendingImages((prev) => ({ ...prev, [ticketUid]: [] }));
            // обновляем updated_at в списке
            setTickets((prev) =>
                prev.map((t) =>
                    t.uid === ticketUid ? { ...t, updated_at: Date.now() / 1000 } : t,
                ),
            );
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка отправки');
        } finally {
            setSendingMap((prev) => ({ ...prev, [ticketUid]: false }));
        }
    }, [replyText, pendingImages, toastError]);

    const handleAttach = useCallback(async (ticketUid: string, files: FileList | null) => {
        if (!files) return;
        const imageFiles = Array.from(files).filter((f) => f.type.startsWith('image/'));
        for (const file of imageFiles) {
            setPendingImages((prev) => ({
                ...prev,
                [ticketUid]: [...(prev[ticketUid] ?? []), { s3Key: '', uploading: true }],
            }));
            try {
                const res = await uploadFeedbackImage(file);
                setPendingImages((prev) => {
                    const arr = prev[ticketUid] ?? [];
                    const idx = arr.findIndex((i) => !i.s3Key);
                    if (idx === -1) return prev;
                    const newArr = arr.map((i, n) => (n === idx ? { s3Key: res.s3_key, uploading: false } : i));
                    return { ...prev, [ticketUid]: newArr };
                });
            } catch (e) {
                toastError(e instanceof Error ? e.message : 'Ошибка загрузки изображения');
                setPendingImages((prev) => {
                    const arr = prev[ticketUid] ?? [];
                    return { ...prev, [ticketUid]: arr.filter((i) => i.s3Key) };
                });
            }
        }
    }, [toastError]);

    return (
        <div className={s.container}>
            <div className={s.toolbar}>
                <div className={s.title}>
                    Обращения
                    {total > 0 && <span className={s.count}>{total}</span>}
                </div>
                <div className={s.filters}>
                    <button
                        className={`${s.filterBtn} ${statusFilter === '' ? s.filterActive : ''}`}
                        onClick={() => setStatusFilter('')}
                    >
                        Все
                    </button>
                    {ALL_STATUSES.map((st) => (
                        <button
                            key={st}
                            className={`${s.filterBtn} ${statusFilter === st ? s.filterActive : ''}`}
                            style={statusFilter === st ? { background: STATUS_COLORS[st], borderColor: STATUS_COLORS[st] } : undefined}
                            onClick={() => setStatusFilter(st)}
                        >
                            {STATUS_LABELS[st]}
                        </button>
                    ))}
                </div>
            </div>

            {loading ? (
                <div className={s.state}>Загрузка…</div>
            ) : tickets.length === 0 ? (
                <div className={s.state}>Обращений пока нет</div>
            ) : (
                <div className={s.list}>
                    {tickets.map((t) => {
                        const expanded = expandedUid === t.uid;
                        const msgs = messages[t.uid] ?? [];
                        const reply = replyText[t.uid] ?? '';
                        const sending = sendingMap[t.uid] ?? false;
                        const imgs = pendingImages[t.uid] ?? [];

                        return (
                            <div key={t.uid} className={s.card}>
                                <div className={s.cardHeader} onClick={() => handleToggle(t)}>
                                    <div className={s.cardInfo}>
                                        <div className={s.cardTop}>
                                            <span className={s.userTitle}>Обращение</span>
                                            <span
                                                className={s.statusBadge}
                                                style={{ background: STATUS_COLORS[t.status] || STATUS_COLORS.new }}
                                            >
                                                {STATUS_LABELS[t.status] || t.status}
                                            </span>
                                        </div>
                                        <div className={s.cardMeta}>
                                            <span>UID: {t.user_uid}</span>
                                            <span>{formatTimestamp(t.created_at)}</span>
                                            {t.app_version && <span>v{t.app_version}</span>}
                                        </div>
                                        <div className={s.cardPreview}>
                                            {msgs.length > 0
                                                ? (msgs[msgs.length - 1].text || '📷 Изображение')
                                                : ''}
                                        </div>
                                    </div>
                                    <div className={s.expand}>
                                        {expanded ? <MdExpandLess /> : <MdExpandMore />}
                                    </div>
                                </div>

                                {expanded && (
                                    <div className={s.detail}>
                                        {/* Status select */}
                                        <div className={s.statusRow}>
                                            <span className={s.statusLabel}>Статус:</span>
                                            <select
                                                className={s.select}
                                                value={t.status}
                                                onChange={(e) =>
                                                    void handleStatusChange(t.uid, e.target.value as FeedbackStatus)
                                                }
                                            >
                                                {ALL_STATUSES.map((st) => (
                                                    <option key={st} value={st}>
                                                        {STATUS_LABELS[st]}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>

                                        {/* Messages */}
                                        <div className={s.msgList}>
                                            {msgs.length === 0 ? (
                                                <div className={s.stateSmall}>Сообщений пока нет</div>
                                            ) : (
                                                msgs.map((m) => (
                                                    <div
                                                        key={m.uid}
                                                        className={`${s.msg} ${m.sender_type === 'admin' ? s.msgAdmin : s.msgUser}`}
                                                    >
                                                        <div className={s.msgSender}>
                                                            {m.sender_type === 'admin' ? 'Вы' : 'Пользователь'}
                                                            <span className={s.msgTime}>{formatTimestamp(m.created_at)}</span>
                                                        </div>
                                                        <div className={s.msgText}>{m.text}</div>
                                                        {m.image_s3_keys && m.image_s3_keys.length > 0 && (
                                                            <div className={s.msgImages}>
                                                                {m.image_s3_keys.map((key) => (
                                                                    <img
                                                                        key={key}
                                                                        src={feedbackImageUrl(key)}
                                                                        alt=""
                                                                        className={s.msgImage}
                                                                        loading="lazy"
                                                                    />
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))
                                            )}
                                        </div>

                                        {/* Attach + reply */}
                                        <div className={s.replyArea}>
                                            <label className={s.attachBtn}>
                                                <MdReply />
                                                <input
                                                    type="file"
                                                    accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                                                    multiple
                                                    className="hidden"
                                                    onChange={(e) => void handleAttach(t.uid, e.target.files)}
                                                />
                                            </label>
                                            {imgs.length > 0 && (
                                                <div className={s.pendingImgs}>
                                                    {imgs.map((img, idx) => (
                                                        <span key={idx} className={s.pendingImg}>
                                                            {img.uploading ? '…' : '📷'}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                            <textarea
                                                className={s.replyInput}
                                                value={reply}
                                                onChange={(e) =>
                                                    setReplyText((prev) => ({ ...prev, [t.uid]: e.target.value }))
                                                }
                                                placeholder="Ответ…"
                                                rows={2}
                                            />
                                            <button
                                                className={s.sendBtn}
                                                disabled={sending || (!reply.trim() && imgs.every((i) => !i.s3Key))}
                                                onClick={() => void handleSendReply(t.uid)}
                                            >
                                                {sending ? '…' : 'Отправить'}
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
