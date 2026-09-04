import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type DragEvent,
    type ClipboardEvent,
} from 'react';
import {
    MdBugReport,
    MdClose,
    MdMinimize,
    MdAttachFile,
    MdSend,
    MdImage,
    MdDelete,
    MdList,
    MdArrowBack,
    MdCreate,
} from 'react-icons/md';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useToast } from '../../../shared/ui/Toast';
import { ModalPortal } from '../../../shared/ui/ModalPortal';
import {
    createTicket,
    sendFeedbackMessage,
    getFeedbackMessages,
    listFeedbackTickets,
    saveDraft as apiSaveDraft,
    getDraft,
    uploadFeedbackImage,
    feedbackImageUrl,
    type FeedbackTicket,
    type FeedbackMessage,
    type FeedbackStatus,
    STATUS_COLORS,
    STATUS_LABELS,
} from '../../../services/api/feedback';
import { collectBrowserInfo, getAppVersion } from '../../../shared/utils/browserInfo';
import s from './FeedbackChat.module.css';

interface FeedbackChatProps {
    onClose: () => void;
}

interface PendingImage {
    id: string;
    file: File;
    preview: string;
    s3Key: string;
    uploading: boolean;
}

type View = 'compose' | 'ticket';

function formatTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

let imageIdCounter = 0;
function nextImageId(): string {
    return `img_${++imageIdCounter}_${Date.now()}`;
}

