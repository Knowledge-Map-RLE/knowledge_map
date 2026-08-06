import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    getAgentModels,
    streamAgentChat,
    estimateTokens,
    type AgentMessage,
    type AgentModel,
    type AgentUsage,
} from '../../../services/api/agent';
import { getAgentArticleText } from '../../../services/api/article_editor';
import { statementsToResolvedText } from './blockConverter';
import type { KnowledgeStatement, ArticleBlockData } from '../model';
import styles from '../Article_editor.module.css';

interface ChatEntry {
    id: number;
    role: 'user' | 'assistant';
    content: string;
    error?: boolean;
    tokens?: number;
}

interface AgentChatProps {
    articleUuid?: string | null;
    blocks?: ArticleBlockData[];
    statements?: KnowledgeStatement[];
}

const AgentChat: React.FC<AgentChatProps> = ({ articleUuid, blocks, statements }) => {
    const [messages, setMessages] = useState<ChatEntry[]>([]);
    const [input, setInput] = useState('');
    const [models, setModels] = useState<AgentModel[]>([]);
    const [model, setModel] = useState('');
    const [sending, setSending] = useState(false);
    const [attachEnabled, setAttachEnabled] = useState(false);
    const [attachSource, setAttachSource] = useState<string | null>(null);
    const [attachError, setAttachError] = useState<string | null>(null);
    const [serviceError, setServiceError] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    const controllerRef = useRef<AbortController | null>(null);
    const nextIdRef = useRef(1);
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const attachTextRef = useRef<string>('');
    const copyTimerRef = useRef<number | null>(null);
    const [copiedId, setCopiedId] = useState<number | null>(null);

    const contextLength = useMemo(() => {
        const entry = models.find((m) => m.id === model);
        return entry?.context_length || 32000;
    }, [models, model]);

    const loadModels = useCallback(async () => {
        setLoadError(null);
        try {
            const list = await getAgentModels();
            setModels(list);
            setModel((prev) => {
                if (prev) return prev;
                const configured = list.find((m) => m.configured);
                return (configured ?? list[0])?.id ?? '';
            });
        } catch (error) {
            setLoadError(error instanceof Error ? error.message : String(error));
            setModels([]);
        }
    }, []);

    useEffect(() => {
        void loadModels();
    }, [loadModels]);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages, sending]);

    useEffect(() => () => controllerRef.current?.abort(), []);

    const loadArticleText = useCallback(async (): Promise<string> => {
        if (!articleUuid) return '';
        const result = await getAgentArticleText(articleUuid);
        if (!result.success) throw new Error('Не удалось получить текст статьи');
        if (result.text) return result.text;
        if (result.source === 'stored' || result.source === 'doi' || result.source === 'docling') {
            return result.text || '';
        }
        if (blocks && statements) {
            return statementsToResolvedText(statements, blocks, articleUuid ?? undefined);
        }
        return '';
    }, [articleUuid, blocks, statements]);

    const handleToggleAttach = useCallback(async () => {
        if (attachEnabled) {
            setAttachEnabled(false);
            attachTextRef.current = '';
            setAttachSource(null);
            setAttachError(null);
            return;
        }
        if (!articleUuid) {
            setAttachError('Текст статьи недоступен (нет открытой статьи)');
            return;
        }
        setAttachError(null);
        try {
            const text = await loadArticleText();
            if (!text) {
                setAttachError('Текст статьи недоступен: нет текстовой версии, триплетов или DOI');
                return;
            }
            attachTextRef.current = text;
            setAttachSource('статья');
            setAttachEnabled(true);
        } catch (error) {
            setAttachError(error instanceof Error ? error.message : String(error));
        }
    }, [attachEnabled, articleUuid, loadArticleText]);

    const attachedTokens = useMemo(() => estimateTokens(attachTextRef.current), [attachEnabled]);

    const inputTokens = useMemo(() => estimateTokens(input), [input]);

    const usedTokens = inputTokens + (attachEnabled ? attachedTokens : 0);

    const tokenRatio = contextLength > 0 ? Math.min(100, (usedTokens / contextLength) * 100) : 0;

    const tokenColor =
        tokenRatio >= 90
            ? styles.agentChatTokensDanger
            : tokenRatio >= 70
                ? styles.agentChatTokensWarn
                : '';

    const handleSend = useCallback(async () => {
        const text = input.trim();
        if (!text || sending) return;

        setInput('');
        setServiceError(null);

        let userContent = text;
        if (attachEnabled && attachTextRef.current) {
            userContent =
                `[Прикреплённая статья]\n${attachTextRef.current}\n\n` +
                `[Вопрос по статье]\n${text}`;
        }

        const userEntry: ChatEntry = { id: nextIdRef.current++, role: 'user', content: userContent, tokens: estimateTokens(userContent) };
        const assistantEntry: ChatEntry = { id: nextIdRef.current++, role: 'assistant', content: '' };
        setMessages((prev) => [...prev, userEntry, assistantEntry]);
        setSending(true);

        // Контекст статьи уже включён в сообщение и передан модели — снимаем галочку,
        // чтобы при следующих запросах статья не грузилась повторно.
        if (attachEnabled) {
            setAttachEnabled(false);
            attachTextRef.current = '';
            setAttachSource(null);
        }

        const history: AgentMessage[] = messages
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({ role: m.role, content: m.content }));
        history.push({ role: 'user', content: userContent });

        const controller = new AbortController();
        controllerRef.current = controller;

        await streamAgentChat({
            messages: history,
            model: model || undefined,
            signal: controller.signal,
            onChunk: (chunk) => {
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantEntry.id
                            ? { ...m, content: (m.content + chunk).replace(/^\s+/, '') }
                            : m,
                    ),
                );
            },
            onUsage: (usage: AgentUsage) => {
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantEntry.id
                            ? { ...m, tokens: usage.completion_tokens || usage.total_tokens }
                            : m,
                    ),
                );
            },
            onError: (error) => {
                setServiceError(error.message);
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantEntry.id ? { ...m, error: true } : m,
                    ),
                );
            },
            onDone: () => {
                setMessages((prev) =>
                    prev.map((m) =>
                        m.id === assistantEntry.id ? { ...m, content: m.content.trim() } : m,
                    ),
                );
                setSending(false);
            },
        });
    }, [input, sending, messages, model, attachEnabled]);

    const handleStop = useCallback(() => {
        controllerRef.current?.abort();
    }, []);

    const handleCopy = useCallback(async (entry: ChatEntry) => {
        if (!entry.content) return;
        try {
            await navigator.clipboard.writeText(entry.content);
        } catch {
            const ta = document.createElement('textarea');
            ta.value = entry.content;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
        setCopiedId(entry.id);
        if (copyTimerRef.current) window.clearTimeout(copyTimerRef.current);
        copyTimerRef.current = window.setTimeout(() => setCopiedId(null), 1500);
    }, []);

    const handleClear = useCallback(() => {
        controllerRef.current?.abort();
        setMessages([]);
        setInput('');
        setServiceError(null);
        setLoadError(null);
        setSending(false);
        setCopiedId(null);
        setAttachEnabled(false);
        attachTextRef.current = '';
        setAttachSource(null);
        setAttachError(null);
    }, []);

    const handleKeyDown = useCallback(
        (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
            }
        },
        [handleSend],
    );

    const attachBlock = (
        <label className={styles.agentChatAttach}>
            <input
                type="checkbox"
                checked={attachEnabled}
                onChange={() => void handleToggleAttach()}
                disabled={!articleUuid || sending}
            />
            <span className={styles.agentChatAttachLabel}>
                {'\u041F\u0440\u0438\u043A\u0440\u0435\u043F\u0438\u0442\u044C \u0441\u0442\u0430\u0442\u044C\u044E'}
                {attachSource ? ` (${attachSource})` : ''}
            </span>
            {attachError && (
                <span className={styles.agentChatAttachError} title={attachError}>
                    {'\u26A0'}
                </span>
            )}
        </label>
    );

    return (
        <div className={styles.agentChat}>
            <div className={styles.agentChatToolbar}>
                <select
                    className={styles.agentChatModelSelect}
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    title="Модель AI"
                >
                    {models.length === 0 && <option value="">по умолчанию</option>}
                    {models.map((m) => (
                        <option key={m.id} value={m.id}>
                            {m.id}
                        </option>
                    ))}
                </select>
                <button
                    className={styles.agentChatClearBtn}
                    onClick={handleClear}
                    disabled={messages.length === 0 && !sending}
                    title="Очистить чат"
                >
                    {'\u0421\u0431\u0440\u043E\u0441'}
                </button>
            </div>

            <div className={styles.agentChatMetaRow}>
                <div className={styles.agentChatAttachRow}>{attachBlock}</div>
                <div
                    className={[styles.agentChatTokens, tokenColor].filter(Boolean).join(' ')}
                    title={`Приблизительно ${usedTokens.toLocaleString('ru-RU')} из ${contextLength.toLocaleString('ru-RU')} токенов`}
                >
                    {usedTokens.toLocaleString('ru-RU')} / {contextLength.toLocaleString('ru-RU')}
                </div>
            </div>

            {loadError && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText} title={loadError}>
                        {'\u041D\u0435 \u0443\u0434\u0430\u043B\u043E\u0441\u044C \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C \u043C\u043E\u0434\u0435\u043B\u0438: '}
                        {loadError}
                    </span>
                    <button
                        className={styles.agentChatRetryBtn}
                        onClick={() => void loadModels()}
                    >
                        {'\u041F\u043E\u0432\u0442\u043E\u0440\u0438\u0442\u044C'}
                    </button>
                </div>
            )}

            {attachError && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText} title={attachError}>
                        {attachError}
                    </span>
                </div>
            )}

            {serviceError && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText} title={serviceError}>
                        {'\u041E\u0448\u0438\u0431\u043A\u0430 \u0430\u0433\u0435\u043D\u0442\u0430: '}
                        {serviceError}
                    </span>
                </div>
            )}

            <div className={styles.agentChatMessages} ref={scrollRef}>
                {messages.length === 0 && !sending && (
                    <div className={styles.agentChatEmpty}>
                        {'\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u0432\u043E\u043F\u0440\u043E\u0441 AI-\u0430\u0433\u0435\u043D\u0442\u0443 \u043E\u0431 \u0441\u0442\u0430\u0442\u044C\u0435'}
                    </div>
                )}
                {messages.map((entry) => (
                    <div
                        key={entry.id}
                        className={[
                            styles.agentChatBubble,
                            entry.role === 'user'
                                ? styles.agentChatBubbleUser
                                : styles.agentChatBubbleAssistant,
                            entry.error ? styles.agentChatBubbleError : '',
                        ]
                            .filter(Boolean)
                            .join(' ')}
                    >
                        {entry.role === 'assistant' && entry.content === '' && !entry.error ? (
                            <div className={styles.agentChatTyping} aria-label="Генерация ответа">
                                <span />
                                <span />
                                <span />
                            </div>
                        ) : (
                            entry.content
                        )}
                        {entry.role === 'assistant' &&
                            entry.error &&
                            entry.content === '' && (
                                <span className={styles.agentChatBubbleMeta}>
                                    {'\u043D\u0435 \u0443\u0434\u0430\u043B\u043E\u0441\u044C \u043F\u043E\u043B\u0443\u0447\u0438\u0442\u044C \u043E\u0442\u0432\u0435\u0442'}
                                </span>
                            )}
                        {entry.content && (
                            <div className={styles.agentChatBubbleFoot}>
                                {typeof entry.tokens === 'number' && entry.tokens >= 0 && (
                                    <span className={styles.agentChatBubbleTokens}>
                                        {entry.tokens.toLocaleString('ru-RU')} ток.
                                    </span>
                                )}
                                <button
                                    className={styles.agentChatCopyBtn}
                                    onClick={() => void handleCopy(entry)}
                                    title="Скопировать сообщение"
                                >
                                    {copiedId === entry.id ? (
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                            <polyline points="20 6 9 17 4 12" />
                                        </svg>
                                    ) : (
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                                        </svg>
                                    )}
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <div className={styles.agentChatInputRow}>
                <textarea
                    className={styles.agentChatTextarea}
                    rows={1}
                    value={input}
                    placeholder={'\u0421\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0435 \u0430\u0433\u0435\u043D\u0442\u0443...'}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={sending}
                />
                {sending ? (
                    <button
                        className={`${styles.agentChatSendBtn} ${styles.agentChatSendBtnStop}`}
                        onClick={handleStop}
                    >
                        {'\u2B15'}
                    </button>
                ) : (
                    <button
                        className={styles.agentChatSendBtn}
                        onClick={() => void handleSend()}
                        disabled={!input.trim()}
                    >
                        {'\u041E\u0442\u043F\u0440\u0430\u0432\u0438\u0442\u044C'}
                    </button>
                )}
            </div>
        </div>
    );
};

export default AgentChat;
