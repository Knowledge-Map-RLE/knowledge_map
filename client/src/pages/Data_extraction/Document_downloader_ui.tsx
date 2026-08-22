import React, { useState, useRef, useCallback, useEffect, useMemo, forwardRef, useImperativeHandle } from 'react';
import s from './Document_downloader_ui.module.css';
import {
    uploadPdfForExtraction, listDocuments, searchDocuments as apiSearchDocuments,
    deleteDocument as apiDeleteDocument, getDocumentStats,
    searchPubMed, getByPubMedId, ingestPubMedArticle, getDocumentProgress,
    type PubMedSearchResult
} from '../../services/api';
import DocumentContextMenu from './DocumentContextMenu';

interface PDFDocument {
    uid: string;
    original_filename: string;
    md5_hash: string;
    file_size?: number;
    upload_date: string;
    title?: string;
    authors?: string[];
    abstract?: string;
    keywords?: string[];
    processing_status: string;
    is_processed: boolean;
    pdf_url?: string;
    pubmed_id?: string;
    pmc_id?: string;
    doi?: string;
    source?: string;
}

export interface DocumentListHandle {
    reloadDocuments: () => Promise<void>;
}

type UnifiedListItem =
    | { kind: 'local'; doc: PDFDocument }
    | { kind: 'pubmed'; result: PubMedSearchResult };

interface DocumentDownloaderUIProps {
    selectedDocument: PDFDocument | null;
    onSelectDocument: (document: PDFDocument | null) => void;
    onDocumentsChange: () => void;
    error: string | null;
    setError: (error: string | null) => void;
}

