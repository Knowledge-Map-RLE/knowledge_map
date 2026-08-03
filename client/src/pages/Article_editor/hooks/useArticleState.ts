import { useState, useCallback, useRef, useEffect } from 'react';
import {
    getArticle, getArticleText, saveArticleText, saveStatements,
    saveBlocks, getBlocks, updateArticleTitle,
    parseText, parseTextStream, uploadArticleImage,
} from '../../../services/api/article_editor';
import { blocksToStatements, statementsToBlocks, blocksToText, statementsToResolvedText, uuid8Str } from '../Editor/blockConverter';
import type { KnowledgeArticle, KnowledgeStatement, SaveStatus, ArticleBlockData, BlockDataValue } from '../model';

function newBlockId(): string {
    return uuid8Str();
}

interface UseArticleStateResult {
    article: KnowledgeArticle | null;
    text: string;
    statements: KnowledgeStatement[];
    blocks: ArticleBlockData[];
    articleUuid: string | null;
    isParsing: boolean;
    parseProgress: { processed: number; total: number } | null;
    parseError: string | null;
    saveStatus: SaveStatus;
    notAnnotatedMessage: string | null;
    loadArticle: (docId: string) => Promise<void>;
    initNewArticle: (docId: string) => void;
    setText: (text: string) => void;
    addBlock: (typeNumber: number, initialData?: Record<string, BlockDataValue>) => void;
    updateBlock: (instanceId: string, fieldKey: string, value: BlockDataValue) => void;
    deleteBlock: (instanceId: string) => void;
    reorderBlocks: (fromIndex: number, toIndex: number) => void;
    triggerParse: (docId: string) => Promise<void>;
    save: (docId: string) => Promise<void>;
    uploadImage: (key: string, file: File) => Promise<string>;
}

