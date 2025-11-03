import React, { useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react';
import s from './Data_extraction.module.css';
import PDFAnnotation from './PDFAnnotation';
import { uploadPdfForExtraction, importAnnotations as apiImportAnnotations, exportAnnotations as apiExportAnnotations, getDocumentAssets, deleteDocument as apiDeleteDocument, listDocuments, saveMarkdown } from '../../services/api';
import MarkdownAnnotator from './MarkdownAnnotator';
import MarkdownEditor from '../MarkdownEditor/MarkdownEditor';
import { AnnotationWorkspace } from './Annotation';

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

interface Annotation {
    uid: string;
    annotation_type: string;
    content: string;
    confidence?: number;
    page_number?: number;
    bbox?: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    metadata?: any;
}

interface ManualAnnotation {
    id: string;
    type: 'entity' | 'relation';
    content: string;
    start: number;
    end: number;
    label: string;
    confidence?: number;
    page?: number;
    bbox?: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
}

interface Relation {
    id: string;
    source: string;
    target: string;
    type: string;
    confidence?: number;
}

export default function Data_extraction() {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [manualAnnotations, setManualAnnotations] = useState<ManualAnnotation[]>([]);
    const [relations, setRelations] = useState<Relation[]>([]);
    const [markdownContent, setMarkdownContent] = useState<string>('');
    const [imageUrls, setImageUrls] = useState<Record<string,string>>({});
    const [pdfUrl, setPdfUrl] = useState<string>('');
    const [isUploading, setIsUploading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showAnnotationMode, setShowAnnotationMode] = useState(false);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    const [docId, setDocId] = useState<string>('');

    // Новый state для исходного markdown и auto-save
    const [sourceMarkdown, setSourceMarkdown] = useState<string>('');
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
    const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);
    const pdfViewerRef = useRef<HTMLIFrameElement>(null);
    const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const cursorPositionRef = useRef<number | null>(null);

    // Загружаем список документов при монтировании компонента
    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            const data = await listDocuments();
            if (data?.success && Array.isArray(data.documents)) {
                // маппинг в локальный тип PDFDocument с проверкой реального статуса
                const mapped = await Promise.all(data.documents.map(async (d) => {
                    let status = d.has_markdown ? 'annotated' : 'uploaded';
                    
                    // Проверяем реальный статус через API маркера
                    try {
                        const response = await fetch(`http://localhost:8000/api/marker/status/doc/${d.doc_id}`);
                        if (response.ok) {
                            const markerStatus = await response.json();
                            if (markerStatus.status === 'processing') {
                                status = 'processing';
                            } else if (markerStatus.status === 'failed') {
                                status = 'error';
                            } else if (markerStatus.status === 'ready' && markerStatus.percent === 100) {
                                status = 'annotated';
                            }
                        }
                    } catch (err) {
                        console.warn(`Не удалось проверить статус для ${d.doc_id}:`, err);
                    }
                    
                    // формируем возможный pdf url из списка документов, если доступен
                    const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
                    const pdf_url = d.files?.pdf ? `${base}${d.files.pdf}` : '';

                    return {
                        uid: d.doc_id,
                        original_filename: d.files?.pdf?.split('/').pop() || d.doc_id + '.pdf',
                        md5_hash: d.doc_id,
                        upload_date: new Date().toISOString(),
                        processing_status: status,
                        is_processed: status === 'annotated',
                        pdf_url,
                    } as any;
                }));
                setDocuments(mapped);
            }
        } catch (err) {
            console.error('Ошибка загрузки документов:', err);
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
        // Загружаем markdown и изображения из S3
        try {
            const assets = await getDocumentAssets(document.uid);
            if (assets?.markdown) {
                // Устанавливаем и исходный markdown, и rendered markdown
                setSourceMarkdown(assets.markdown);
                setMarkdownContent(assets.markdown);
                setProgressMap(prev => ({ ...prev, [document.uid]: 100 }));
                console.log('Markdown загружен:', assets.markdown.length, 'символов');
            } else {
                console.log('Markdown не найден для документа:', document.uid);
                setSourceMarkdown('');
                setMarkdownContent('');
            }
            if (assets?.image_urls) {
                setImageUrls(assets.image_urls);
                console.log('Изображения загружены:', Object.keys(assets.image_urls));
            } else {
                setImageUrls({});
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
            setMarkdownContent('');
            setImageUrls({});
            setPdfUrl('');
        }
    };

    // Обработчик изменений в textarea (Исходный Markdown)
    const handleSourceMarkdownChange = useCallback((newMarkdown: string) => {
        // Сохраняем позицию курсора перед обновлением в ref
        if (textareaRef.current) {
            cursorPositionRef.current = textareaRef.current.selectionStart;
        }

        setSourceMarkdown(newMarkdown);

        // НЕ обновляем markdownContent пока textarea в фокусе
        // Обновление произойдет при потере фокуса

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


    // Восстанавливаем позицию курсора после каждого рендера
    useLayoutEffect(() => {
        if (textareaRef.current && cursorPositionRef.current !== null) {
            textareaRef.current.setSelectionRange(cursorPositionRef.current, cursorPositionRef.current);
            cursorPositionRef.current = null; // Сбрасываем после восстановления
        }
    });

    // Cleanup timeout при unmount
    useEffect(() => {
        return () => {
            if (saveTimeoutRef.current) {
                clearTimeout(saveTimeoutRef.current);
            }
        };
    }, []);

    // Пуллинг прогресса обработки: проверяем реальный статус через API
    useEffect(() => {
        const interval = setInterval(async () => {
            const current = selectedDocument;
            if (!current) return;
            if (current.processing_status !== 'annotated') {
                try {
                    // Проверяем статус через API маркера
                    const response = await fetch(`http://localhost:8000/api/marker/status/doc/${current.uid}`);
                    if (response.ok) {
                        const status = await response.json();
                        if (status.status === 'ready' && status.percent === 100) {
                            // Документ готов, загружаем markdown
                            const assets = await getDocumentAssets(current.uid);
                            if (assets?.markdown) {
                                setMarkdownContent(assets.markdown);
                                setImageUrls(assets.image_urls || {});
                                setProgressMap(prev => ({ ...prev, [current.uid]: 100 }));
                                // обновляем локальный статус
                                setSelectedDocument(prev => prev ? { ...prev, processing_status: 'annotated', is_processed: true } as any : prev);
                                console.log('Обработка завершена, markdown загружен:', assets.markdown.length, 'символов');
                            }
                        } else if (status.status === 'processing') {
                            // Обновляем реальный прогресс
                            setProgressMap(prev => ({ ...prev, [current.uid]: status.percent || 0 }));
                        } else if (status.status === 'failed') {
                            // Обработка не удалась
                            setProgressMap(prev => ({ ...prev, [current.uid]: 0 }));
                            setSelectedDocument(prev => prev ? { ...prev, processing_status: 'error' } as any : prev);
                        }
                    }
                } catch (err) {
                    console.error('Ошибка проверки статуса:', err);
                }
            }
        }, 2000); // Проверяем каждые 2 секунды
        return () => clearInterval(interval);
    }, [selectedDocument]);

    const generateMarkdownFromAnnotations = (anns: Annotation[], manualAnns: ManualAnnotation[] = [], rels: Relation[] = []) => {
        let markdown = '# Аннотированный документ\n\n';
        
        // Группируем автоматические аннотации по типам
        const groupedAnnotations = anns.reduce((acc, ann) => {
            if (!acc[ann.annotation_type]) {
                acc[ann.annotation_type] = [];
            }
            acc[ann.annotation_type].push(ann);
            return acc;
        }, {} as Record<string, Annotation[]>);

        // Добавляем заголовок
        if (groupedAnnotations.title) {
            markdown += `## ${groupedAnnotations.title[0].content}\n\n`;
        }

        // Добавляем авторов
        if (groupedAnnotations.author) {
            markdown += `**Авторы:** ${groupedAnnotations.author.map(a => a.content).join(', ')}\n\n`;
        }

        // Добавляем аннотацию
        if (groupedAnnotations.abstract) {
            markdown += `**Аннотация:**\n${groupedAnnotations.abstract[0].content}\n\n`;
        }

        // Добавляем ключевые слова
        if (groupedAnnotations.keyword) {
            markdown += `**Ключевые слова:** ${groupedAnnotations.keyword.map(k => k.content).join(', ')}\n\n`;
        }

        // Добавляем остальные автоматические аннотации
        Object.entries(groupedAnnotations).forEach(([type, items]) => {
            if (!['title', 'author', 'abstract', 'keyword'].includes(type)) {
                markdown += `## ${type.charAt(0).toUpperCase() + type.slice(1)}\n\n`;
                items.forEach(item => {
                    markdown += `- ${item.content}`;
                    if (item.confidence) {
                        markdown += ` (уверенность: ${(item.confidence * 100).toFixed(1)}%)`;
                    }
                    markdown += '\n';
                });
                markdown += '\n';
            }
        });

        // Добавляем ручные аннотации
        if (manualAnns.length > 0) {
            markdown += `## Ручные аннотации\n\n`;
            const groupedManual = manualAnns.reduce((acc, ann) => {
                if (!acc[ann.label]) {
                    acc[ann.label] = [];
                }
                acc[ann.label].push(ann);
                return acc;
            }, {} as Record<string, ManualAnnotation[]>);

            Object.entries(groupedManual).forEach(([label, items]) => {
                markdown += `### ${label.charAt(0).toUpperCase() + label.slice(1)}\n\n`;
                items.forEach(item => {
                    markdown += `- ${item.content}`;
                    if (item.confidence) {
                        markdown += ` (уверенность: ${(item.confidence * 100).toFixed(1)}%)`;
                    }
                    markdown += '\n';
                });
                markdown += '\n';
            });
        }

        // Добавляем связи
        if (rels.length > 0) {
            markdown += `## Связи\n\n`;
            rels.forEach(rel => {
                const sourceAnn = manualAnns.find(a => a.id === rel.source);
                const targetAnn = manualAnns.find(a => a.id === rel.target);
                if (sourceAnn && targetAnn) {
                    markdown += `- **${sourceAnn.content}** → *${rel.type}* → **${targetAnn.content}**\n`;
                }
            });
            markdown += '\n';
        }

        setMarkdownContent(markdown);
    };

    const downloadPDF = () => {
        if (selectedDocument) {
            const link = document.createElement('a');
            link.href = `http://localhost:8000/api/s3/buckets/knowledge-map-pdfs/objects/documents/${selectedDocument.uid}/${selectedDocument.uid}.pdf`;
            link.download = selectedDocument.original_filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    };

    const handleAnnotationsChange = (newAnnotations: ManualAnnotation[], newRelations: Relation[]) => {
        setManualAnnotations(newAnnotations);
        setRelations(newRelations);
        
        // Обновляем Markdown с учетом ручных аннотаций
        generateMarkdownFromAnnotations(annotations, newAnnotations, newRelations);
    };

    // Label Studio удаляем — используем свой аннотатор
    const createLabelStudioProject = async () => { return; };
    const openLabelStudioDirectly = () => { return; };

    const loadLabelStudioAnnotations = async () => { return; };

    const startAnnotation = async () => {
        // Обработка запускается автоматически на бэкенде после загрузки /data_extraction
        setIsProcessing(true);
        setTimeout(() => setIsProcessing(false), 5000);
    };

    const onExportAnnotations = async () => {
        if (!docId) return;
        try {
            const json = await apiExportAnnotations(docId);
            const a = document.createElement('a');
            const blob = new Blob([json], { type: 'application/json' });
            a.href = URL.createObjectURL(blob);
            a.download = `${docId}_annotations.json`;
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            setError('Не удалось экспортировать аннотации');
        }
    };

    const onImportAnnotations = async (file: File) => {
        if (!docId) return;
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            await apiImportAnnotations(docId, data);
        } catch (e) {
            setError('Не удалось импортировать аннотации');
        }
    };

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
                    {documents.map((doc) => (
                        <div 
                            key={doc.uid}
                            className={`${s.fileItem} ${selectedDocument?.uid === doc.uid ? 'bg-blue-100' : ''}`}
                            onClick={() => selectDocument(doc)}
                        >
                            <div className="flex items-center gap-2 min-w-0">
                                <span className={getStatusClass(doc.processing_status)}></span>
                                <div className="min-w-0">
                                    <p className="font-medium truncate" title={doc.original_filename}>{doc.original_filename}</p>
                                    <p className="text-xs text-gray-500">
                                        {getStatusText(doc.processing_status)}
                                        {doc.processing_status === 'processing' ? (
                                            <span className="text-blue-600 font-semibold"> {progressMap[doc.uid] ?? 0}%</span>
                                        ) : null}
                                    </p>
                                </div>
                            </div>
                            <button
                                className={`deleteButton`}
                                onClick={async (e) => {
                                    e.stopPropagation();
                                    try {
                                        await apiDeleteDocument(doc.uid);
                                        if (selectedDocument?.uid === doc.uid) {
                                            setSelectedDocument(null);
                                            setMarkdownContent('');
                                            setDocId('');
                                        }
                                        await loadDocuments();
                                    } catch {}
                                }}
                            >
                                Удалить
                            </button>
                        </div>
                    ))}
                </div>
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

            {/* Колонка: Исходный Markdown с инструментом аннотирования */}
            <div className={s.sourceMarkdownColumn}>
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-base font-bold">Исходный Markdown</h2>
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
                        />
                    </div>
                ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                        Выберите документ для просмотра
                    </div>
                )}
            </div>

            {/* Правая колонка: Предпросмотр Markdown */}
            <div className={s.rightColumn}>
                <h2 className="text-base font-bold mb-3">Предпросмотр Markdown</h2>
                {selectedDocument && docId ? (
                    <div style={{ height: 'calc(100% - 40px)' }}>
                        <MarkdownEditor
                            value={markdownContent}
                            onChange={() => {}}
                            readOnly={true}
                        />
                    </div>
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        <p>Выберите документ для предпросмотра</p>
                    </div>
                )}
            </div>
        </main>
    );
}