const Document_downloader_ui = React.memo(forwardRef<DocumentListHandle, DocumentDownloaderUIProps>(function Document_downloader_ui({
    selectedDocument,
    onSelectDocument,
    onDocumentsChange,
    error,
    setError
}, ref) {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [fullTextCount, setFullTextCount] = useState(0);
    const [fullTextOnly, setFullTextOnly] = useState(true);
    const [isUploading, setIsUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    const [progressMessageMap, setProgressMessageMap] = useState<Record<string, string>>({});
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number; documentId: string } | null>(null);

    // Unified search: документы, PubMed текст, PMID/PMCID
    const [searchQuery, setSearchQuery] = useState('');
    const [pubmedResults, setPubmedResults] = useState<PubMedSearchResult[]>([]);
    const [isPubMedSearching, setIsPubMedSearching] = useState(false);
    const pubmedDebounceRef = useRef<number | null>(null);

    // PubMed direct ID search
    const [pubmedIdResult, setPubmedIdResult] = useState<PubMedSearchResult | null>(null);
    const [isPubMedIdSearching, setIsPubMedIdSearching] = useState(false);
    const pubmedIdDebounceRef = useRef<number | null>(null);

    // Toast
    const [toast, setToast] = useState<string | null>(null);

    const [ingestingId, setIngestingId] = useState<string | null>(null);
    const [searchResults, setSearchResults] = useState<PDFDocument[] | null>(null);
    const searchDebounceRef = useRef<number | null>(null);
    const searchAbortRef = useRef<AbortController | null>(null);
    const pubmedAbortRef = useRef<AbortController | null>(null);
    const pubmedIdAbortRef = useRef<AbortController | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(null), 3000);
    };

    const abortRef = useRef<AbortController | null>(null);

    const loadDocuments = useCallback(async (): Promise<PDFDocument[]> => {
        // Отменяем предыдущий висячий запрос
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const timeoutMs = 60000;
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

            const data = await listDocuments(0, 100, controller.signal, fullTextOnly);
            clearTimeout(timeoutId);

            if (!data?.success || !Array.isArray(data.documents)) {
                setError('Ошибка загрузки документов');
                return [];
            }
            const total = data.total_count ?? data.documents.length;
            const mapped = data.documents.map((d) => {
                try {
                    // Статус берём с сервера: 'annotated' присваивается только
                    // валидному markdown, has_markdown для этого не индикатор.
                    const status = d.processing_status || 'ready_for_annotation';
                    const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                    const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';
                    const filename = d.files?.pdf ? d.files.pdf.split('/').pop() || d.doc_id + '.pdf' : d.doc_id + '.pdf';
                    return {
                        uid: d.doc_id,
                        original_filename: filename,
                        md5_hash: d.doc_id,
                        title: d.title || undefined,
                        upload_date: new Date().toISOString(),
                        processing_status: status,
                        is_processed: d.is_processed,
                        pdf_url,
                        pubmed_id: d.pubmed_id,
                        pmc_id: d.pmc_id,
                        doi: d.doi,
                        source: d.source,
                    } as PDFDocument;
                } catch {
                    return {
                        uid: d.doc_id,
                        original_filename: d.doc_id + '.pdf',
                        md5_hash: d.doc_id,
                        upload_date: new Date().toISOString(),
                        processing_status: 'error',
                        is_processed: false,
                    } as PDFDocument;
                }
            });
            setDocuments(mapped);
            (window as any).__documents_total = total;
            return mapped;
        } catch (err: any) {
            if (err.name === 'AbortError') {
                console.warn('Загрузка документов прервана по таймауту');
                return [];
            }
            setError(`Ошибка загрузки документов: ${err instanceof Error ? err.message : String(err)}`);
            return [];
        }
    }, [setError, fullTextOnly]);

    useImperativeHandle(ref, () => ({ reloadDocuments: () => loadDocuments().then(() => {}) }));
    useEffect(() => {
        loadDocuments();
    }, [loadDocuments]);

    useEffect(() => {
        getDocumentStats().then(data => {
            if (data?.success) setFullTextCount(data.full_text_count ?? 0);
        }).catch(() => {});
    }, []);

    // --- Ingest article ---
    const handleIngestArticle = async (result: PubMedSearchResult) => {
        const key = result.pmid || result.pmcid || '';
        setIngestingId(key);
        setError(null);
        try {
            const resp = await ingestPubMedArticle(result.pmid, result.pmcid, result.source);
            if (resp.success && resp.doc_id) {
                if (resp.processing_status === 'pdf_to_markdown') {
                    // Асинхронная обработка (Docling) — добавляем временный элемент
                    const tempDoc: PDFDocument = {
                        uid: resp.doc_id,
                        original_filename: result.pmcid || `PMID${result.pmid}` || resp.doc_id,
                        md5_hash: resp.doc_id,
                        title: result.title,
                        upload_date: new Date().toISOString(),
                        processing_status: 'pdf_to_markdown',
                        is_processed: false,
                        pubmed_id: result.pmid,
                        pmc_id: result.pmcid,
                    };
                    setDocuments(prev => prev.some(d => d.uid === resp.doc_id) ? prev : [tempDoc, ...prev]);
                    onSelectDocument(tempDoc);
                    showToast(`⏳ PDF загружается: ${result.title.slice(0, 50)}...`);
                    // Поллинг обработки; после завершения — открываем статью автоматически
                    const pollIngest = async (docId: string) => {
                        try {
                            const prog = await getDocumentProgress(docId);
                            setProgressMap(prev => ({ ...prev, [docId]: prog.percent }));
                            if (prog.message) {
                                setProgressMessageMap(prev => ({ ...prev, [docId]: prog.message }));
                            }
                            setDocuments(prev => prev.map(doc =>
                                doc.uid === docId ? { ...doc, processing_status: prog.processing_status } : doc
                            ));
                            if (prog.processing_status === 'pdf_to_markdown' || prog.processing_status === 'uploading') {
                                setTimeout(() => pollIngest(docId), 2000);
                            } else {
                                setProgressMap(prev => { const u = { ...prev }; delete u[docId]; return u; });
                                setProgressMessageMap(prev => { const u = { ...prev }; delete u[docId]; return u; });
                                loadDocuments();
                                onSelectDocument({
                                    uid: docId,
                                    original_filename: result.pmcid || `PMID${result.pmid}` || docId,
                                    md5_hash: docId,
                                    title: result.title,
                                    upload_date: new Date().toISOString(),
                                    processing_status: prog.processing_status,
                                    is_processed: prog.processing_status === 'annotated',
                                    pubmed_id: result.pmid,
                                    pmc_id: result.pmcid,
                                } as PDFDocument);
                                onDocumentsChange();
                            }
                        } catch {
                            setTimeout(() => pollIngest(docId), 3000);
                        }
                    };
                    setTimeout(() => pollIngest(resp.doc_id), 2000);
                } else {
                    // Синхронная загрузка (tar.gz → MD или metadata) — открываем сразу по doc_id,
                    // не дожидаясь попадания документа в топ-200 списка
                    loadDocuments();
                    onSelectDocument({
                        uid: resp.doc_id,
                        original_filename: result.pmcid || `PMID${result.pmid}` || resp.doc_id,
                        md5_hash: resp.doc_id,
                        title: result.title,
                        upload_date: new Date().toISOString(),
                        processing_status: resp.processing_status,
                        is_processed: false,
                        pubmed_id: result.pmid,
                        pmc_id: result.pmcid,
                    } as PDFDocument);
                    const isFullText = result.is_open_access;
                    showToast(isFullText
                        ? `✓ Добавлен полный текст: ${result.title.slice(0, 50)}...`
                        : `✓ Добавлен абстракт: ${result.title.slice(0, 50)}...`
                    );
                }
                onDocumentsChange();
            } else {
                setError(resp.message || 'Ошибка загрузки статьи');
            }
        } catch (err) {
            setError(`Ошибка: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setIngestingId(null);
        }
    };

    // --- Delete with optimistic update ---
    const handleDelete = async (documentId: string) => {
        // Сначала убираем из UI немедленно
        setDocuments(prev => prev.filter(d => d.uid !== documentId));
        setContextMenu(null);
        if (selectedDocument?.uid === documentId) {
            // Сбрасываем выбранный документ если удаляем его
            onSelectDocument(null as any);
        }
        try {
            await apiDeleteDocument(documentId);
            onDocumentsChange();
            // Синхронизируем с сервером
            await loadDocuments();
        } catch (err) {
            console.error('Ошибка удаления документа:', err);
            // Восстанавливаем список при ошибке
            await loadDocuments();
        }
    };

    // --- Unified search: документы (fuzzy APOC), PubMed текст, PMID/PMCID ---
    useEffect(() => {
        if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
        if (pubmedDebounceRef.current) clearTimeout(pubmedDebounceRef.current);
        if (pubmedIdDebounceRef.current) clearTimeout(pubmedIdDebounceRef.current);
        if (searchAbortRef.current) searchAbortRef.current.abort();
        if (pubmedAbortRef.current) pubmedAbortRef.current.abort();
        if (pubmedIdAbortRef.current) pubmedIdAbortRef.current.abort();

        const q = searchQuery.trim();
        if (q.length < 3) {
            setSearchResults(null);
            setPubmedResults([]);
            setPubmedIdResult(null);
            return;
        }

        const isId = /^\d+$/.test(q) || /^PMC\d+$/i.test(q);
        const isDoi = /^10\.\d{4,}\/\S+$/i.test(q.trim());

        if (isId) {
            // PMID / PMCID — прямой поиск по ID
            setPubmedResults([]);
            pubmedIdDebounceRef.current = window.setTimeout(async () => {
                const controller = new AbortController();
                pubmedIdAbortRef.current = controller;
                const timeoutId = setTimeout(() => controller.abort(), 15000);
                setIsPubMedIdSearching(true);
                try {
                    const resp = await getByPubMedId(q, controller.signal);
                    setPubmedIdResult(resp.results?.[0] || null);
                } catch (err: any) {
                    if (err.name === 'AbortError') return;
                    console.error('PubMed ID search error:', err);
                    setPubmedIdResult(null);
                } finally {
                    clearTimeout(timeoutId);
                    setIsPubMedIdSearching(false);
                }
            }, 400);
        } else {
            // Текстовый запрос — ищем по локальным документам (Neo4j fulltext)
            setPubmedIdResult(null);
            setPubmedResults([]);
            searchDebounceRef.current = window.setTimeout(async () => {
                const controller = new AbortController();
                searchAbortRef.current = controller;
                try {
                    const data = await apiSearchDocuments(q, 0, 100, controller.signal, fullTextOnly);
                    if (!data?.success || !Array.isArray(data.documents)) {
                        setSearchResults([]);
                        return;
                    }
                    const mapped = data.documents.map((d: any) => ({
                        uid: d.doc_id,
                        original_filename: d.original_filename || d.doc_id + '.pdf',
                        md5_hash: d.doc_id,
                        title: d.title || undefined,
                        upload_date: new Date().toISOString(),
                        processing_status: d.has_markdown ? 'annotated' : 'ready_for_annotation',
                        is_processed: !!d.has_markdown,
                        pdf_url: d.files?.pdf ? `${(import.meta as any).env?.VITE_API_BASE_URL || ''}${d.files.pdf}` : '',
                        pubmed_id: d.pubmed_id,
                        pmc_id: d.pmc_id,
                        doi: d.doi,
                        source: d.source,
                    } as PDFDocument));
                    setSearchResults(mapped);
                } catch (err: any) {
                    if (err.name === 'AbortError') return;
                    console.warn('Ошибка поиска документов:', err);
                    setSearchResults([]);
                }
            }, 300);
        }

        return () => {
            if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
            if (pubmedDebounceRef.current) clearTimeout(pubmedDebounceRef.current);
            if (pubmedIdDebounceRef.current) clearTimeout(pubmedIdDebounceRef.current);
            if (searchAbortRef.current) searchAbortRef.current.abort();
            if (pubmedAbortRef.current) pubmedAbortRef.current.abort();
            if (pubmedIdAbortRef.current) pubmedIdAbortRef.current.abort();
        };
    }, [searchQuery, fullTextOnly]);

    // --- Document list: search results if query >=3, else full list ---
    const filteredDocuments = searchQuery.trim().length >= 3
        ? (searchResults ?? documents)
        : documents.slice(0, 100);
    const sortedDocuments = [...filteredDocuments].sort((a, b) => {
        if (a.is_processed === b.is_processed) return 0;
        return a.is_processed ? -1 : 1;
    });
    const hasMoreDocuments = searchQuery.trim().length < 3 && documents.length > 100;

    // --- Дедупликация: уже загруженные статьи не показываем в результатах PubMed ---
    const loadedArticleKeys = useMemo(() => {
        const ids = new Set<string>();
        const titles = new Set<string>();
        documents.forEach(d => {
            if (d.uid) ids.add(`uid:${d.uid}`);
            if (d.pubmed_id) ids.add(`pmid:${d.pubmed_id}`);
            if (d.pmc_id) ids.add(`pmcid:${d.pmc_id}`);
            const title = (d.title || d.original_filename || '').trim().toLowerCase().replace(/\s+/g, ' ');
            if (title) titles.add(title);
        });
        return { ids, titles };
    }, [documents]);

    const isPubmedResultLoaded = useCallback((r: PubMedSearchResult): boolean => {
        if (r.is_loaded) return true;
        if (r.pmid && loadedArticleKeys.ids.has(`pmid:${r.pmid}`)) return true;
        if (r.pmcid && loadedArticleKeys.ids.has(`pmcid:${r.pmcid}`)) return true;
        const title = (r.title || '').trim().toLowerCase().replace(/\s+/g, ' ');
        return title.length > 0 && loadedArticleKeys.titles.has(title);
    }, [loadedArticleKeys]);

    // --- PDF upload ---
    const handleFileUpload = async (file: File) => {
        if (!file.type.startsWith('application/pdf')) { setError('Пожалуйста, выберите PDF файл'); return; }
        setIsUploading(true);
        setError(null);
        const tempDocId = 'upload_' + Date.now();
        const tempDoc = { uid: tempDocId, original_filename: file.name, md5_hash: '', upload_date: new Date().toISOString(), processing_status: 'uploading', is_processed: false } as PDFDocument;
        setDocuments(prev => [tempDoc, ...prev]);
        onSelectDocument(tempDoc);
        try {
            const result = await uploadPdfForExtraction(file, (progress) => {
                setProgressMap(prev => ({ ...prev, [tempDocId]: progress }));
            });
            if (result.success) {
                const isDuplicate = result.message?.includes('Дубликат') || result.message?.includes('уже существует');
                const initialStatus = isDuplicate ? 'ready_for_annotation' : 'pdf_to_markdown';
                const newDoc = { uid: result.doc_id || '', original_filename: file.name, md5_hash: result.doc_id || '', upload_date: new Date().toISOString(), processing_status: initialStatus, is_processed: isDuplicate } as PDFDocument;
                setDocuments(prev => [newDoc, ...prev.filter(doc => doc.uid !== tempDocId)]);
                onSelectDocument(newDoc);

                if (isDuplicate) {
                    // Дубликат — документ уже открыт, список обновляем в фоне
                    loadDocuments();
                    onDocumentsChange();
                } else {
                    setProgressMap(prev => ({ ...prev, [newDoc.uid]: 0 }));

                    // Polling реального прогресса через API
                    const pollProgress = async (docId: string) => {
                        try {
                            const prog = await getDocumentProgress(docId);
                            setProgressMap(prev => ({ ...prev, [docId]: prog.percent }));
                            if (prog.message) {
                                setProgressMessageMap(prev => ({ ...prev, [docId]: prog.message }));
                            }
                            setDocuments(prev => prev.map(doc =>
                                doc.uid === docId ? { ...doc, processing_status: prog.processing_status } : doc
                            ));
                            if (prog.processing_status === 'pdf_to_markdown' || prog.processing_status === 'uploading') {
                                setTimeout(() => pollProgress(docId), 2000);
                            } else {
                                setProgressMap(prev => { const u = { ...prev }; delete u[docId]; return u; });
                                setProgressMessageMap(prev => { const u = { ...prev }; delete u[docId]; return u; });
                                loadDocuments();
                                onSelectDocument({
                                    uid: docId,
                                    original_filename: file.name,
                                    md5_hash: docId,
                                    upload_date: new Date().toISOString(),
                                    processing_status: prog.processing_status,
                                    is_processed: prog.processing_status === 'annotated',
                                } as PDFDocument);
                                onDocumentsChange();
                            }
                        } catch {
                            setTimeout(() => pollProgress(docId), 3000);
                        }
                    };
                    setTimeout(() => pollProgress(newDoc.uid), 2000);
                }
            } else {
                setError(result.message || 'Ошибка загрузки файла');
                setDocuments(prev => prev.filter(doc => doc.uid !== tempDocId));
            }
        } catch {
            setError('Ошибка загрузки файла');
            setDocuments(prev => prev.filter(doc => doc.uid !== tempDocId));
        } finally {
            setIsUploading(false);
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); };
    const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileUpload(f); }, []);
    const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setDragOver(true); }, []);
    const handleDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); setDragOver(false); }, []);

    const getStatusClass = (status: string) => {
        switch (status) {
            case 'uploading': case 'pdf_to_markdown': case 'processing': return s.statusIndicator + ' ' + s.processing;
            case 'ready_for_annotation': return s.statusIndicator + ' ' + s.uploaded;
            case 'annotated': return s.statusIndicator + ' ' + s.annotated;
            case 'error': return s.statusIndicator + ' ' + s.error;
            default: return s.statusIndicator + ' ' + s.uploaded;
        }
    };
    const getStatusText = (status: string) => {
        switch (status) {
            case 'uploading': return 'Загрузка';
            case 'pdf_to_markdown': return 'Обрабатывается';
            case 'ready_for_annotation': return 'Готов к аннотированию';
            case 'processing': return 'Обрабатывается';
            case 'annotated': return 'Аннотирован';
            case 'error': return 'Ошибка';
            default: return 'Неизвестно';
        }
    };
    const getProgressText = (status: string, docId: string) => {
        const progress = progressMap[docId];
        const message = progressMessageMap[docId];
        if (status === 'uploading') return `Загружено ${progress ?? 0}%`;
        if (status === 'pdf_to_markdown' || status === 'processing') {
            if (message) return `${progress ?? 0}% — ${message}`;
            return `Обработано ${progress ?? 0}%`;
        }
        return null;
    };

    const handlePubMedClick = (r: PubMedSearchResult) => {
        if (ingestingId) return;
        const loadedDoc = documents.find(doc =>
            (r.pmid && doc.pubmed_id === r.pmid) || (r.pmcid && doc.pmc_id === r.pmcid)
        );
        if (loadedDoc) {
            onSelectDocument(loadedDoc);
            return;
        }
        handleIngestArticle(r);
    };

    const DocumentListItem = ({ item }: { item: UnifiedListItem }) => {
        if (item.kind === 'local') {
            const doc = item.doc;
            const displayName = doc.title || doc.original_filename || doc.uid;
            const progressText = getProgressText(doc.processing_status, doc.uid);
            const sourceTag = doc.source && doc.source !== 'upload'
                ? <span className="text-gray-400 text-[10px] ml-1">[{doc.source}]</span>
                : null;
            const doiTag = doc.doi
                ? <span className="text-gray-500 text-[10px] ml-1" title={doc.doi}>DOI</span>
                : null;
            return (
                <div
                    className={`${s.docItem} ${selectedDocument?.uid === doc.uid ? s.docItemSelected : ''}`}
                    onClick={() => onSelectDocument(doc)}
                    onContextMenu={(e) => {
                        e.preventDefault();
                        setContextMenu({ x: e.clientX, y: e.clientY, documentId: doc.uid });
                    }}
                >
                    <span className={getStatusClass(doc.processing_status)} title={getStatusText(doc.processing_status)}></span>
                    <div className={s.docItemContent}>
                        <p className={s.docItemTitle} title={displayName}>{displayName}</p>
                        <p className={s.docItemMeta}>
                            {getStatusText(doc.processing_status)}
                            {sourceTag}
                            {doiTag}
                            {progressText && <span className="text-blue-600 font-semibold"> {progressText}</span>}
                        </p>
                    </div>
                </div>
            );
        }

        const r = item.result;
        const isIngesting = ingestingId === (r.pmid || r.pmcid || '');

        return (
            <div
                className={s.docItem}
                onClick={() => handlePubMedClick(r)}
                title={isIngesting ? 'Загрузка статьи...' : 'Нажмите, чтобы загрузить и открыть'}
            >
                <span className={`${s.statusIndicator} ${s.uploaded}`} title="Внешний источник (PubMed)"></span>
                <div className={s.docItemContent}>
                    <p className={s.docItemTitle} title={r.title}>{r.title}</p>
                </div>
                {isIngesting && (
                    <div className={s.docItemAction}>
                        <span className={s.loadingSpinner} style={{ width: 14, height: 14 }}></span>
                    </div>
                )}
            </div>
        );
    };

    const isSearching = isPubMedSearching || isPubMedIdSearching;
    const combinedList: UnifiedListItem[] = [
        ...sortedDocuments.map(d => ({ kind: 'local' as const, doc: d })),
        ...(pubmedIdResult && !isPubmedResultLoaded(pubmedIdResult)
            ? [{ kind: 'pubmed' as const, result: pubmedIdResult }]
            : []),
        ...pubmedResults
            .filter(r => !isPubmedResultLoaded(r))
            .filter(r => !pubmedIdResult || (
                r.pmid !== pubmedIdResult.pmid &&
                r.pmcid !== pubmedIdResult.pmcid
            ))
            .map(r => ({ kind: 'pubmed' as const, result: r })),
    ];

    return (
        <div className={s.columnLayout}>
            {toast && <div className={s.toast}>{toast}</div>}

            {/* Верхний блок: загруженные документы */}
            <div className={s.topBlock}>
                <h2 className="text-base font-bold mb-2">Документы</h2>

                <div
                    className={`${s.uploadArea} ${dragOver ? s.dragover : ''}`}
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileSelect} className="hidden" />
                    {isUploading ? (
                        <div className="flex flex-col items-center">
                            <div className={s.loadingSpinner}></div>
                            <p className="mt-2 text-sm">Загрузка файла...</p>
                        </div>
                    ) : (
                        <p className="text-sm">Перетащите PDF или нажмите для выбора</p>
                    )}
                </div>

                {error && (
                    <div className="mt-2 p-2 bg-red-100 border border-red-300 rounded text-red-700 text-xs">
                        {error}
                    </div>
                )}

                <input
                    type="text"
                    className={`${s.searchInput} mt-2`}
                    placeholder="Поиск: название, DOI, PMID или PMCID..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                />

                <label className="flex items-center gap-2 mt-2 text-xs text-gray-500 cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={fullTextOnly}
                        onChange={e => setFullTextOnly(e.target.checked)}
                        className="accent-blue-600"
                    />
                    Только с полными текстами
                </label>

                <div className={s.docListWrap}>
                    {isSearching && (
                        <div className={s.searchOverlay}>
                            <div className={s.loadingSpinner} style={{ width: 20, height: 20 }}></div>
                        </div>
                    )}
                    <div className={s.fileList}>
                        {combinedList.length === 0 ? (
                            <p className="text-xs text-gray-300 p-2">
                                {searchQuery.trim().length >= 3 ? 'Ничего не найдено' : 'Введите запрос или ID статьи'}
                            </p>
                        ) : (
                            combinedList.map(item => (
                                <DocumentListItem
                                    key={item.kind === 'local'
                                        ? `local-${item.doc.uid}`
                                        : `pubmed-${item.result.pmid || item.result.pmcid || item.result.title}`}
                                    item={item}
                                />
                            ))
                        )}
                    </div>
                </div>
                {searchQuery.trim().length >= 3 ? (
                    <p className={s.docListHint}>
                        Найдено {sortedDocuments.length} документов по запросу «{searchQuery}».
                        {fullTextCount > 0 && <> С полным текстом: {fullTextCount}.</>}
                    </p>
                ) : (hasMoreDocuments || (window as any).__documents_total > 100) && (
                    <p className={s.docListHint}>
                        Показано {Math.min(100, documents.length)} из {(window as any).__documents_total || documents.length}.
                        {fullTextCount > 0 && <> С полным текстом: {fullTextCount}.</>}
                        Введите запрос для поиска.
                    </p>
                )}
            </div>

            {contextMenu && (
                <DocumentContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    onDelete={() => handleDelete(contextMenu.documentId)}
                    onClose={() => setContextMenu(null)}
                />
            )}
        </div>
    );
}) as typeof Document_downloader_ui);

export default Document_downloader_ui;