export function useArticleState(): UseArticleStateResult {
    const [article, setArticle] = useState<KnowledgeArticle | null>(null);
    const [text, setTextState] = useState<string>('');
    const [blocks, setBlocks] = useState<ArticleBlockData[]>([]);
    const [statements, setStatements] = useState<KnowledgeStatement[]>([]);
    const [isParsing, setIsParsing] = useState(false);
    const [parseProgress, setParseProgress] = useState<{ processed: number; total: number } | null>(null);
    const [parseError, setParseError] = useState<string | null>(null);
    const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
    const [notAnnotatedMessage, setNotAnnotatedMessage] = useState<string | null>(null);
    const [articleUuid, setArticleUuid] = useState<string | null>(null);
    const parseTimerRef = useRef<number | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const lastDocIdRef = useRef<string>('');
    const skipBlocksSyncRef = useRef(false);
    const statementsCountRef = useRef(0);

    const blocksRef = useRef(blocks);
    blocksRef.current = blocks;

    const loadArticle = useCallback(async (docId: string) => {
        lastDocIdRef.current = docId;
        setParseError(null);
        setNotAnnotatedMessage(null);
        setTextState('');
        setBlocks([]);
        setStatements([]);
        setArticleUuid(docId);
        articleUuidRef.current = docId;

        let loadedArticle: KnowledgeArticle | null = null;
        // Аннотированную статью грузим двумя независимыми вызовами параллельно:
        // метаданные+стейтменты и структурные блоки. Текст не запрашиваем,
        // если есть блоки — он генерируется из блоков (statementsToResolvedText).
        try {
            const [articleResp, blocksResp] = await Promise.all([
                getArticle(docId).catch(() => null),
                getBlocks(docId).catch(() => null),
            ]);

            if (articleResp?.success && articleResp?.article) {
                loadedArticle = articleResp.article;
                setArticle(articleResp.article);

                const blockedStatuses = ['uploaded', 'uploading', 'pdf_to_markdown', 'processing', 'error'];
                const status = articleResp.article.processing_status;
                if (status && blockedStatuses.includes(status)) {
                    setNotAnnotatedMessage(
                        '\u0420\u0435\u0434\u0430\u043A\u0442\u0438\u0440\u043E\u0432\u0430\u043D\u0438\u0435 \u0434\u043E\u0441\u0442\u0443\u043F\u043D\u043E \u0442\u043E\u043B\u044C\u043A\u043E \u0434\u043B\u044F \u0430\u043D\u043D\u043E\u0442\u0438\u0440\u043E\u0432\u0430\u043D\u043D\u044B\u0445 \u0434\u043E\u043A\u0443\u043C\u0435\u043D\u0442\u043E\u0432. '
                        + '\u041F\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u0432 data_extraction \u0440\u0435\u0434\u0430\u043A\u0442\u043E\u0440 \u0434\u043B\u044F \u043F\u0440\u0438\u0432\u0435\u0434\u0435\u043D\u0438\u044F \u0442\u0435\u043A\u0441\u0442\u0430 \u0432 \u043A\u0430\u043D\u043E\u043D\u0438\u0447\u043D\u044B\u0439 \u0432\u0438\u0434.'
                    );
                    return;
                }
            }

            if (blocksResp?.success && Array.isArray(blocksResp.blocks) && blocksResp.blocks.length > 0) {
                const idMap = new Map<string, string>();
                for (const b of blocksResp.blocks as ArticleBlockData[]) {
                    if (b.instanceId && b.instanceId.startsWith('blk-')) {
                        idMap.set(b.instanceId, uuid8Str());
                    }
                }
                const loaded = (blocksResp.blocks as ArticleBlockData[]).map((b) => {
                    const newId = idMap.get(b.instanceId) || b.instanceId;
                    const data: Record<string, BlockDataValue> = {};
                    for (const [key, val] of Object.entries(b.data)) {
                        if (typeof val === 'string' && idMap.has(val)) {
                            data[key] = idMap.get(val)!;
                        } else {
                            data[key] = val;
                        }
                    }
                    return { ...b, instanceId: newId, data };
                });
                setBlocks(loaded);
                skipBlocksSyncRef.current = true;
                const existing = loadedArticle?.statements?.filter(
                    (s) => !(s.predicate === 'содержит' || (s.predicate === 'является' && s.object_text === 'научная статья')),
                );
                const derived = blocksToStatements(loaded, docId, existing);
                statementsCountRef.current = derived.length;
                setStatements(derived);
                setTextState(statementsToResolvedText(derived, loaded, docId, loadedArticle?.statements));
                return;
            }
        } catch (err) {
            console.warn('Article metadata not found (may be new document):', err);
        }

        // Блоков нет — грузим текст из markdown.
        let loadedText = '';
        try {
            const textResp = await getArticleText(docId);
            if (textResp?.success) loadedText = textResp.text || '';
        } catch { /* empty */ }

        if (!loadedText) {
            try {
                const { getDocumentAssets } = await import('../../../services/api/documents');
                const assets = await getDocumentAssets(docId);
                if (assets?.markdown) loadedText = assets.markdown;
            } catch { /* empty */ }
        }

        setTextState(loadedText);
        if (loadedArticle?.statements && loadedArticle.statements.length > 0) {
            skipBlocksSyncRef.current = true;
            setStatements(loadedArticle.statements);
            const converted = statementsToBlocks(loadedArticle.statements);
            if (converted.length > 0) {
                setBlocks(converted);
            }
        }
    }, []);

    const setText = useCallback((newText: string) => {
        setTextState(newText);
    }, []);

    const initNewArticle = useCallback((docId: string) => {
        setArticleUuid(docId);
        articleUuidRef.current = docId;
        setBlocks([]);
        setStatements([]);
        setTextState('');
    }, []);

    // Blocks → statements + text sync
    const articleUuidRef = useRef(articleUuid);
    articleUuidRef.current = articleUuid;

    const blocksSyncTimerRef = useRef<number | null>(null);

    useEffect(() => {
        return () => {
            if (blocksSyncTimerRef.current) {
                clearTimeout(blocksSyncTimerRef.current);
            }
        };
    }, []);

    useEffect(() => {
        if (skipBlocksSyncRef.current) {
            skipBlocksSyncRef.current = false;
            return;
        }
        if (blocks.length === 0) {
            if (statementsCountRef.current > 0) setStatements([]);
            return;
        }
        if (blocksSyncTimerRef.current) {
            clearTimeout(blocksSyncTimerRef.current);
        }
        blocksSyncTimerRef.current = window.setTimeout(() => {
            blocksSyncTimerRef.current = null;
            const currentArticleUuid = articleUuidRef.current;
            const prevStatements = statementsRef.current;
            const derived = blocksToStatements(blocks, currentArticleUuid ?? undefined, prevStatements);
            statementsCountRef.current = derived.length;
            setStatements(derived);
            const derivedText = statementsToResolvedText(derived, blocks, currentArticleUuid ?? undefined, prevStatements);
            setTextState(derivedText);
        }, 250);
    }, [blocks]);

    const addBlock = useCallback((typeNumber: number, initialData?: Record<string, BlockDataValue>) => {
        setBlocks((prev) => {
            const maxOrder = prev.length > 0 ? Math.max(...prev.map((b) => b.order)) : -1;
            const newBlock: ArticleBlockData = {
                instanceId: newBlockId(),
                blockType: typeNumber,
                data: initialData || {},
                order: maxOrder + 1,
            };
            return [...prev, newBlock];
        });
    }, []);

    const updateBlock = useCallback((instanceId: string, fieldKey: string, value: BlockDataValue) => {
        setBlocks((prev) =>
            prev.map((b) =>
                b.instanceId === instanceId
                    ? { ...b, data: { ...b.data, [fieldKey]: value } }
                    : b,
            ),
        );
    }, []);

    const deleteBlock = useCallback((instanceId: string) => {
        setBlocks((prev) => {
            const next = prev.filter((b) => b.instanceId !== instanceId);
            return next.map((b, i) => ({ ...b, order: i }));
        });
    }, []);

    const reorderBlocks = useCallback((fromIndex: number, toIndex: number) => {
        setBlocks((prev) => {
            const sorted = [...prev].sort((a, b) => a.order - b.order);
            const [moved] = sorted.splice(fromIndex, 1);
            sorted.splice(toIndex, 0, moved);
            return sorted.map((b, i) => ({ ...b, order: i }));
        });
    }, []);

    const textRef = useRef(text);
    textRef.current = text;
    const statementsRef = useRef(statements);
    statementsRef.current = statements;

    const triggerParse = useCallback(async (docId: string) => {
        setParseError(null);
        if (abortRef.current) abortRef.current.abort();
        if (parseTimerRef.current) clearTimeout(parseTimerRef.current);

        parseTimerRef.current = window.setTimeout(async () => {
            if (!docId && lastDocIdRef.current) docId = lastDocIdRef.current;
            const currentText = textRef.current;
            if (!currentText.trim()) {
                setStatements([]);
                return;
            }
            setIsParsing(true);
            setParseProgress(null);
            const controller = new AbortController();
            abortRef.current = controller;

            try {
                let gotResult = false;
                try {
                    await parseTextStream(currentText, docId, false, true, {
                        signal: controller.signal,
                        onProgress: (p) => setParseProgress(p),
                        onResult: (data) => {
                            if (data?.success && data?.statements) {
                                setStatements(data.statements);
                                gotResult = true;
                            } else {
                                setParseError(data?.message || '\u041F\u0430\u0440\u0441\u0438\u043D\u0433 \u043D\u0435 \u0434\u0430\u043B \u0440\u0435\u0437\u0443\u043B\u044C\u0442\u0430\u0442\u043E\u0432');
                                gotResult = true;
                            }
                        },
                        onError: (err) => setParseError(err),
                    });
                } catch { /* streaming not available */ }

                if (!gotResult) {
                    const result = await parseText(currentText, docId, false, true);
                    if (result?.success && result?.statements) {
                        setStatements(result.statements);
                    } else {
                        setParseError(result?.message || '\u041F\u0430\u0440\u0441\u0438\u043D\u0433 \u043D\u0435 \u0434\u0430\u043B \u0440\u0435\u0437\u0443\u043B\u044C\u0442\u0430\u0442\u043E\u0432');
                    }
                }
            } catch (err) {
                setParseError(err instanceof Error ? err.message : String(err));
            } finally {
                setIsParsing(false);
                setParseProgress(null);
            }
        }, 800);
    }, []);

    const save = useCallback(async (docId: string) => {
        const currentBlocks = blocksRef.current;
        const currentText = textRef.current;
        const currentArticleUuid = articleUuidRef.current;
        if (currentBlocks.length === 0 && !currentText) return;
        setSaveStatus('saving');
        try {
            if (currentBlocks.length > 0) {
                const t1Block = currentBlocks.find((b) => b.blockType === 1);
                const titleFromBlock = t1Block?.data?.title;
                const derivedStatements = blocksToStatements(currentBlocks, currentArticleUuid ?? undefined, statementsRef.current);
                const stmtPayload = derivedStatements.map((s) => ({
                    uid: s.id,
                    subject_text: s.subject_text,
                    predicate: s.predicate,
                    object_text: s.object_text,
                    subject_type: s.subject_type,
                    object_type: s.object_type,
                    type: s.type,
                    confidence: s.confidence,
                    sentence_text: '',
                    sort_order: 0,
                    sourceBlockId: s.sourceBlockId,
                }));
                const promises: Promise<any>[] = [
                    saveArticleText(docId, currentText),
                    saveBlocks(docId, currentBlocks),
                    saveStatements(docId, stmtPayload),
                ];
                if (titleFromBlock) {
                    promises.push(updateArticleTitle(docId, String(titleFromBlock)));
                }
                const results = await Promise.all(promises);
                if (!results[0]?.success) {
                    setSaveStatus('error');
                    return;
                }
                const saveResult = results[2];
                if (saveResult?.statement_ids) {
                    const ids: string[] = saveResult.statement_ids;
                    setStatements((prev) => prev.map((s, i) => ({
                        ...s,
                        id: ids[i] ?? s.id,
                    })));
                }
            } else {
                const textResult = await saveArticleText(docId, currentText);
                if (!textResult?.success) {
                    setSaveStatus('error');
                    return;
                }
                const currentStatements = statementsRef.current;
                if (currentStatements.length > 0) {
                    await saveStatements(docId, currentStatements);
                }
            }
            setSaveStatus('saved');
            setTimeout(() => setSaveStatus('idle'), 2000);
        } catch {
            setSaveStatus('error');
        }
    }, []);

    const uploadImage = useCallback(async (_key: string, file: File): Promise<string> => {
        const docId = articleUuidRef.current;
        if (!docId) throw new Error('Документ не выбран');
        const result = await uploadArticleImage(docId, file);
        if (!result?.success || !result?.object_key) {
            throw new Error('Не удалось загрузить изображение');
        }
        return result.object_key;
    }, []);

    return {
        article, text, statements, blocks, articleUuid,
        isParsing, parseProgress, parseError, saveStatus, notAnnotatedMessage,
        loadArticle, initNewArticle, setText, addBlock, updateBlock, deleteBlock, reorderBlocks,
        triggerParse, save, uploadImage,
    };
}
