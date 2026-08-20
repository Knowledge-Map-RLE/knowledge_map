import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { estimateTokens } from '../../../services/api/agent';
import {
    listAIChats,
    createAIChat,
    getAIChatMessages,
    estimateAIChatMessage,
    streamAIChatMessage,
    type AIChatCostBreakdown,
    type AIChatMessage,
    type AIChatStreamUsage,
    type AIChatSummary,
} from '../../../services/api/aiChats';
import { getAgentArticleText, extractBlocksStream } from '../../../services/api/article_editor';
import { statementsToResolvedText } from './blockConverter';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import { useAuth, AUTH_GATE_MESSAGE } from '../../../entities/auth';
import type { KnowledgeStatement, ArticleBlockData } from '../model';
import styles from '../Article_editor.module.css';

interface ChatEntry extends AIChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    error?: boolean;
    estimatedCost?: string;
    actualCost?: string;
    tokens?: number;
    inputTokens?: number;
    cachedTokens?: number;
    toolTokens?: number;
    totalTokens?: number;
    costBreakdown?: AIChatCostBreakdown | null;
    cacheUsed?: boolean;
    pending?: boolean;
}

interface AgentChatProps {
    articleUuid?: string | null;
    blocks?: ArticleBlockData[];
    statements?: KnowledgeStatement[];
    text?: string;
    onExtracted?: (docId: string, blocks: ArticleBlockData[]) => Promise<void>;
}

const ESTIMATE_DEBOUNCE_MS = 400;
const DEFAULT_CONTEXT_LENGTH = 128000;

function formatCost(cost: string): string {
    const value = Number(cost || '0');
    if (!Number.isFinite(value)) return '0,00 ₽';
    return `${value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ₽`;
}

function sumCost(...parts: (string | undefined)[]): string {
    const total = parts.reduce((acc, p) => acc + (Number(p || '0') || 0), 0);
    return total.toFixed(4);
}

