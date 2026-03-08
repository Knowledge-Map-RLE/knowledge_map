import React, { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import s from './Document_downloader_ui.module.css';
import {
    uploadPdfForExtraction, listDocuments, deleteDocument as apiDeleteDocument,
    searchPubMed, getByPubMedId, ingestPubMedArticle,
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
}

export interface DocumentListHandle {
    reloadDocuments: () => Promise<void>;
}

interface DocumentDownloaderUIProps {
    selectedDocument: PDFDocument | null;
    onSelectDocument: (document: PDFDocument | null) => void;
    onDocumentsChange: () => void;
    error: string | null;
    setError: (error: string | null) => void;
}

const Document_downloader_ui = forwardRef<DocumentListHandle, DocumentDownloaderUIProps>(function Document_downloader_ui({
    selectedDocument,
    onSelectDocument,
    onDocumentsChange,
    error,
    setError
}, ref) {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    const [contextMenu, setContextMenu] = useState<{ x: number; y: number; documentId: string } | null>(null);

    // PubMed unified search
    const [pubmedQuery, setPubmedQuery] = useState('');
    const [pubmedResults, setPubmedResults] = useState<PubMedSearchResult[]>([]);
    const [isPubMedSearching, setIsPubMedSearching] = useState(false);
    const pubmedDebounceRef = useRef<number | null>(null);

    // PubMed direct ID search
    const [pubmedIdQuery, setPubmedIdQuery] = useState('');
    const [pubmedIdResult, setPubmedIdResult] = useState<PubMedSearchResult | null>(null);
    const [isPubMedIdSearching, setIsPubMedIdSearching] = useState(false);
    const pubmedIdDebounceRef = useRef<number | null>(null);

    // Expanded abstract
    const [expandedAbstract, setExpandedAbstract] = useState<string | null>(null);

    // Toast
    const [toast, setToast] = useState<string | null>(null);

    const [ingestingId, setIngestingId] = useState<string | null>(null);
    const [localQuery, setLocalQuery] = useState('');
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(null), 3000);
    };

    const loadDocuments = async (): Promise<PDFDocument[]> => {
        try {
            const data = await listDocuments();
            if (!data?.success || !Array.isArray(data.documents)) {
                setError('Ошибка загрузки документов');
                return [];
            }
            const mapped = data.documents.map((d) => {
                try {
                    const status = d.has_markdown ? 'annotated' : 'ready_for_annotation';
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
                        is_processed: status === 'annotated',
                        pdf_url,
                        pubmed_id: d.pubmed_id,
                        pmc_id: d.pmc_id,
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
            return mapped;
        } catch (err) {
            setError(`Ошибка загрузки документов: ${err instanceof Error ? err.message : String(err)}`);
            return [];
        }
    };

    useImperativeHandle(ref, () => ({ reloadDocuments: () => loadDocuments().then(() => {}) }));
    useEffect(() => { loadDocuments(); }, []);

    // Надёжная проверка "уже загружено" по pubmed_id/pmc_id из Neo4j
    const isAlreadyLoaded = (r: PubMedSearchResult): boolean => {
        return documents.some(doc => {
            if (r.pmid && doc.pubmed_id && doc.pubmed_id === r.pmid) return true;
            if (r.pmcid && doc.pmc_id && doc.pmc_id === r.pmcid) return true;
            return false;
        });
    };

    // --- PubMed text search ---
    const handlePubMedQueryChange = (value: string) => {
        setPubmedQuery(value);
        if (pubmedDebounceRef.current) window.clearTimeout(pubmedDebounceRef.current);
        if (value.length < 3) { setPubmedResults([]); return; }
        pubmedDebounceRef.current = window.setTimeout(async () => {
            setIsPubMedSearching(true);
            try {
                const resp = await searchPubMed(value, 10);
                setPubmedResults(resp.results || []);
            } catch (err) {
                console.error('PubMed search error:', err);
                setPubmedResults([]);
            } finally {
                setIsPubMedSearching(false);
            }
        }, 500);
    };

    // --- PubMed direct ID search ---
    const handlePubMedIdChange = (value: string) => {
        setPubmedIdQuery(value);
        setPubmedIdResult(null);
        // Очищаем текстовые результаты, чтобы не было дублей
        if (value.trim()) {
            setPubmedResults([]);
            setPubmedQuery('');
        }
        if (pubmedIdDebounceRef.current) window.clearTimeout(pubmedIdDebounceRef.current);
        const trimmed = value.trim();
        if (!trimmed) return;
        const isPmid = /^\d+$/.test(trimmed);
        const isPmcid = /^PMC\d+$/i.test(trimmed);
        if (!isPmid && !isPmcid) return;
        pubmedIdDebounceRef.current = window.setTimeout(async () => {
            setIsPubMedIdSearching(true);
            try {
                const resp = await getByPubMedId(trimmed);
                setPubmedIdResult(resp.results?.[0] || null);
            } catch (err) {
                console.error('PubMed ID search error:', err);
            } finally {
                setIsPubMedIdSearching(false);
            }
        }, 400);
    };

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
                    // Перезагружаем через 5 сек и обновляем выбранный документ
                    setTimeout(async () => {
                        const freshDocs = await loadDocuments();
                        const updated = freshDocs.find(d => d.uid === resp.doc_id);
                        if (updated) onSelectDocument(updated);
                    }, 5000);
                } else {
                    // Синхронная загрузка (tar.gz → MD или metadata) — перезагружаем список
                    const freshDocs = await loadDocuments();
                    const added = freshDocs.find(d => d.uid === resp.doc_id);
                    if (added) onSelectDocument(added);
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

    // --- Local document filter ---
    const filteredDocuments = localQuery.length >= 3
        ? documents.filter(doc => {
            const q = localQuery.toLowerCase();
            return (doc.title || '').toLowerCase().includes(q)
                || (doc.original_filename || '').toLowerCase().includes(q);
        })
        : documents;

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
                const newDoc = { uid: result.doc_id || '', original_filename: file.name, md5_hash: result.doc_id || '', upload_date: new Date().toISOString(), processing_status: 'pdf_to_markdown', is_processed: false } as PDFDocument;
                setDocuments(prev => [newDoc, ...prev.filter(doc => doc.uid !== tempDocId)]);
                onSelectDocument(newDoc);
                let progress = 0;
                setProgressMap(prev => ({ ...prev, [newDoc.uid]: progress }));
                const progressInterval = setInterval(() => {
                    progress += Math.floor(Math.random() * 10) + 5;
                    if (progress >= 100) {
                        progress = 100;
                        clearInterval(progressInterval);
                        setDocuments(prev => prev.map(doc => doc.uid === newDoc.uid ? { ...doc, processing_status: 'ready_for_annotation' } : doc));
                        onDocumentsChange();
                    }
                    setProgressMap(prev => ({ ...prev, [newDoc.uid]: progress }));
                }, 200);
                setTimeout(() => setProgressMap(prev => { const u = { ...prev }; delete u[newDoc.uid]; return u; }), 25000);
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
        if (status === 'uploading') return `Загружено ${progress ?? 0}%`;
        if (status === 'pdf_to_markdown' || status === 'processing') return `Обработано ${progress ?? 0}%`;
        return null;
    };

    const PubMedResultItem = ({ r }: { r: PubMedSearchResult }) => {
        const key = r.pmid || r.pmcid || '';
        const isIngesting = ingestingId === key;
        const alreadyLoaded = isAlreadyLoaded(r);
        const abstractKey = r.pmid || r.pmcid || r.title;
        const isExpanded = expandedAbstract === abstractKey;

        return (
            <div className={s.pubmedResultItem}>
                <div className={s.pubmedResultHeader}>
                    <div className={s.pubmedResultTitle} title={r.title}>{r.title}</div>
                    <div className={s.pubmedResultBadges}>
                        {r.is_open_access
                            ? <span className={s.oaBadgeFull} title="Полный текст доступен">📖 OA</span>
                            : <span className={s.oaBadgeAbstract} title="Только абстракт">📄</span>
                        }
                    </div>
                </div>
                <div className={s.pubmedResultMeta}>
                    {r.authors.length > 0 && <span>{r.authors.slice(0, 2).join(', ')}{r.authors.length > 2 ? ' et al.' : ''}</span>}
                    {r.journal && <span>{r.journal}</span>}
                    {r.pub_date && <span>{r.pub_date}</span>}
                    {r.pmid && <span>PMID: {r.pmid}</span>}
                    {r.pmcid && <span>{r.pmcid}</span>}
                </div>
                {r.abstract && (
                    <button className={s.abstractToggle} onClick={() => setExpandedAbstract(isExpanded ? null : abstractKey)}>
                        {isExpanded ? '▲ Скрыть' : '▼ Абстракт'}
                    </button>
                )}
                {isExpanded && r.abstract && (
                    <div className={s.abstractText}>{r.abstract}</div>
                )}
                <div className={s.pubmedResultFooter}>
                    {alreadyLoaded ? (
                        <span className={s.alreadyLoaded}>✓ В списке</span>
                    ) : (
                        <button className={s.pubmedAddBtn} onClick={() => handleIngestArticle(r)} disabled={isIngesting}>
                            {isIngesting ? 'Загрузка...' : '+ Добавить'}
                        </button>
                    )}
                </div>
            </div>
        );
    };

    const isSearching = isPubMedSearching || isPubMedIdSearching;
    const hasResults = pubmedIdResult !== null || pubmedResults.length > 0;

    return (
        <div className={s.columnLayout}>
            {toast && <div className={s.toast}>{toast}</div>}

            {/* Верхний блок: загруженные документы */}
            <div className={s.topBlock}>
                <h2 className="text-base font-bold mb-2">Загруженные документы</h2>

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
                    placeholder="Поиск по документам (мин. 3 символа)..."
                    value={localQuery}
                    onChange={e => setLocalQuery(e.target.value)}
                />

                <div className={s.fileList}>
                    {filteredDocuments.map((doc) => {
                        const displayName = doc.title || doc.original_filename || doc.uid;
                        const progressText = getProgressText(doc.processing_status, doc.uid);
                        return (
                            <div
                                key={doc.uid}
                                className={`${s.fileItem} ${selectedDocument?.uid === doc.uid ? 'bg-blue-100' : ''}`}
                                onClick={() => onSelectDocument(doc)}
                                onContextMenu={(e) => {
                                    e.preventDefault();
                                    setContextMenu({ x: e.clientX, y: e.clientY, documentId: doc.uid });
                                }}
                            >
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className={getStatusClass(doc.processing_status)}></span>
                                    <div className="min-w-0">
                                        <p className="font-medium truncate text-sm" title={displayName}>{displayName}</p>
                                        <p className="text-xs text-gray-500">
                                            {getStatusText(doc.processing_status)}
                                            {progressText && <span className="text-blue-600 font-semibold"> {progressText}</span>}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Нижний блок: поиск PubMed + PMC */}
            <div className={s.bottomBlock}>
                <p className="text-sm font-semibold text-gray-700 mb-1.5">Поиск в PubMed и PMC</p>

                <input
                    type="text"
                    className={`${s.searchInput} mb-1.5`}
                    placeholder="Запрос (мин. 3 символа)..."
                    value={pubmedQuery}
                    onChange={e => handlePubMedQueryChange(e.target.value)}
                />

                <input
                    type="text"
                    className={`${s.searchInput} mb-1.5`}
                    placeholder="PMID или PMCID (напр. PMC3836174)..."
                    value={pubmedIdQuery}
                    onChange={e => handlePubMedIdChange(e.target.value)}
                />

                {/* Результаты с оверлей-спиннером */}
                <div className={s.pubmedResultsWrap}>
                    {isSearching && (
                        <div className={s.searchOverlay}>
                            <div className={s.loadingSpinner} style={{ width: 20, height: 20 }}></div>
                        </div>
                    )}
                    <div className={s.pubmedResults}>
                        {pubmedIdResult && <PubMedResultItem r={pubmedIdResult} />}
                        {pubmedResults
                            .filter(r => !pubmedIdResult || (
                                r.pmid !== pubmedIdResult.pmid &&
                                r.pmcid !== pubmedIdResult.pmcid
                            ))
                            .map(r => (
                                <PubMedResultItem key={r.pmid || r.pmcid || r.title} r={r} />
                            ))}
                        {!isSearching && pubmedQuery.length >= 3 && !hasResults && (
                            <p className="text-xs text-gray-400 p-2">Ничего не найдено</p>
                        )}
                        {!isSearching && !pubmedQuery && !pubmedIdQuery && (
                            <p className="text-xs text-gray-300 p-2">Введите запрос или ID статьи</p>
                        )}
                    </div>
                </div>
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
});

export default Document_downloader_ui;
