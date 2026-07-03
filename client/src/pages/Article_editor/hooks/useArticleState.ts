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
    const parseTimerRef = useRef<number | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const lastDocIdRef = useRef<string>('');

    const loadArticle = useCallback(async (docId: string) => {
        lastDocIdRef.current = docId;
        setParseError(null);
        // Пробуем получить статью (метаданные + statement'ы). Если 404 — не фатально.
        try {
            const resp = await getArticle(docId);
            if (resp?.success && resp?.article) {
                setArticle(resp.article);
                setStatements(resp.article.statements || []);
            }
        } catch (err) {
            console.warn('Article metadata not found (may be new document):', err);
            setArticle(null);
            setStatements([]);
        }
        // Текст грузим всегда. Пробуем article_editor, затем data_extraction как fallback.
        let loadedText = '';
        try {
            const textResp = await getArticleText(docId);
            if (textResp?.success) {
                loadedText = textResp.text || '';
            }
        } catch {
            console.warn('Article text via article_editor failed, trying data_extraction...');
        }
        if (!loadedText) {
            try {
                const { getDocumentAssets } = await import('../../../services/api/documents');
                const assets = await getDocumentAssets(docId);
                if (assets?.markdown) {
                    loadedText = assets.markdown;
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
            if (!text.trim()) {
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
                    await parseTextStream(text, docId, false, true, {
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
                    const result = await parseText(text, docId, false, true);
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
    }, [text]);

    const save = useCallback(async (docId: string) => {
        setSaveStatus('saving');
        try {
            await saveArticleText(docId, text);
            if (statements.length > 0) {
                await saveStatements(docId, statements);
            }
            setSaveStatus('saved');
            setTimeout(() => setSaveStatus('idle'), 2000);
        } catch (err) {
            console.error('Save failed:', err);
            setSaveStatus('error');
        }
    }, [text, statements]);

    return {
        article, text, statements, isParsing, parseProgress, parseError, saveStatus,
        loadArticle, setText, triggerParse, save,
    };
}