const AgentChat: React.FC<AgentChatProps> = ({ articleUuid, blocks, statements, text: editorText, onExtracted }) => {
    const requireAuth = useRequireAuth();
    const { isAuthenticated, requestLogin, requestRegister } = useAuth();
    const [messages, setMessages] = useState<ChatEntry[]>([]);
    const [chats, setChats] = useState<AIChatSummary[]>([]);
    const [chat, setChat] = useState<AIChatSummary | null>(null);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const [initializing, setInitializing] = useState(false);
    const [extracting, setExtracting] = useState(false);
    const [extractElapsed, setExtractElapsed] = useState(0);
    const [extractError, setExtractError] = useState<string | null>(null);
    const [attachEnabled, setAttachEnabled] = useState(false);
    const [attachSource, setAttachSource] = useState<string | null>(null);
    const [attachError, setAttachError] = useState<string | null>(null);
    const [serviceError, setServiceError] = useState<string | null>(null);
    const [estimate, setEstimate] = useState<{
        input: number;
        output: number;
        cost: string;
        breakdown?: AIChatCostBreakdown | null;
    } | null>(null);
    const [estimatePending, setEstimatePending] = useState(false);

    const controllerRef = useRef<AbortController | null>(null);
    const extractControllerRef = useRef<AbortController | null>(null);
    const nextIdRef = useRef(1);
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const attachTextRef = useRef<string>('');
    const copyTimerRef = useRef<number | null>(null);
    const estimateTimerRef = useRef<number | null>(null);
    const extractTimerRef = useRef<number | null>(null);
    const estimateSeqRef = useRef(0);
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const contextLength = DEFAULT_CONTEXT_LENGTH;

    const refreshChats = useCallback(async (): Promise<AIChatSummary[]> => {
        const list = await listAIChats(50);
        setChats(list);
        return list;
    }, []);

    const loadChatHistory = useCallback(
        async (current: AIChatSummary): Promise<void> => {
            const history = await getAIChatMessages(current.id, 100);
            setMessages(
                history.map((m) => ({
                    ...m,
                    id: m.id,
                    content: m.content,
                    tokens: m.tokens ?? undefined,
                    actualCost: m.cost ?? undefined,
                    inputTokens: m.input_tokens ?? undefined,
                    cachedTokens: m.cached_tokens ?? undefined,
                    toolTokens: m.tool_tokens ?? undefined,
                    totalTokens: m.total_tokens ?? undefined,
                    costBreakdown: m.cost_breakdown ?? null,
                    cacheUsed: m.cache_used ?? false,
                })),
            );
            nextIdRef.current = history.length + 1;
        },
        [],
    );

    const selectChat = useCallback(
        async (chatId: string): Promise<void> => {
            if (chat && chat.id === chatId) return;
            const current = chats.find((c) => c.id === chatId) ?? null;
            setChat(current);
            if (current) {
                await loadChatHistory(current);
            } else {
                setMessages([]);
                nextIdRef.current = 1;
            }
        },
        [chat, chats, loadChatHistory],
    );

    const ensureChat = useCallback(async (): Promise<AIChatSummary> => {
        if (chat) return chat;
        const created = await createAIChat('AI-чат');
        setChat(created);
        setChats((prev) => [created, ...prev]);
        return created;
    }, [chat]);

    const initChat = useCallback(async () => {
        if (!isAuthenticated) return;
        setInitializing(true);
        try {
            const chats = await listAIChats(50);
            setChats(chats);
            if (chats.length > 0) {
                const current = chats[0];
                setChat(current);
                await loadChatHistory(current);
            }
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : String(error));
        } finally {
            setInitializing(false);
        }
    }, [isAuthenticated, loadChatHistory]);

    useEffect(() => {
        if (!isAuthenticated) return;
        void initChat();
    }, [initChat, isAuthenticated]);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages, sending]);

    useEffect(() => () => {
        controllerRef.current?.abort();
        extractControllerRef.current?.abort();
        if (estimateTimerRef.current) window.clearTimeout(estimateTimerRef.current);
    }, []);

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

    const buildContextMessages = useCallback(
        (userContent: string): { role: string; content: string }[] => {
            return [
                ...messages.map((m) => ({ role: m.role, content: m.content })),
                { role: 'user', content: userContent },
            ];
        },
        [messages],
    );

    const buildUserContent = useCallback(
        (text: string): string => {
            if (attachEnabled && attachTextRef.current) {
                return (
                    `[Прикреплённая статья]\n${attachTextRef.current}\n\n` +
                    `[Вопрос по статье]\n${text}`
                );
            }
            return text;
        },
        [attachEnabled],
    );

    const scheduleEstimate = useCallback(
        (userContent: string) => {
            if (estimateTimerRef.current) window.clearTimeout(estimateTimerRef.current);
            if (!chat) return;
            if (!userContent.trim() && messages.length === 0 && !attachEnabled) {
                setEstimate(null);
                return;
            }
            estimateTimerRef.current = window.setTimeout(() => {
                const seq = ++estimateSeqRef.current;
                setEstimatePending(true);
                const fullContent = buildUserContent(userContent);
                const context = buildContextMessages(fullContent);
                estimateAIChatMessage(chat.id, context)
                    .then((result) => {
                        if (seq !== estimateSeqRef.current) return;
                        setEstimate({
                            input: result.estimated_input_tokens,
                            output: result.estimated_output_tokens,
                            cost: result.estimated_cost,
                            breakdown: result.cost_breakdown ?? null,
                        });
                    })
                    .catch(() => {
                        if (seq === estimateSeqRef.current) setEstimate(null);
                    })
                    .finally(() => {
                        if (seq === estimateSeqRef.current) setEstimatePending(false);
                    });
            }, ESTIMATE_DEBOUNCE_MS);
        },
        [chat, messages, buildContextMessages, buildUserContent, attachEnabled],
    );

    useEffect(() => {
        scheduleEstimate(input.trim());
    }, [input, chat, scheduleEstimate]);

    useEffect(() => {
        if (extracting) {
            setExtractElapsed(0);
            const started = Date.now();
            extractTimerRef.current = window.setInterval(() => {
                setExtractElapsed(Math.floor((Date.now() - started) / 1000));
            }, 1000);
            return () => {
                if (extractTimerRef.current != null) {
                    clearInterval(extractTimerRef.current);
                    extractTimerRef.current = null;
                }
            };
        }
        return undefined;
    }, [extracting]);

    const handleExtract = useCallback(async () => {
        if (!requireAuth()) return;
        if (!articleUuid) {
            setExtractError('\u041D\u0435\u0442 \u043E\u0442\u043A\u0440\u044B\u0442\u043E\u0439 \u0441\u0442\u0430\u0442\u044C\u0438');
            return;
        }
        if (extracting || sending) return;
        setExtractError(null);
        setExtracting(true);
        try {
            let text = '';
            try {
                text = await loadArticleText();
            } catch { /* fallback ниже */ }
            if (!text && editorText) text = editorText;
            if (!text) {
                setExtractError('\u041D\u0435\u0442 \u0442\u0435\u043A\u0441\u0442\u0430 \u0441\u0442\u0430\u0442\u044C\u0438 \u0434\u043B\u044F \u0438\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u044F');
                return;
            }
            const controller = new AbortController();
            extractControllerRef.current = controller;
            await extractBlocksStream(
                { text, docId: articleUuid, save: true },
                {
                    signal: controller.signal,
                    onStart: () => {},
                    onProgress: () => {},
                    onResult: async (data) => {
                        if (data?.success && Array.isArray(data.blocks)) {
                            await onExtracted?.(articleUuid, data.blocks);
                        } else {
                            setExtractError(data?.message || '\u0418\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u0435 \u043D\u0435 \u0434\u0430\u043B\u043E \u0440\u0435\u0437\u0443\u043B\u044C\u0442\u0430\u0442\u0430');
                        }
                    },
                    onCancelled: () => setExtractError('\u0418\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u0435 \u043E\u0442\u043C\u0435\u043D\u0435\u043D\u043E'),
                    onError: (err) => setExtractError(err),
                },
            );
        } catch (err) {
            if (err instanceof DOMException && err.name === 'AbortError') {
                setExtractError('\u0418\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u0435 \u043E\u0442\u043C\u0435\u043D\u0435\u043D\u043E');
            } else {
                setExtractError(err instanceof Error ? err.message : String(err));
            }
        } finally {
            setExtracting(false);
            extractControllerRef.current = null;
        }
    }, [articleUuid, extracting, sending, loadArticleText, editorText, onExtracted, requireAuth]);

    const handleStopExtract = useCallback(() => {
        extractControllerRef.current?.abort();
    }, []);

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
        if (!requireAuth()) return;
        const text = input.trim();
        if (!text || sending || extracting) return;

        setInput('');
        setServiceError(null);
        setEstimate(null);
        const userContent = buildUserContent(text);

        const userEntry: ChatEntry = {
            id: `local-${nextIdRef.current++}`,
            role: 'user',
            content: userContent,
        };
        const assistantEntry: ChatEntry = {
            id: `local-${nextIdRef.current++}`,
            role: 'assistant',
            content: '',
            pending: true,
        };
        setMessages((prev) => [...prev, userEntry, assistantEntry]);
        setSending(true);

        if (attachEnabled) {
            setAttachEnabled(false);
            attachTextRef.current = '';
            setAttachSource(null);
        }

        const controller = new AbortController();
        controllerRef.current = controller;

        try {
            const currentChat = await ensureChat();
            await streamAIChatMessage(currentChat.id, {
                content: userContent,
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
                onUsage: (usage: AIChatStreamUsage) => {
                    const bd = usage.cost_breakdown ?? null;
                    setMessages((prev) =>
                        prev.map((m) => {
                            if (m.id === userEntry.id) {
                                return {
                                    ...m,
                                    tokens: usage.prompt_tokens ?? usage.total_tokens,
                                    actualCost: bd
                                        ? sumCost(bd.input, bd.cached)
                                        : usage.cost,
                                    inputTokens: usage.prompt_tokens,
                                    cachedTokens: usage.cached_tokens,
                                    toolTokens: 0,
                                    totalTokens: usage.prompt_tokens,
                                    costBreakdown: bd
                                        ? {
                                              input: bd.input,
                                              cached: bd.cached,
                                              output: '0',
                                              tool: '0',
                                          }
                                        : null,
                                    cacheUsed: (usage.cached_tokens ?? 0) > 0,
                                };
                            }
                            if (m.id === assistantEntry.id) {
                                return {
                                    ...m,
                                    tokens:
                                        usage.completion_tokens || usage.total_tokens,
                                    actualCost: bd
                                        ? sumCost(bd.output, bd.tool)
                                        : usage.cost,
                                    inputTokens: 0,
                                    cachedTokens: 0,
                                    toolTokens: usage.tool_tokens,
                                    totalTokens:
                                        (usage.completion_tokens || 0) +
                                        (usage.tool_tokens || 0),
                                    costBreakdown: bd
                                        ? {
                                              input: '0',
                                              cached: '0',
                                              output: bd.output,
                                              tool: bd.tool,
                                          }
                                        : null,
                                    cacheUsed: false,
                                };
                            }
                            return m;
                        }),
                    );
                },
                onError: (error) => {
                    setServiceError(error.message);
                    setMessages((prev) =>
                        prev.map((m) =>
                            m.id === assistantEntry.id ? { ...m, error: true, pending: false } : m,
                        ),
                    );
                },
                onDone: () => {
                    setMessages((prev) =>
                        prev.map((m) =>
                            m.id === assistantEntry.id
                                ? { ...m, content: m.content.trim(), pending: false }
                                : m,
                        ),
                    );
                    setSending(false);
                    void refreshChats();
                },
            });
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : String(error));
            setMessages((prev) =>
                prev.map((m) =>
                    m.id === assistantEntry.id ? { ...m, error: true, pending: false } : m,
                ),
            );
            setSending(false);
        }
    }, [input, sending, messages, attachEnabled, extracting, requireAuth, ensureChat, refreshChats, buildUserContent]);

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
        setChat(null);
        setInput('');
        setServiceError(null);
        setSending(false);
        setEstimate(null);
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
                disabled={!articleUuid || sending || extracting}
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

    if (!isAuthenticated) {
        return (
            <div className={styles.agentChat}>
                <div className={styles.agentChatGate}>
                    <svg
                        className={styles.agentChatGateIcon}
                        width="40"
                        height="40"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    <div className={styles.agentChatGateTitle}>
                        {'\u0414\u043E\u0441\u0442\u0443\u043F \u043A AI-\u0430\u0433\u0435\u043D\u0442\u0443 \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0430\u0432\u0442\u043E\u0440\u0438\u0437\u0430\u0446\u0438\u0438'}
                    </div>
                    <p className={styles.agentChatGateText}>{AUTH_GATE_MESSAGE}</p>
                    <div className={styles.agentChatGateActions}>
                        <button className={styles.agentChatGateBtnPrimary} onClick={requestLogin}>
                            {'\u0412\u043E\u0439\u0442\u0438'}
                        </button>
                        <button className={styles.agentChatGateBtnSecondary} onClick={requestRegister}>
                            {'\u0417\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u043E\u0432\u0430\u0442\u044C\u0441\u044F'}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className={styles.agentChat}>
            <div className={styles.agentChatToolbar}>
                <select
                    className={styles.agentChatModelSelect}
                    value={chat?.id ?? ''}
                    onChange={(e) => {
                        if (!e.target.value) {
                            handleClear();
                        } else {
                            void selectChat(e.target.value);
                        }
                    }}
                    title="Выбрать чат"
                    disabled={sending || extracting}
                >
                    <option value="">
                        {'\u041D\u043E\u0432\u044B\u0439 \u0447\u0430\u0442'}
                    </option>
                    {chats.map((c) => (
                        <option key={c.id} value={c.id}>
                            {c.title || c.id}
                        </option>
                    ))}
                </select>
            </div>

            <div className={styles.agentChatExtractRow}>
                {extracting ? (
                    <>
                        <button
                            className={`${styles.agentChatExtractBtn} ${styles.agentChatExtractBtnStop}`}
                            onClick={handleStopExtract}
                            title="Прервать извлечение блоков"
                        >
                            {'\u2B15 \u041F\u0440\u0435\u0440\u0432\u0430\u0442\u044C'}
                        </button>
                        <div className={styles.agentChatExtractProgress}>
                            <div className={styles.agentChatExtractBar}>
                                <div className={`${styles.agentChatExtractFill} ${styles.agentChatExtractFillIndeterminate}`} />
                            </div>
                            <span className={styles.agentChatExtractLabel}>
                                {`\u0413\u0435\u043D\u0435\u0440\u0430\u0446\u0438\u044F... ${extractElapsed}\u00a0\u0441\u0435\u043A`}
                            </span>
                        </div>
                    </>
                ) : (
                    <button
                        className={styles.agentChatExtractBtn}
                        onClick={() => void handleExtract()}
                        disabled={!articleUuid || sending}
                        title="Извлечь структурные блоки из текста статьи через AI-модель"
                    >
                        {'\u2699 \u0418\u0437\u0432\u043B\u0435\u0447\u044C \u0431\u043B\u043E\u043A\u0438 \u0438\u0437 \u0441\u0442\u0430\u0442\u044C\u0438'}
                    </button>
                )}
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

            {initializing && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText}>
                        {'\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430 \u0447\u0430\u0442\u0430...'}
                    </span>
                </div>
            )}

            {attachError && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText} title={attachError}>
                        {attachError}
                    </span>
                </div>
            )}

            {extractError && (
                <div className={styles.agentChatErrorBanner}>
                    <span className={styles.agentChatErrorText} title={extractError}>
                        {'\u041E\u0448\u0438\u0431\u043A\u0430 \u0438\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u044F: '}
                        {extractError}
                    </span>
                    {extracting && (
                        <button
                            className={styles.agentChatRetryBtn}
                            onClick={handleStopExtract}
                        >
                            {'\u041F\u0440\u0435\u0440\u0432\u0430\u0442\u044C'}
                        </button>
                    )}
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
                {messages.length === 0 && !sending && !extracting && !initializing && (
                    <div className={styles.agentChatEmpty}>
                        {'\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u0432\u043E\u043F\u0440\u043E\u0441 AI-\u0430\u0433\u0435\u043D\u0442\u0443 \u043E\u0431 \u0441\u0442\u0430\u0442\u044C\u0435'}
                    </div>
                )}
                {messages.length === 0 && extracting && (
                    <div className={styles.agentChatEmpty}>
                        {'\u0418\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u0435 \u0441\u0442\u0440\u0443\u043A\u0442\u0443\u0440\u043D\u044B\u0445 \u0431\u043B\u043E\u043A\u043E\u0432 \u0438\u0437 \u0441\u0442\u0430\u0442\u044C\u0438...'}
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
                                    <span
                                        className={styles.agentChatBubbleTokens}
                                        title={
                                            entry.role === 'user'
                                                ? `вход: ${entry.tokens.toLocaleString('ru-RU')}${(entry.cachedTokens ?? 0) > 0 ? ` · кэш: ${(entry.cachedTokens ?? 0).toLocaleString('ru-RU')}` : ''}`
                                                : `выход: ${entry.tokens.toLocaleString('ru-RU')}${(entry.toolTokens ?? 0) > 0 ? ` · инструменты: ${(entry.toolTokens ?? 0).toLocaleString('ru-RU')}` : ''}`
                                        }
                                    >
                                        {entry.role === 'user' ? '\u0432\u0445\u043E\u0434: ' : '\u0432\u044B\u0445\u043E\u0434: '}
                                        {entry.tokens.toLocaleString('ru-RU')}{' \u0442\u043E\u043A.'}
                                    </span>
                                )}
                                {typeof entry.actualCost === 'string' && entry.actualCost && (
                                    <span
                                        className={styles.agentChatBubbleTokens}
                                        title={
                                            entry.costBreakdown
                                                ? entry.role === 'user'
                                                    ? `вход: ${formatCost(entry.costBreakdown.input)}${entry.costBreakdown.cached !== '0' ? ` · кэш: ${formatCost(entry.costBreakdown.cached)}` : ''}`
                                                    : `выход: ${formatCost(entry.costBreakdown.output)}${entry.costBreakdown.tool !== '0' ? ` · инструменты: ${formatCost(entry.costBreakdown.tool)}` : ''}`
                                                : undefined
                                        }
                                    >
                                        {'\u0440\u0430\u0441\u0445\u043E\u0434: '}
                                        {formatCost(entry.actualCost)}
                                    </span>
                                )}
                                {entry.role === 'user' && entry.cacheUsed && (entry.cachedTokens ?? 0) > 0 && (
                                    <span className={styles.agentChatBubbleCache} title="Использован кэш входных токенов">
                                        {'\u043A\u044D\u0448: '}
                                        {(entry.cachedTokens ?? 0).toLocaleString('ru-RU')}
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

            {estimate && !sending && (
                <div className={styles.agentChatEstimate}>
                    <span className={styles.agentChatEstimateLabel}>
                        {'\u041E\u0446\u0435\u043D\u043A\u0430 \u0441\u0442\u043E\u0438\u043C\u043E\u0441\u0442\u0438: '}
                        {formatCost(estimate.cost)}
                        <span
                            className={styles.agentChatEstimateDetail}
                            title={
                                estimate.breakdown
                                    ? `вход: ${formatCost(estimate.breakdown.input)} · выход: ${formatCost(estimate.breakdown.output)}`
                                    : undefined
                            }
                        >
                            {` (~${estimate.input.toLocaleString('ru-RU')} \u0432\u0445. + ${estimate.output.toLocaleString('ru-RU')} \u0432\u044B\u0445. \u0442\u043E\u043A.)`}
                        </span>
                    </span>
                    {estimatePending && (
                        <span className={styles.agentChatEstimatePending}>{'\u2026'}</span>
                    )}
                </div>
            )}

            <div className={styles.agentChatInputRow}>
                <textarea
                    className={styles.agentChatTextarea}
                    rows={1}
                    value={input}
                    placeholder={'\u0421\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0435 \u0430\u0433\u0435\u043D\u0442\u0443...'}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={sending || extracting}
                />
                {sending || extracting ? (
                    <button
                        className={`${styles.agentChatSendBtn} ${styles.agentChatSendBtnStop}`}
                        onClick={sending ? handleStop : handleStopExtract}
                        title={sending ? '\u041F\u0440\u0435\u0440\u0432\u0430\u0442\u044C \u0433\u0435\u043D\u0435\u0440\u0430\u0446\u0438\u044E' : '\u041F\u0440\u0435\u0440\u0432\u0430\u0442\u044C \u0438\u0437\u0432\u043B\u0435\u0447\u0435\u043D\u0438\u0435'}
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
