import React, { useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react';
import s from './Data_extraction.module.css';
import { uploadPdfForExtraction, importAnnotations as apiImportAnnotations, exportAnnotations as apiExportAnnotations, getDocumentAssets, deleteDocument as apiDeleteDocument, listDocuments, saveMarkdown } from '../../services/api';
import { AnnotationWorkspace } from './Annotation';
import MarkdownEditor from '../MarkdownEditor/MarkdownEditor';
import Project_title from '../Project_title';
import Search from '../Search';
import User from '../User';
import DocumentContextMenu from './DocumentContextMenu';
import { PatternGenerator } from './Patterns';

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
}

export default function Data_extraction() {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [pdfUrl, setPdfUrl] = useState<string>('');
    const [isUploading, setIsUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    const [docId, setDocId] = useState<string>('');

    // Новый state для исходного markdown и auto-save
    const [sourceMarkdown, setSourceMarkdown] = useState<string>('');
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
    const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

    // Context menu state
    const [contextMenu, setContextMenu] = useState<{
        x: number;
        y: number;
        documentId: string;
    } | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);
    const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    // Загружаем список документов при монтировании компонента
    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            console.log('Начало загрузки документов...');
            const data = await listDocuments();
            console.log('Загруженные документы из API:', data);

            if (!data) {
                console.error('API вернул null/undefined');
                setError('Не удалось загрузить список документов');
                return;
            }

            if (!data.success) {
                console.error('API вернул success=false');
                setError('Ошибка при загрузке документов');
                return;
            }

            if (!Array.isArray(data.documents)) {
                console.error('data.documents не является массивом:', typeof data.documents);
                setError('Некорректный формат данных от сервера');
                return;
            }

            console.log(`Обработка ${data.documents.length} документов...`);

            if (data?.success && Array.isArray(data.documents)) {
                // маппинг в локальный тип PDFDocument с проверкой реального статуса
                const mappedPromises = data.documents.map(async (d) => {
                    try {
                        console.log('Обработка документа:', d);
                        let status = d.has_markdown ? 'annotated' : 'uploaded';

                        // формируем возможный pdf url из списка документов, если доступен
                        const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                        const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';

                        return {
                            uid: d.doc_id,
                            original_filename: d.original_filename || d.files?.pdf?.split('/').pop() || d.doc_id + '.pdf',
                            md5_hash: d.doc_id,
                            title: d.title || null,
                            upload_date: new Date().toISOString(),
                            processing_status: status,
                            is_processed: status === 'annotated',
                            pdf_url,
                        } as any;
                    } catch (err) {
                        console.error(`Ошибка обработки документа ${d.doc_id}:`, err);
                        // Возвращаем документ с минимальной информацией даже при ошибке
                        const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                        const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';
                        return {
                            uid: d.doc_id,
                            original_filename: d.original_filename || d.doc_id + '.pdf',
                            md5_hash: d.doc_id,
                            title: d.title || null,
                            upload_date: new Date().toISOString(),
                            processing_status: 'error',
                            is_processed: false,
                            pdf_url,
                        } as any;
                    }
                });
                const mapped = await Promise.all(mappedPromises);
                console.log(`Загружено ${mapped.length} документов, устанавливаем в state...`);
                setDocuments(mapped);
                console.log('Документы установлены в state');
            }
        } catch (err) {
            console.error('Ошибка загрузки документов:', err);
            setError(`Ошибка загрузки документов: ${err instanceof Error ? err.message : String(err)}`);
        }
    };

    const handleFileUpload = async (file: File) => {
        if (!file.type.startsWith('application/pdf')) {
            setError('Пожалуйста, выберите PDF файл');
            return;
        }

        setIsUploading(true);
        setError(null);

        try {
            const result = await uploadPdfForExtraction(file);
            if (result.success) {
                setDocId(result.doc_id || '');
                // добавим в список локально
                const newDoc = {
                    uid: result.doc_id || '',
                    original_filename: file.name,
                    md5_hash: result.doc_id || '',
                    upload_date: new Date().toISOString(),
                    processing_status: 'processing',
                    is_processed: false,
                } as PDFDocument;
                setDocuments(prev => [newDoc, ...prev]);
                setSelectedDocument(newDoc);
            } else {
                setError(result.message || 'Ошибка загрузки файла');
            }
        } catch (err) {
            setError('Ошибка загрузки файла');
            console.error('Ошибка загрузки:', err);
        } finally {
            setIsUploading(false);
        }
    };

    const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            handleFileUpload(file);
        }
    };

    const handleDrop = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        setDragOver(false);
        
        const file = event.dataTransfer.files[0];
        if (file) {
            handleFileUpload(file);
        }
    }, []);

    const handleDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        setDragOver(true);
    }, []);

    const handleDragLeave = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        setDragOver(false);
    }, []);

    const selectDocument = async (document: PDFDocument) => {
        setSelectedDocument(document);
        setDocId(document.uid);
        // Загружаем markdown из S3
        try {
            const assets = await getDocumentAssets(document.uid);
            if (assets?.markdown) {
                setSourceMarkdown(assets.markdown);
                setProgressMap(prev => ({ ...prev, [document.uid]: 100 }));
                console.log('Markdown загружен:', assets.markdown.length, 'символов');
            } else {
                console.log('Markdown не найден для документа:', document.uid);
                setSourceMarkdown('');
            }
            // Пытаемся извлечь PDF URL из ассетов
            const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
            const candidate = (assets as any)?.pdf_url || (assets as any)?.files?.pdf_url || (assets as any)?.files?.pdf;
            if (candidate) {
                setPdfUrl(String(candidate).startsWith('http') ? String(candidate) : `${base}${candidate}`);
            } else if (document.pdf_url) {
                setPdfUrl(document.pdf_url);
            } else {
                setPdfUrl('');
            }
        } catch (err) {
            console.error('Ошибка загрузки документа:', err);
            setSourceMarkdown('');
            setPdfUrl('');
        }
    };

    // Обработчик изменений в markdown
    const handleSourceMarkdownChange = useCallback((newMarkdown: string) => {
        setSourceMarkdown(newMarkdown);
        setSaveStatus('idle');

        // Отменяем предыдущий таймер (если был)
        if (saveTimeoutRef.current) {
            clearTimeout(saveTimeoutRef.current);
        }
    }, []);

    // Функция для ручного сохранения markdown (вызывается по кнопке "Сохранить")
    const handleManualSave = useCallback(async () => {
        if (!selectedDocument) return;

        try {
            setSaveStatus('saving');
            setIsSaving(true);

            await saveMarkdown(selectedDocument.uid, sourceMarkdown);

            setSaveStatus('saved');
            setLastSavedAt(new Date());
            console.log('Markdown сохранен в S3');

            // Сбрасываем статус 'saved' через 3 секунды
            setTimeout(() => {
                setSaveStatus('idle');
            }, 3000);
        } catch (err) {
            console.error('Ошибка сохранения markdown:', err);
            setSaveStatus('error');
            setError('Не удалось сохранить изменения');
        } finally {
            setIsSaving(false);
        }
    }, [selectedDocument, sourceMarkdown]);

    // Cleanup timeout при unmount
    useEffect(() => {
        return () => {
            if (saveTimeoutRef.current) {
                clearTimeout(saveTimeoutRef.current);
            }
        };
    }, []);



    const getStatusClass = (status: string) => {
        switch (status) {
            case 'uploaded': return s.statusIndicator + ' ' + s.uploaded;
            case 'processing': return s.statusIndicator + ' ' + s.processing;
            case 'annotated': return s.statusIndicator + ' ' + s.annotated;
            case 'error': return s.statusIndicator + ' ' + s.error;
            default: return s.statusIndicator + ' ' + s.uploaded;
        }
    };

    const getStatusText = (status: string) => {
        switch (status) {
            case 'uploaded': return 'Загружен';
            case 'processing': return 'Обрабатывается';
            case 'annotated': return 'Аннотирован';
            case 'error': return 'Ошибка';
            default: return 'Неизвестно';
        }
    };

    return (
        <main className={s.dex}>
            {/* Шапка */}
            <div className={s.headerRow}>
                <Project_title className={s.headerPanel} />
                <Search className={s.headerPanel} />
                <User className={s.headerPanel} />
            </div>

            {/* Основная строка: 3 колонки */}
            <div className={s.topRow}>
                {/* Левая колонка: Загрузка встроена в список документов */}
                <div className={s.leftColumn}>
                    <h2 className="text-base font-bold mb-3">Загруженные документы</h2>
                    <div
                        className={`${s.uploadArea} ${dragOver ? s.dragover : ''} mb-3`}
                        onDrop={handleDrop}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onClick={() => fileInputRef.current?.click()}
                        style={{ position:'sticky', top:0, zIndex:1 }}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf"
                            onChange={handleFileSelect}
                            className="hidden"
                        />
                        {isUploading ? (
                            <div className="flex flex-col items-center">
                                <div className={s.loadingSpinner}></div>
                                <p className="mt-2">Загрузка файла...</p>
                            </div>
                        ) : (
                            <div>
                                <p className="text-sm">Перетащите PDF или нажмите для выбора</p>
                            </div>
                        )}
                    </div>

                    {/* Ошибки */}
                    {error && (
                        <div className="mb-3 p-2 bg-red-100 border border-red-300 rounded-lg text-red-700 text-sm">
                            {error}
                        </div>
                    )}

                    <div className={s.fileList}>
                        {documents.map((doc) => {
                            // Определяем отображаемое название: title или original_filename
                            const displayName = doc.title || doc.original_filename || doc.uid;

                            return (
                                <div
                                    key={doc.uid}
                                    className={`${s.fileItem} ${selectedDocument?.uid === doc.uid ? 'bg-blue-100' : ''}`}
                                    onClick={() => selectDocument(doc)}
                                    onContextMenu={(e) => {
                                        e.preventDefault();
                                        setContextMenu({
                                            x: e.clientX,
                                            y: e.clientY,
                                            documentId: doc.uid,
                                        });
                                    }}
                                >
                                    <div className="flex items-center gap-2 min-w-0">
                                        <span className={getStatusClass(doc.processing_status)}></span>
                                        <div className="min-w-0">
                                            <p className="font-medium truncate" title={displayName}>{displayName}</p>
                                            <p className="text-xs text-gray-500">
                                                {getStatusText(doc.processing_status)}
                                                {doc.processing_status === 'processing' ? (
                                                    <span className="text-blue-600 font-semibold"> {progressMap[doc.uid] ?? 0}%</span>
                                                ) : null}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Context Menu */}
                    {contextMenu && (
                        <DocumentContextMenu
                            x={contextMenu.x}
                            y={contextMenu.y}
                            onDelete={async () => {
                                try {
                                    await apiDeleteDocument(contextMenu.documentId);
                                    if (selectedDocument?.uid === contextMenu.documentId) {
                                        setSelectedDocument(null);
                                        setSourceMarkdown('');
                                        setDocId('');
                                    }
                                    await loadDocuments();
                                } catch (err) {
                                    console.error('Ошибка удаления документа:', err);
                                }
                            }}
                            onClose={() => setContextMenu(null)}
                        />
                    )}
                </div>

                {/* Средняя колонка: Исходный PDF */}
                <div className={s.middleColumn}>
                    <h2 className="text-base font-bold mb-3">Исходный PDF</h2>
                    <div id="km-pdf-pane" className={s.pdfViewer} style={{ overflow:'auto' }}>
                        {pdfUrl ? (
                            <iframe
                                id="km-pdf-viewer"
                                title="PDF"
                                src={pdfUrl}
                                style={{ width:'100%', height:'100%', border:'0' }}
                            />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Нет PDF</div>
                        )}
                    </div>
                </div>

                {/* Правая колонка: Предпросмотр Markdown (Quill) */}
                <div className={s.rightColumn}>
                    <h2 className="text-base font-bold mb-3">Предпросмотр Markdown</h2>
                    {selectedDocument ? (
                        <div style={{ height: 'calc(100% - 50px)' }}>
                            <MarkdownEditor
                                value={sourceMarkdown}
                                onChange={() => {}}
                                readOnly={true}
                            />
                        </div>
                    ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                            Выберите документ
                        </div>
                    )}
                </div>
            </div>

            {/* Нижняя строка: Аннотатор */}
            <div className={s.bottomRow}>
                <div className={s.fullWidth} style={{ padding: '16px', background: 'white', height: '100%', overflow: 'hidden' }}>
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="text-base font-bold">Аннотатор</h2>
                        {/* Индикатор сохранения */}
                        {saveStatus !== 'idle' && (
                            <div className={`${s.saveIndicator} ${s[saveStatus]}`}>
                                {saveStatus === 'saving' && (
                                    <>
                                        <div className={s.loadingSpinner} style={{ width: '12px', height: '12px' }}></div>
                                        <span>Сохранение...</span>
                                    </>
                                )}
                                {saveStatus === 'saved' && (
                                    <>
                                        <span>✓</span>
                                        <span>Сохранено {lastSavedAt ? new Date(lastSavedAt).toLocaleTimeString() : ''}</span>
                                    </>
                                )}
                                {saveStatus === 'error' && (
                                    <>
                                        <span>✗</span>
                                        <span>Ошибка сохранения</span>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                    {selectedDocument && docId ? (
                        <div style={{ height: 'calc(100% - 50px)' }}>
                            <AnnotationWorkspace
                                docId={docId}
                                text={sourceMarkdown}
                                readOnly={false}
                                onTextChange={handleSourceMarkdownChange}
                                onSave={handleManualSave}
                                documentTitle={selectedDocument.title || selectedDocument.original_filename}
                            />
                        </div>
                    ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                            Выберите документ для аннотирования
                        </div>
                    )}
                </div>
            </div>

            {/* Блок паттернов */}
            <div className={s.patternsRow}>
                <PatternGenerator />
            </div>
        </main>
    );
}
