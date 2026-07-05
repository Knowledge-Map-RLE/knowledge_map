import { useState, useCallback, useRef } from 'react';
import {
    getArticle, getArticleText, saveArticleText, saveStatements, parseText, parseTextStream,
} from '../../../services/api/article_editor';
import type { KnowledgeArticle, KnowledgeStatement, SaveStatus } from '../model';

interface UseArticleStateResult {
    article: KnowledgeArticle | null;
    text: string;
    statements: KnowledgeStatement[];
    isParsing: boolean;
    parseProgress: { processed: number; total: number } | null;
    parseError: string | null;
    saveStatus: SaveStatus;
    notAnnotatedMessage: string | null;
    loadArticle: (docId: string) => Promise<void>;
    setText: (text: string) => void;
    triggerParse: (docId: string) => Promise<void>;
    save: (docId: string) => Promise<void>;
}

export function useArticleState(): UseArticleStateResult {
    const [article, setArticle] = useState<KnowledgeArticle | null>(null);
    const [text, setTextState] = useState<string>('');
    const [statements, setStatements] = useState<KnowledgeStatement[]>([]);
    const [isParsing, setIsParsing] = useState(false);
    const [parseProgress, setParseProgress] = useState<{ processed: number; total: number } | null>(null);
    const [parseError, setParseError] = useState<string | null>(null);
    const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
    const [notAnnotatedMessage, setNotAnnotatedMessage] = useState<string | null>(null);
    const parseTimerRef = useRef<number | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const lastDocIdRef = useRef<string>('');

    const loadArticle = useCallback(async (docId: string) => {
        lastDocIdRef.current = docId;
        setParseError(null);
        setNotAnnotatedMessage(null);
        setTextState('');
        setStatements([]);
        // Пробуем получить статью (метаданные + statement'ы). Если 404 — не фатально.
        try {
            const resp = await getArticle(docId);
            if (resp?.success && resp?.article) {
                setArticle(resp.article);
                setStatements(resp.article.statements || []);

                // Блокируем только документы, которые ещё в обработке или с ошибкой
                const blockedStatuses = ['uploaded', 'uploading', 'pdf_to_markdown', 'processing', 'error'];
                const status = resp.article.processing_status;
                if (status && blockedStatuses.includes(status)) {
                    setNotAnnotatedMessage(
                        'Редактирование доступно только для аннотированных документов. '
                        + 'Перейдите в data_extraction редактор для приведения текста в каноничный вид.'
                    );
                    return;
                }
            }
        } catch (err) {
            console.warn('Article metadata not found (may be new document):', err);
            setArticle(null);
            setStatements([]);
        }
        // Текст грузим только для аннотированных документов
        let loadedText = '';
        try {
            const textResp = await getArticleText(docId);
            if (textResp?.success) {
                loadedText = textResp.text || '';
            }
        } catch (err) {
            console.warn('getArticleText failed:', err instanceof Error ? err.message : String(err));
        }
        if (!loadedText) {
            try {
                const { getDocumentAssets } = await import('../../../services/api/documents');
                const assets = await getDocumentAssets(docId);
                if (assets?.markdown) {
                    loadedText = assets.markdown;
                } else {
                    console.warn('getDocumentAssets returned no markdown:', assets);
                }
            } catch (err) {
                console.error('Failed to load text from data_extraction:', err);
            }
        }
        setTextState(loadedText);
    }, []);

    const setText = useCallback((newText: string) => {
        setTextState(newText);
    }, []);

    const textRef = useRef(text);
    textRef.current = text;
    const statementsRef = useRef(statements);
    statementsRef.current = statements;

    const triggerParse = useCallback(async (docId: string) => {
        setParseError(null);
        if (abortRef.current) {
            abortRef.current.abort();
        }
        if (parseTimerRef.current) {
            clearTimeout(parseTimerRef.current);
        }
        parseTimerRef.current = window.setTimeout(async () => {
            if (!docId && lastDocIdRef.current) {
                docId = lastDocIdRef.current;
            }
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
                // try streaming parse first
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
                                setParseError(data?.message || 'Парсинг не дал результатов');
                                gotResult = true;
                            }
                        },
                        onError: (err) => {
                            setParseError(err);
                        },
                    });
                } catch { /* streaming not available */ }

                if (!gotResult) {
                    // Fallback: regular parse
                    const result = await parseText(currentText, docId, false, true);
                    if (result?.success && result?.statements) {
                        setStatements(result.statements);
                    } else {
                        setParseError(result?.message || 'Парсинг не дал результатов');
                    }
                }
            } catch (err) {
                setParseError(err instanceof Error ? err.message : String(err));
                console.error('Parse failed:', err);
            } finally {
                setIsParsing(false);
                setParseProgress(null);
            }
        }, 800);
    }, []);

    const save = useCallback(async (docId: string) => {
        const currentText = textRef.current;
        const currentStatements = statementsRef.current;
        setSaveStatus('saving');
        try {
            const result = await saveArticleText(docId, currentText);
            if (!result?.success) {
                setSaveStatus('error');
                return;
            }
            if (currentStatements.length > 0) {
                await saveStatements(docId, currentStatements);
            }
            setSaveStatus('saved');
            setTimeout(() => setSaveStatus('idle'), 2000);
        } catch (err) {
            console.error('Save failed:', err);
            setSaveStatus('error');
        }
    }, []);

    return {
        article, text, statements, isParsing, parseProgress, parseError, saveStatus, notAnnotatedMessage,
        loadArticle, setText, triggerParse, save,
    };
}
