import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    getChat,
    sendMessage,
    toggleLike,
    createComplaint,
    listFriends,
    listCommunities,
    getTrends,
    resolveEntity,
    type ChatMessage,
    type ChatReference,
    type ChatTargetType,
    type CommunitySummary,
    type SocialUserProfile,
    type TrendItem,
} from '../../../services/api/social';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import { MarkdownContent } from '../../../shared/ui/MarkdownContent';
import { BlockCard, type BlockCardReference } from '../../../shared/ui/BlockCard';
import {
    MdArrowForward, MdChatBubbleOutline, MdLocalFireDepartment,
    MdThumbUp, MdReply, MdContentCopy, MdWarning, MdClose, MdLink,
} from 'react-icons/md';
import { formatTime, TARGET_TYPE_LABELS, type ChatTarget } from '../model';
import s from '../Social_network.module.css';

interface ChatPanelProps {
    target: ChatTarget | null;
    onOpenTarget: (target: ChatTarget) => void;
    myUid: string;
    hideRail?: boolean;
    title?: string;
}

const COMPLAINT_REASONS = [
    'Оскорбления',
    'Спам',
    'Недостоверная информация',
    'Нарушение правил',
    'Другое',
];

export function ChatPanel({ target, onOpenTarget, myUid, hideRail = false, title }: ChatPanelProps) {
    const requireAuth = useRequireAuth();
    const toast = useToast();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
    const [pendingRefs, setPendingRefs] = useState<ChatReference[]>([]);
    const [refUid, setRefUid] = useState('');
    const [refResolving, setRefResolving] = useState(false);
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const [friends, setFriends] = useState<SocialUserProfile[]>([]);
    const [communities, setCommunities] = useState<CommunitySummary[]>([]);
    const [trends, setTrends] = useState<TrendItem[]>([]);
    const [manualType, setManualType] = useState<ChatTargetType>('article');
    const [manualUid, setManualUid] = useState('');
    const [reportFor, setReportFor] = useState<ChatMessage | null>(null);
    const [reportReason, setReportReason] = useState(COMPLAINT_REASONS[0]);
    const [reportComment, setReportComment] = useState('');
    const bottomRef = useRef<HTMLDivElement>(null);

    const loadMessages = useCallback(async () => {
        if (!target) {
            setMessages([]);
            return;
        }
        setLoading(true);
        setError('');
        try {
            const res = await getChat(target.type, target.uid);
            setMessages(res.messages.slice().reverse());
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не удалось загрузить сообщения');
        } finally {
            setLoading(false);
        }
    }, [target]);

    useEffect(() => {
        loadMessages();
    }, [loadMessages]);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            const [f, c, t] = await Promise.allSettled([listFriends(), listCommunities(), getTrends()]);
            if (cancelled) return;
            if (f.status === 'fulfilled') setFriends(f.value.friends ?? []);
            if (c.status === 'fulfilled') setCommunities(c.value.communities ?? []);
            if (t.status === 'fulfilled') setTrends(t.value.by_comments ?? []);
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages]);

    const openManual = () => {
        const uid = manualUid.trim();
        if (!uid) {
            toast.error('Введите UID цели обсуждения');
            return;
        }
        onOpenTarget({ type: manualType, uid, label: uid });
        setManualUid('');
    };

    const handleSend = async () => {
        const text = input.trim();
        if ((!text && pendingRefs.length === 0) || !target) return;
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы отправлять сообщения')) return;
        setSending(true);
        try {
            const refs = pendingRefs.map((r) => ({ uid: r.uid, type: r.type }));
            const res = await sendMessage(target.type, target.uid, text, replyTo?.uid, refs);
            if (res.success && res.message) {
                setMessages((prev) => [...prev, res.message!]);
                setInput('');
                setReplyTo(null);
                setPendingRefs([]);
            } else {
                toast.error(res.error || 'Не удалось отправить сообщение');
            }
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка отправки');
        } finally {
            setSending(false);
        }
    };

    const addReference = async () => {
        const uid = refUid.trim();
        if (!uid) {
            toast.error('Введите UID блока или статьи');
            return;
        }
        if (pendingRefs.some((r) => r.uid === uid)) {
            toast.error('Эта ссылка уже прикреплена');
            return;
        }
        setRefResolving(true);
        try {
            const res = await resolveEntity(uid);
            if (!res.success || !res.entity) {
                toast.error('Не удалось найти блок/статью по UID');
                return;
            }
            const e = res.entity;
            if (e.type !== 'block' && e.type !== 'article' && e.type !== 'statement') {
                toast.error('Можно прикрепить только блок, статью или триплет');
                return;
            }
            setPendingRefs((prev) => [
                ...prev,
                {
                    uid: e.uid,
                    type: e.type as ChatReference['type'],
                    label: e.label,
                    block_type: e.block_type,
                    order: e.order,
                },
            ]);
            setRefUid('');
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка поиска');
        } finally {
            setRefResolving(false);
        }
    };

    const handleLike = async (msg: ChatMessage) => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы ставить лайки')) return;
        try {
            const res = await toggleLike(msg.uid);
            setMessages((prev) =>
                prev.map((m) =>
                    m.uid === msg.uid
                        ? { ...m, liked_by_me: !!res.liked, like_count: res.like_count ?? m.like_count }
                        : m,
                ),
            );
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка лайка');
        }
    };

    const handleCopy = async (msg: ChatMessage) => {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(msg.text);
            } else {
                const ta = document.createElement('textarea');
                ta.value = msg.text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
            toast.success('Сообщение скопировано');
        } catch {
            toast.error('Не удалось скопировать сообщение');
        }
    };

    const handleReport = async () => {
        if (!reportFor || !reportReason.trim()) return;
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы отправлять жалобы')) return;
        try {
            await createComplaint({
                target_type: reportFor.target_type,
                target_uid: reportFor.uid,
                reason: reportReason.trim(),
                comment: reportComment.trim(),
            });
            toast.success('Жалоба отправлена');
            setReportFor(null);
            setReportReason(COMPLAINT_REASONS[0]);
            setReportComment('');
        } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Ошибка отправки жалобы');
        }
    };

    const chatTitle = useMemo(() => {
        if (title) return title;
        if (!target) return 'Нет обсуждения';
        return target.label || `${TARGET_TYPE_LABELS[target.type]}: ${target.uid}`;
    }, [target, title]);

    return (
        <div className={hideRail ? s.chatPanelSingle : s.chatLayout}>
            {!hideRail && (
                <div className={s.chatRail}>
                <div className={s.railSection}>
                    <div className={s.railTitle}>Открыть обсуждение</div>
                    <div className={s.manualRow}>
                        <select
                            value={manualType}
                            onChange={(e) => setManualType(e.target.value as ChatTargetType)}
                            className={s.manualType}
                        >
                            {Object.entries(TARGET_TYPE_LABELS).map(([key, label]) => (
                                <option key={key} value={key}>{label}</option>
                            ))}
                        </select>
                        <input
                            className={s.manualUid}
                            value={manualUid}
                            onChange={(e) => setManualUid(e.target.value)}
                            placeholder="UID"
                        />
                        <button className={s.primaryBtn} onClick={openManual}><MdArrowForward /></button>
                    </div>
                </div>

                <div className={s.railSection}>
                    <div className={s.railTitle}>Друзья</div>
                    {friends.length === 0 && <div className={s.railEmpty}>Нет друзей</div>}
                    {friends.map((f) => (
                        <button
                            key={f.uid}
                            className={s.railItem}
                            onClick={() => onOpenTarget({ type: 'user', uid: f.uid, label: f.nickname || f.login })}
                        >
                            <MdChatBubbleOutline /> {f.nickname || f.login}
                        </button>
                    ))}
                </div>

                <div className={s.railSection}>
                    <div className={s.railTitle}>Сообщества</div>
                    {communities.length === 0 && <div className={s.railEmpty}>Нет сообществ</div>}
                    {communities.map((c) => (
                        <button
                            key={c.uid}
                            className={s.railItem}
                            onClick={() => onOpenTarget({ type: 'community', uid: c.uid, label: c.name })}
                        >
                            <MdChatBubbleOutline /> {c.name}
                        </button>
                    ))}
                </div>

                <div className={s.railSection}>
                    <div className={s.railTitle}>Тренды</div>
                    {trends.length === 0 && <div className={s.railEmpty}>Пока пусто</div>}
                    {trends.map((t, i) => (
                        <button
                            key={`${t.target_type}:${t.target_uid}:${i}`}
                            className={s.railItem}
                            onClick={() => onOpenTarget({ type: t.target_type, uid: t.target_uid, label: t.label })}
                        >
                            <MdLocalFireDepartment /> {t.label}
                        </button>
                    ))}
                </div>
            </div>
            )}

            <div className={s.chatWindow}>
                <div className={s.chatHeader}>
                    <span className={s.chatHeaderType}>{target ? TARGET_TYPE_LABELS[target.type] : ''}</span>
                    <span className={s.chatHeaderTitle}>{chatTitle}</span>
                </div>

                {error && <div className={s.errorBanner}>{error}</div>}

                <div className={s.messages}>
                    {loading && <div className={s.centerHint}>Загрузка…</div>}
                    {!loading && !target && (
                        <div className={s.centerHint}>Выберите цель обсуждения слева или укажите её UID</div>
                    )}
                    {!loading && target && messages.length === 0 && (
                        <div className={s.centerHint}>Сообщений пока нет — начните обсуждение</div>
                    )}
                    {messages.map((m) => (
                        <div key={m.uid} className={m.author_uid === myUid ? `${s.message} ${s.messageOwn}` : s.message}>
                            <div className={s.messageHead}>
                                <span className={s.messageAuthor}>{m.author_nickname || m.author_login || 'Пользователь'}</span>
                                <span className={s.messageTime}>{formatTime(m.created_at)}</span>
                            </div>
                            {m.parent_uid && <div className={s.messageParentHint}>ответ на сообщение</div>}
                            <div className={s.messageText}>
                                <MarkdownContent value={m.text} />
                            </div>
                            {m.references && m.references.length > 0 && (
                                <div className={s.messageRefs}>
                                    {m.references.map((r) => (
                                        <BlockCard key={r.uid} reference={r as BlockCardReference} />
                                    ))}
                                </div>
                            )}
                            <div className={s.messageActions}>
                                <button
                                    className={m.liked_by_me ? `${s.msgBtn} ${s.msgBtnActive}` : s.msgBtn}
                                    onClick={() => handleLike(m)}
                                    title={m.liked_by_me ? 'Убрать лайк' : 'Нравится'}
                                >
                                    <MdThumbUp /> {m.like_count}
                                </button>
                                <button
                                    className={s.msgBtnIcon}
                                    onClick={() => setReplyTo(m)}
                                    title="Ответить"
                                    aria-label="Ответить"
                                >
                                    <MdReply />
                                </button>
                                <button
                                    className={s.msgBtnIcon}
                                    onClick={() => void handleCopy(m)}
                                    title="Копировать сообщение"
                                    aria-label="Копировать сообщение"
                                >
                                    <MdContentCopy />
                                </button>
                                {m.reply_count > 0 && <span className={s.msgCount}>{m.reply_count} ответов</span>}
                                <button
                                    className={s.msgBtnIcon}
                                    onClick={() => setReportFor(m)}
                                    title="Пожаловаться"
                                    aria-label="Пожаловаться"
                                >
                                    <MdWarning />
                                </button>
                            </div>
                        </div>
                    ))}
                    <div ref={bottomRef} />
                </div>

                {reportFor && (
                    <div className={s.reportBox}>
                        <div className={s.reportTitle}>Жалоба на сообщение</div>
                        <select value={reportReason} onChange={(e) => setReportReason(e.target.value)} className={s.reportSelect}>
                            {COMPLAINT_REASONS.map((r) => <option key={r}>{r}</option>)}
                        </select>
                        <input
                            value={reportComment}
                            onChange={(e) => setReportComment(e.target.value)}
                            placeholder="Комментарий (необязательно)"
                            className={s.reportComment}
                        />
                        <div className={s.reportActions}>
                            <button className={s.primaryBtn} onClick={handleReport}>Отправить</button>
                            <button className={s.ghostBtn} onClick={() => setReportFor(null)}>Отмена</button>
                        </div>
                    </div>
                )}

                <div className={s.composer}>
                    {replyTo && (
                        <div className={s.replyBar}>
                            <span>Ответ на: {replyTo.text.slice(0, 60)}{replyTo.text.length > 60 ? '…' : ''}</span>
                            <button className={s.msgBtn} onClick={() => setReplyTo(null)}><MdClose /></button>
                        </div>
                    )}
                    {pendingRefs.length > 0 && (
                        <div className={s.pendingRefs}>
                            {pendingRefs.map((r) => (
                                <BlockCard
                                    key={r.uid}
                                    reference={r as BlockCardReference}
                                    onRemove={() => setPendingRefs((prev) => prev.filter((x) => x.uid !== r.uid))}
                                />
                            ))}
                        </div>
                    )}
                    <div className={s.refRow}>
                        <input
                            className={s.refUidInput}
                            value={refUid}
                            onChange={(e) => setRefUid(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    void addReference();
                                }
                            }}
                            placeholder="Прикрепить блок/статью по UID…"
                            disabled={!target || refResolving}
                        />
                        <button className={s.ghostBtn} onClick={() => void addReference()} disabled={!target || refResolving || !refUid.trim()}>
                            {refResolving ? '…' : <><MdLink /> Прикрепить</>}
                        </button>
                    </div>
                    <div className={s.composerRow}>
                        <textarea
                            className={s.composerInput}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    handleSend();
                                }
                            }}
                            placeholder="Сообщение… (Markdown поддерживается)"
                            disabled={!target || sending}
                        />
                        <button className={s.primaryBtn} onClick={handleSend} disabled={!target || sending || (!input.trim() && pendingRefs.length === 0)}>
                            {sending ? '…' : 'Отправить'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