export function FeedbackChat({ onClose }: FeedbackChatProps) {
    const requireAuth = useRequireAuth();
    const { error: toastError, success: toastSuccess } = useToast();

    const [isMinimized, setIsMinimized] = useState(false);
    const [view, setView] = useState<View>('compose');
    const [tickets, setTickets] = useState<FeedbackTicket[]>([]);
    const [ticket, setTicket] = useState<FeedbackTicket | null>(null);
    const [messages, setMessages] = useState<FeedbackMessage[]>([]);
    const [draftText, setDraftText] = useState('');
    const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
    const [sending, setSending] = useState(false);
    const [loading, setLoading] = useState(true);
    const [loadingTicket, setLoadingTicket] = useState(false);
    const [dragOver, setDragOver] = useState(false);

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const previewUrlsRef = useRef<string[]>([]);

    // ── Load draft + ticket list on mount ────────────────────────────────
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const [draftRes, listRes] = await Promise.allSettled([
                    getDraft(),
                    listFeedbackTickets(),
                ]);
                if (cancelled) return;

                if (draftRes.status === 'fulfilled' && draftRes.value.draft?.text) {
                    setDraftText(draftRes.value.draft.text);
                }
                if (listRes.status === 'fulfilled') {
                    setTickets(listRes.value.tickets ?? []);
                }
            } catch {
                /* не критично */
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    // ── Auto-save draft on blur ──────────────────────────────────────────
    const handleDraftBlur = useCallback(async () => {
        if (!draftText.trim()) return;
        try {
            await apiSaveDraft(draftText);
        } catch {
            /* не критично */
        }
    }, [draftText]);

    // ── Auto-resize textarea ─────────────────────────────────────────────
    useEffect(() => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
        }
    }, [draftText]);

    // ── Scroll to bottom on new messages ─────────────────────────────────
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Open a ticket ────────────────────────────────────────────────────
    const openTicket = useCallback(async (t: FeedbackTicket) => {
        setView('ticket');
        setTicket(t);
        setLoadingTicket(true);
        try {
            const res = await getFeedbackMessages(t.uid);
            setMessages(res.messages);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки сообщений');
            setMessages([]);
        } finally {
            setLoadingTicket(false);
        }
    }, [toastError]);

    const goToCompose = useCallback(() => {
        setView('compose');
        setTicket(null);
        setMessages([]);
    }, []);

    // ── Image handling ───────────────────────────────────────────────────
    const addFiles = useCallback(async (files: FileList | File[]) => {
        const imageFiles = Array.from(files).filter((f) =>
            f.type.startsWith('image/') && f.size <= 10 * 1024 * 1024,
        );

        for (const file of imageFiles) {
            const id = nextImageId();
            const preview = URL.createObjectURL(file);
            previewUrlsRef.current.push(preview);
            const entry: PendingImage = { id, file, preview, s3Key: '', uploading: true };
            setPendingImages((prev) => [...prev, entry]);

            try {
                const res = await uploadFeedbackImage(file);
                setPendingImages((prev) =>
                    prev.map((p) =>
                        p.id === id ? { ...p, s3Key: res.s3_key, uploading: false } : p,
                    ),
                );
            } catch (e) {
                toastError(e instanceof Error ? e.message : 'Ошибка загрузки изображения');
                setPendingImages((prev) => prev.filter((p) => p.id !== id));
            }
        }
    }, [toastError]);

    const removeImage = useCallback((id: string) => {
        setPendingImages((prev) => {
            const img = prev.find((p) => p.id === id);
            if (img) {
                URL.revokeObjectURL(img.preview);
                previewUrlsRef.current = previewUrlsRef.current.filter((u) => u !== img.preview);
            }
            return prev.filter((p) => p.id !== id);
        });
    }, []);

    useEffect(() => {
        return () => {
            previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
            previewUrlsRef.current = [];
        };
    }, []);

    // ── Drag & Drop ──────────────────────────────────────────────────────
    const handleDragOver = useCallback((e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragOver(true);
    }, []);

    const handleDragLeave = useCallback((e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragOver(false);
    }, []);

    const handleDrop = useCallback((e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragOver(false);
        if (e.dataTransfer.files.length > 0) {
            void addFiles(e.dataTransfer.files);
        }
    }, [addFiles]);

    // ── Paste from clipboard ─────────────────────────────────────────────
    const handlePaste = useCallback((e: ClipboardEvent) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        const imageFiles: File[] = [];
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.startsWith('image/')) {
                const file = items[i].getAsFile();
                if (file) imageFiles.push(file);
            }
        }
        if (imageFiles.length > 0) {
            e.preventDefault();
            void addFiles(imageFiles);
        }
    }, [addFiles]);

    // ── Send message ─────────────────────────────────────────────────────
    const handleSend = useCallback(async () => {
        if (!requireAuth('Войдите, чтобы отправить сообщение')) return;

        const text = draftText.trim();
        const uploadedKeys = pendingImages.filter((p) => p.s3Key).map((p) => p.s3Key);

        if (!text && uploadedKeys.length === 0) return;

        setSending(true);
        try {
            if (!ticket) {
                // Создаём новое обращение
                const res = await createTicket(
                    text,
                    collectBrowserInfo(),
                    getAppVersion(),
                    uploadedKeys,
                );
                const newTicket: FeedbackTicket = {
                    uid: res.ticket.uid,
                    user_uid: '',
                    status: res.ticket.status as FeedbackStatus,
                    created_at: res.ticket.created_at,
                    updated_at: res.ticket.created_at,
                };
                setTickets((prev) => [newTicket, ...prev]);
                setTicket(newTicket);
                setView('ticket');
                // Загружаем сообщения
                const msgRes = await getFeedbackMessages(res.ticket.uid);
                setMessages(msgRes.messages);
            } else {
                // Отправляем сообщение в существующее обращение
                const res = await sendFeedbackMessage(ticket.uid, text, uploadedKeys, 'user');
                setMessages((prev) => [...prev, res.message]);
                // Обновляем время в списке
                setTickets((prev) =>
                    prev.map((t) =>
                        t.uid === ticket.uid ? { ...t, updated_at: res.message.created_at } : t,
                    ),
                );
            }

            setDraftText('');
            setPendingImages([]);
            toastSuccess('Сообщение отправлено');
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка отправки');
        } finally {
            setSending(false);
        }
    }, [draftText, pendingImages, ticket, requireAuth, toastError, toastSuccess]);

    // ── Handle Enter key ─────────────────────────────────────────────────
    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
            }
        },
        [handleSend],
    );

    if (isMinimized) {
        return (
            <ModalPortal>
                <div className={s.minimized} onClick={() => setIsMinimized(false)}>
                    <MdBugReport className={s.minimizedIcon} />
                    {ticket && (
                        <span
                            className={s.statusDot}
                            style={{ background: STATUS_COLORS[ticket.status] || STATUS_COLORS.new }}
                        />
                    )}
                </div>
            </ModalPortal>
        );
    }

    return (
        <ModalPortal>
            <div className={s.backdrop} onClick={onClose} />
            <div
                className={s.chatWindow}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                {dragOver && (
                    <div className={s.dropOverlay}>
                        <MdImage className={s.dropIcon} />
                        <span>Перетащите изображение</span>
                    </div>
                )}

                {/* Header */}
                <div className={s.header}>
                    <div className={s.headerLeft}>
                        <MdBugReport className={s.headerIcon} />
                        <span className={s.headerTitle}>
                            {view === 'ticket' && ticket ? 'Обращение' : 'Баг? Пожелание?'}
                        </span>
                        {view === 'ticket' && ticket && (
                            <span
                                className={s.statusBadge}
                                style={{
                                    background: STATUS_COLORS[ticket.status] || STATUS_COLORS.new,
                                }}
                            >
                                {STATUS_LABELS[ticket.status] || 'Новое'}
                            </span>
                        )}
                    </div>
                    <div className={s.headerActions}>
                        {view === 'ticket' && tickets.length > 0 && (
                            <button
                                className={s.headerBtn}
                                onClick={goToCompose}
                                title="Мои обращения"
                            >
                                <MdList />
                            </button>
                        )}
                        <button
                            className={s.headerBtn}
                            onClick={() => setIsMinimized(true)}
                            title="Свернуть"
                        >
                            <MdMinimize />
                        </button>
                        <button className={s.headerBtn} onClick={onClose} title="Закрыть">
                            <MdClose />
                        </button>
                    </div>
                </div>

                {/* Body: list OR conversation */}
                {view === 'compose' ? (
                    <div className={s.body}>
                        {/* Ticket list */}
                        {loading ? (
                            <div className={s.state}>Загрузка…</div>
                        ) : (
                            <>
                                {tickets.length > 0 && (
                                    <div className={s.ticketList}>
                                        <div className={s.ticketListTitle}>Мои обращения</div>
                                        {tickets.map((t) => (
                                            <div
                                                key={t.uid}
                                                className={s.ticketItem}
                                                onClick={() => void openTicket(t)}
                                                role="button"
                                            >
                                                <div className={s.ticketItemTop}>
                                                    <span
                                                        className={s.ticketStatus}
                                                        style={{
                                                            background: STATUS_COLORS[t.status] || STATUS_COLORS.new,
                                                        }}
                                                    >
                                                        {STATUS_LABELS[t.status] || t.status}
                                                    </span>
                                                    <span className={s.ticketDate}>
                                                        {formatDateTime(t.created_at)}
                                                    </span>
                                                </div>
                                                <div className={s.ticketFooter}>
                                                    <span className={s.ticketViewBtn}>Открыть</span>
                                                    <MdArrowBack className={s.ticketArrow} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Compose */}
                                <div className={s.composeBlock}>
                                    <div className={s.composeTitle}>
                                        <MdCreate className={s.composeIcon} />
                                        Новое обращение
                                    </div>
                                    <div className={s.messages}>
                                        {messages.length === 0 && (
                                            <div className={s.state}>
                                                Опишите проблему или пожелание.<br />
                                                Изображения можно перетащить, вставить из буфера или прикрепить через скрепку.
                                            </div>
                                        )}
                                    </div>

                                    {/* Pending images preview */}
                                    {pendingImages.length > 0 && (
                                        <div className={s.imagePreviews}>
                                            {pendingImages.map((img) => (
                                                <div key={img.id} className={s.previewItem}>
                                                    <img src={img.preview} alt="" className={s.previewImg} />
                                                    {img.uploading && <div className={s.previewUploading}>…</div>}
                                                    <button
                                                        className={s.previewRemove}
                                                        onClick={() => removeImage(img.id)}
                                                        title="Удалить"
                                                    >
                                                        <MdDelete />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {/* Input */}
                                    <div className={s.inputArea}>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                                            multiple
                                            className="hidden"
                                            onChange={(e) => {
                                                if (e.target.files) void addFiles(e.target.files);
                                                e.target.value = '';
                                            }}
                                        />
                                        <button
                                            className={s.attachBtn}
                                            onClick={() => fileInputRef.current?.click()}
                                            title="Прикрепить изображение"
                                        >
                                            <MdAttachFile />
                                        </button>
                                        <textarea
                                            ref={textareaRef}
                                            className={s.textarea}
                                            value={draftText}
                                            onChange={(e) => setDraftText(e.target.value)}
                                            onBlur={handleDraftBlur}
                                            onKeyDown={handleKeyDown}
                                            onPaste={handlePaste}
                                            placeholder="Опишите проблему…"
                                            rows={1}
                                        />
                                        <button
                                            className={s.sendBtn}
                                            onClick={() => void handleSend()}
                                            disabled={sending || (!draftText.trim() && pendingImages.length === 0)}
                                            title="Отправить"
                                        >
                                            <MdSend />
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                ) : (
                    /* Conversation view */
                    <div className={s.body}>
                        <div className={s.messages}>
                            {loadingTicket ? (
                                <div className={s.state}>Загрузка…</div>
                            ) : messages.length === 0 ? (
                                <div className={s.state}>Сообщений пока нет</div>
                            ) : (
                                messages.map((m) => (
                                    <div
                                        key={m.uid}
                                        className={`${s.message} ${m.sender_type === 'admin' ? s.messageAdmin : s.messageUser}`}
                                    >
                                        <div className={s.messageSender}>
                                            {m.sender_type === 'admin' ? 'Поддержка' : 'Вы'}
                                        </div>
                                        <div className={s.messageText}>{m.text}</div>
                                        {m.image_s3_keys && m.image_s3_keys.length > 0 && (
                                            <div className={s.messageImages}>
                                                {m.image_s3_keys.map((key) => (
                                                    <img
                                                        key={key}
                                                        src={feedbackImageUrl(key)}
                                                        alt="Изображение"
                                                        className={s.messageImage}
                                                        loading="lazy"
                                                    />
                                                ))}
                                            </div>
                                        )}
                                        <div className={s.messageTime}>{formatTime(m.created_at)}</div>
                                    </div>
                                ))
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Pending images preview (reply) */}
                        {pendingImages.length > 0 && (
                            <div className={s.imagePreviews}>
                                {pendingImages.map((img) => (
                                    <div key={img.id} className={s.previewItem}>
                                        <img src={img.preview} alt="" className={s.previewImg} />
                                        {img.uploading && <div className={s.previewUploading}>…</div>}
                                        <button
                                            className={s.previewRemove}
                                            onClick={() => removeImage(img.id)}
                                            title="Удалить"
                                        >
                                            <MdDelete />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Input */}
                        <div className={s.inputArea}>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                                multiple
                                className="hidden"
                                onChange={(e) => {
                                    if (e.target.files) void addFiles(e.target.files);
                                    e.target.value = '';
                                }}
                            />
                            <button
                                className={s.attachBtn}
                                onClick={() => fileInputRef.current?.click()}
                                title="Прикрепить изображение"
                            >
                                <MdAttachFile />
                            </button>
                            <textarea
                                ref={textareaRef}
                                className={s.textarea}
                                value={draftText}
                                onChange={(e) => setDraftText(e.target.value)}
                                onBlur={handleDraftBlur}
                                onKeyDown={handleKeyDown}
                                onPaste={handlePaste}
                                placeholder="Ответ…"
                                rows={1}
                            />
                            <button
                                className={s.sendBtn}
                                onClick={() => void handleSend()}
                                disabled={sending || (!draftText.trim() && pendingImages.length === 0)}
                                title="Отправить"
                            >
                                <MdSend />
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </ModalPortal>
    );
}
