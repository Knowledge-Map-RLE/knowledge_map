import React, { useState, useRef, useCallback, useEffect } from 'react';
import s from './Data_extraction.module.css';
import PDFAnnotation from './PDFAnnotation';
import { uploadPdfForExtraction, importAnnotations as apiImportAnnotations, exportAnnotations as apiExportAnnotations, getDocumentAssets, deleteDocument as apiDeleteDocument, listDocuments } from '../../services/api';
import MarkdownAnnotator from './MarkdownAnnotator';

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
    const [isUploading, setIsUploading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showAnnotationMode, setShowAnnotationMode] = useState(false);
    const [progressMap, setProgressMap] = useState<Record<string, number>>({});
    const [docId, setDocId] = useState<string>('');
    
    const fileInputRef = useRef<HTMLInputElement>(null);
    const pdfViewerRef = useRef<HTMLIFrameElement>(null);

    // Загружаем список документов при монтировании компонента
    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            const data = await listDocuments();
            if (data?.success && Array.isArray(data.documents)) {
                // маппинг в локальный тип PDFDocument
                const mapped = data.documents.map(d => ({
                    uid: d.doc_id,
                    original_filename: d.files?.pdf?.split('/').pop() || d.doc_id + '.pdf',
                    md5_hash: d.doc_id,
                    upload_date: new Date().toISOString(),
                    processing_status: d.has_markdown ? 'annotated' : 'uploaded',
                    is_processed: !!d.has_markdown,
                })) as any[];
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
                setMarkdownContent(assets.markdown);
                setProgressMap(prev => ({ ...prev, [document.uid]: 100 }));
            }
            if (assets?.image_urls) {
                setImageUrls(assets.image_urls);
            } else {
                setImageUrls({});
            }
        } catch (err) {
            console.error('Ошибка загрузки документа:', err);
        }
    };

    // Пуллинг прогресса обработки: если документ в статусе processing/uploaded без markdown — увеличиваем проценты и проверяем assets
    useEffect(() => {
        const interval = setInterval(async () => {
            const current = selectedDocument;
            if (!current) return;
            if (current.processing_status !== 'annotated') {
                try {
                    const assets = await getDocumentAssets(current.uid);
                    if (assets?.markdown) {
                        setMarkdownContent(assets.markdown);
                        setProgressMap(prev => ({ ...prev, [current.uid]: 100 }));
                        // обновляем локальный статус
                        setSelectedDocument(prev => prev ? { ...prev, processing_status: 'annotated', is_processed: true } as any : prev);
                    } else {
                        // плавное увеличение: максимум до 95%
                        setProgressMap(prev => {
                            const val = Math.min(95, (prev[current.uid] ?? 10) + 3);
                            return { ...prev, [current.uid]: val };
                        });
                    }
                } catch {}
            }
        }, 5000);
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
            link.href = `http://localhost:8000/api/pdf/document/${selectedDocument.uid}/download`;
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
            {/* Верхняя левая - загрузка PDF */}
            <div className={s.topLeft}>
                <h2 className="text-xl font-bold mb-4">Загрузка PDF документов</h2>
                
                {/* Область загрузки */}
                <div 
                    className={`${s.uploadArea} ${dragOver ? s.dragover : ''}`}
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onClick={() => fileInputRef.current?.click()}
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
                            <p className="text-lg mb-2">Перетащите PDF файл сюда или нажмите для выбора</p>
                            <p className="text-sm text-gray-500">Поддерживаются только PDF файлы</p>
                        </div>
                    )}
                </div>

                {/* Ошибки */}
                {error && (
                    <div className="mt-4 p-3 bg-red-100 border border-red-300 rounded-lg text-red-700">
                        {error}
                    </div>
                )}
            </div>

            {/* Верхняя правая - список документов */}
            <div className={s.topRight}>
                <h2 className="text-xl font-bold mb-4">Загруженные документы</h2>
                
                <div className={s.fileList}>
                    {documents.map((doc) => (
                        <div 
                            key={doc.uid}
                            className={`${s.fileItem} ${selectedDocument?.uid === doc.uid ? 'bg-blue-100' : ''}`}
                            onClick={() => selectDocument(doc)}
                        >
                            <div className="flex items-center">
                                <span className={getStatusClass(doc.processing_status)}></span>
                                <div>
                                    <p className="font-medium">{doc.original_filename}</p>
                                    <p className="text-sm text-gray-500">
                                        {getStatusText(doc.processing_status)}
                                        {doc.processing_status === 'processing' ? (
                                            <>
                                                {' '}
                                                <span className="text-blue-600 font-semibold">
                                                    {Math.min( (progressMap[doc.uid] ?? 10), 100)}%
                                                </span>
                                            </>
                                        ) : null}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    className={`${s.button} ${s.danger}`}
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
                            {doc.processing_status === 'uploaded' && (
                                <button
                                    className={`${s.button} ${s.primary}`}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        startAnnotation();
                                    }}
                                    disabled={isProcessing}
                                >
                                    Аннотировать
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* Нижняя левая - просмотр PDF и аннотации */}
            <div className={s.bottomLeft}>
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold">Просмотр и аннотации</h2>
                    <div className="flex gap-2">
                        {selectedDocument && (
                            <>
                                <button
                                    onClick={() => setShowAnnotationMode(!showAnnotationMode)}
                                    className={`${s.button} ${showAnnotationMode ? s.primary : ''} px-4 py-2`}
                                >
                                    {showAnnotationMode ? 'Режим просмотра' : 'Аннотатор'}
                                </button>
                                <button
                                    onClick={downloadPDF}
                                    className={`${s.button} px-4 py-2`}
                                >
                                    Скачать PDF
                                </button>
                                <label className={`${s.button} px-4 py-2`}>
                                    Импорт аннотаций
                                    <input type="file" accept="application/json" className="hidden" onChange={(e) => {
                                        const f = e.target.files?.[0];
                                        if (f) onImportAnnotations(f);
                                    }} />
                                </label>
                                <button className={`${s.button} px-4 py-2`} onClick={onExportAnnotations}>Экспорт аннотаций</button>
                            </>
                        )}
                    </div>
                </div>
                
                {selectedDocument ? (
                    showAnnotationMode ? (
                        <div className="flex items-center justify-center h-full text-gray-500">
                            <p>Откройте аннотатор Markdown, созданный для документа (HTML сохраняется рядом в S3).</p>
                        </div>
                    ) : (
                        <div className={s.pdfViewer}>
                            <MarkdownAnnotator
                              docId={docId}
                              markdown={markdownContent}
                              images={[]}
                              imageUrls={imageUrls}
                              onExport={(json) => {
                                // скачиваем локально и отправляем в backend при необходимости
                                const blob = new Blob([JSON.stringify(json, null, 2)], { type:'application/json' });
                                const a = document.createElement('a');
                                a.href = URL.createObjectURL(blob);
                                a.download = `${docId || 'annotations'}.json`;
                                a.click();
                                URL.revokeObjectURL(a.href);
                              }}
                              onImport={async (data) => {
                                if (!docId) return;
                                await apiImportAnnotations(docId, data);
                              }}
                            />
                        </div>
                    )
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        <p>Выберите документ для просмотра</p>
                    </div>
                )}
            </div>

            {/* Нижняя правая - аннотации в Markdown */}
            <div className={s.bottomRight}>
                <h2 className="text-xl font-bold mb-4">Аннотации в Markdown</h2>
                
                {selectedDocument ? (
                    <div className={s.markdownViewer}>
                        {markdownContent ? (
                            <pre className="whitespace-pre-wrap text-sm">{markdownContent}</pre>
                        ) : (
                            <p className="text-gray-500">Аннотации не найдены</p>
                        )}
                    </div>
                ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                        <p>Выберите документ для просмотра аннотаций</p>
                    </div>
                )}
            </div>
        </main>
    );
}
