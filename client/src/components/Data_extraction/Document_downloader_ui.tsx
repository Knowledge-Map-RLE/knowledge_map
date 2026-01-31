import React, { useState, useRef, useCallback, useEffect } from 'react';
import s from './Document_downloader_ui.module.css';
import { uploadPdfForExtraction, listDocuments, deleteDocument as apiDeleteDocument } from '../../services/api';
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
}

interface DocumentDownloaderUIProps {
    selectedDocument: PDFDocument | null;
    onSelectDocument: (document: PDFDocument) => void;
    onDocumentsChange: () => void;
    error: string | null;
    setError: (error: string | null) => void;
}

export default function Document_downloader_ui({
    selectedDocument,
    onSelectDocument,
    onDocumentsChange,
    error,
    setError
}: DocumentDownloaderUIProps) {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    
    // Context menu state
    const [contextMenu, setContextMenu] = useState<{
        x: number;
        y: number;
        documentId: string;
    } | null>(null);
    
    const fileInputRef = useRef<HTMLInputElement>(null);

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
                const mapped = data.documents.map((d) => {
                    try {
                        console.log('Обработка документа:', d);
                        // Проверяем, есть ли у документа markdown файл
                        let status = d.has_markdown ? 'annotated' : 'ready_for_annotation';
                        
                        // формируем возможный pdf url из списка документов, если доступен
                        const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                        const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';
                        
                        // Извлекаем имя файла из пути, если доступно
                        const filename = d.files?.pdf ? d.files.pdf.split('/').pop() || d.doc_id + '.pdf' : d.doc_id + '.pdf';
                        
                        console.log('Определение статуса документа:', d.doc_id, 'has_markdown:', d.has_markdown, 'status:', status);
                        
                        return {
                            uid: d.doc_id,
                            original_filename: filename,
                            md5_hash: d.doc_id,
                            title: null, // API не возвращает title в listDocuments
                            upload_date: new Date().toISOString(),
                            processing_status: status,
                            is_processed: status === 'annotated',
                            pdf_url,
                        } as PDFDocument;
                    } catch (err) {
                        console.error(`Ошибка обработки документа ${d.doc_id}:`, err);
                        // Возвращаем документ с минимальной информацией даже при ошибке
                        const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                        const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';
                        const filename = d.files?.pdf ? d.files.pdf.split('/').pop() || d.doc_id + '.pdf' : d.doc_id + '.pdf';
                        
                        return {
                            uid: d.doc_id,
                            original_filename: filename,
                            md5_hash: d.doc_id,
                            title: null,
                            upload_date: new Date().toISOString(),
                            processing_status: 'error',
                            is_processed: false,
                            pdf_url,
                        } as PDFDocument;
                    }
                });
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
        
        // Create a temporary document for tracking progress
        const tempDocId = 'upload_' + Date.now();
        const tempDoc = {
            uid: tempDocId,
            original_filename: file.name,
            md5_hash: '',
            upload_date: new Date().toISOString(),
            processing_status: 'uploading',
            is_processed: false,
        } as PDFDocument;
        
        setDocuments(prev => [tempDoc, ...prev]);
        onSelectDocument(tempDoc);

        try {
            const result = await uploadPdfForExtraction(file, (progress) => {
                // Update progress for the temporary document
                setProgressMap(prev => ({ ...prev, [tempDocId]: progress }));
            });
            
            if (result.success) {
                console.log('Файл успешно загружен, начинаем преобразование PDF в Markdown');
                // After upload, start PDF to Markdown conversion
                const newDoc = {
                    uid: result.doc_id || '',
                    original_filename: file.name,
                    md5_hash: result.doc_id || '',
                    upload_date: new Date().toISOString(),
                    processing_status: 'pdf_to_markdown',
                    is_processed: false,
                } as PDFDocument;
                
                console.log('Создание документа со статусом pdf_to_markdown:', newDoc);
                
                setDocuments(prev => {
                    // Remove temporary document and add real one
                    const filtered = prev.filter(doc => doc.uid !== tempDocId);
                    return [newDoc, ...filtered];
                });
                
                onSelectDocument(newDoc);
                
                // Simulate PDF to Markdown conversion progress
                let progress = 0;
                console.log('Начало преобразования PDF в Markdown для документа:', newDoc.uid);
                setProgressMap(prev => {
                    const newProgressMap = { ...prev, [newDoc.uid]: progress };
                    console.log('Обновление progressMap:', newProgressMap);
                    return newProgressMap;
                });
                
                const progressInterval = setInterval(() => {
                    progress += Math.floor(Math.random() * 10) + 5;
                    if (progress >= 100) {
                        progress = 100;
                        clearInterval(progressInterval);
                        console.log('Преобразование PDF в Markdown завершено для документа:', newDoc.uid);
                        
                        // Update document status to ready_for_annotation when conversion is complete
                        setDocuments(prev => {
                            const updated = prev.map(doc =>
                                doc.uid === newDoc.uid
                                    ? {...doc, processing_status: 'ready_for_annotation'}
                                    : doc
                            );
                            console.log('Обновлен статус документа на ready_for_annotation:', newDoc.uid);
                            return updated;
                        });
                        
                        onDocumentsChange();
                    }
                    console.log('Прогресс преобразования PDF в Markdown для документа', newDoc.uid, ':', progress, '%');
                    setProgressMap(prev => ({ ...prev, [newDoc.uid]: progress }));
                }, 200);
                
                // Clear progress for this document after 25 seconds
                setTimeout(() => {
                    setProgressMap(prev => {
                        const updated = { ...prev };
                        delete updated[newDoc.uid];
                        return updated;
                    });
                }, 25000);
            } else {
                setError(result.message || 'Ошибка загрузки файла');
                
                // Remove temporary document on error
                setDocuments(prev => prev.filter(doc => doc.uid !== tempDocId));
            }
        } catch (err) {
            setError('Ошибка загрузки файла');
            console.error('Ошибка загрузки:', err);
            
            // Remove temporary document on error
            setDocuments(prev => prev.filter(doc => doc.uid !== tempDocId));
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

    const getStatusClass = (status: string) => {
        switch (status) {
            case 'uploading': return s.statusIndicator + ' ' + s.processing;
            case 'pdf_to_markdown': return s.statusIndicator + ' ' + s.processing;
            case 'ready_for_annotation': return s.statusIndicator + ' ' + s.uploaded;
            case 'processing': return s.statusIndicator + ' ' + s.processing;
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
        console.log('Получение прогресса для документа:', docId, 'статус:', status, 'прогресс:', progress);
        
        if (status === 'uploading') {
            return `Загружено ${progress ?? 0}%`;
        }
        if (status === 'pdf_to_markdown') {
            return `Обработано ${progress ?? 0}%`;
        }
        if (status === 'processing') {
            return `Обработано ${progress ?? 0}%`;
        }
        return null;
    };

    return (
        <>
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
                    const progressText = getProgressText(doc.processing_status, doc.uid);
                    
                    console.log('Отображение документа:', doc.uid, 'статус:', doc.processing_status, 'прогресс:', progressText);
                    
                    return (
                        <div
                            key={doc.uid}
                            className={`${s.fileItem} ${selectedDocument?.uid === doc.uid ? 'bg-blue-100' : ''}`}
                            onClick={() => onSelectDocument(doc)}
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
                                        {progressText && (
                                            <span className="text-blue-600 font-semibold"> {progressText}</span>
                                        )}
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
                            await loadDocuments();
                            onDocumentsChange();
                        } catch (err) {
                            console.error('Ошибка удаления документа:', err);
                        }
                    }}
                    onClose={() => setContextMenu(null)}
                />
            )}
        </>
    );
}