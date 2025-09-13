import React, { useState, useRef, useCallback, useEffect } from 'react';
import s from './Data_extraction.module.css';

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

export default function Data_extraction() {
    const [documents, setDocuments] = useState<PDFDocument[]>([]);
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [markdownContent, setMarkdownContent] = useState<string>('');
    const [isUploading, setIsUploading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [error, setError] = useState<string | null>(null);
    
    const fileInputRef = useRef<HTMLInputElement>(null);
    const pdfViewerRef = useRef<HTMLIFrameElement>(null);

    // Загружаем список документов при монтировании компонента
    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            // TODO: Заменить на реальный API вызов
            const response = await fetch('http://localhost:8000/api/pdf/documents?user_id=test_user');
            if (response.ok) {
                const docs = await response.json();
                setDocuments(docs);
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
            const formData = new FormData();
            formData.append('file', file);
            formData.append('user_id', 'test_user'); // TODO: Получить реальный user_id

            const response = await fetch('http://localhost:8000/api/pdf/upload', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    await loadDocuments();
                    if (result.document_id) {
                        // Автоматически выбираем загруженный документ
                        const newDoc = documents.find(d => d.uid === result.document_id) || 
                                     { uid: result.document_id, original_filename: file.name, md5_hash: result.md5_hash, upload_date: new Date().toISOString(), processing_status: 'uploaded', is_processed: false };
                        setSelectedDocument(newDoc);
                    }
                }
            } else {
                const errorData = await response.json();
                setError(errorData.detail || 'Ошибка загрузки файла');
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
        
        // Загружаем аннотации для выбранного документа
        try {
            const response = await fetch(`http://localhost:8000/api/pdf/document/${document.uid}/annotations`);
            if (response.ok) {
                const anns = await response.json();
                setAnnotations(anns);
                
                // Генерируем Markdown из аннотаций
                generateMarkdownFromAnnotations(anns);
            }
        } catch (err) {
            console.error('Ошибка загрузки аннотаций:', err);
        }
    };

    const generateMarkdownFromAnnotations = (anns: Annotation[]) => {
        let markdown = '# Аннотированный документ\n\n';
        
        // Группируем аннотации по типам
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

        // Добавляем остальные аннотации
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

    const startAnnotation = async () => {
        if (!selectedDocument) return;

        setIsProcessing(true);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('user_id', 'test_user'); // TODO: Получить реальный user_id

            const response = await fetch(`http://localhost:8000/api/pdf/document/${selectedDocument.uid}/annotate`, {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                // Обновляем статус документа
                setSelectedDocument(prev => prev ? { ...prev, processing_status: 'processing' } : null);
                
                // Периодически проверяем статус обработки
                const checkStatus = setInterval(async () => {
                    try {
                        const statusResponse = await fetch(`http://localhost:8000/api/pdf/document/${selectedDocument.uid}`);
                        if (statusResponse.ok) {
                            const doc = await statusResponse.json();
                            if (doc.processing_status === 'annotated') {
                                clearInterval(checkStatus);
                                setIsProcessing(false);
                                await selectDocument(doc);
                            } else if (doc.processing_status === 'error') {
                                clearInterval(checkStatus);
                                setIsProcessing(false);
                                setError('Ошибка обработки документа');
                            }
                        }
                    } catch (err) {
                        console.error('Ошибка проверки статуса:', err);
                    }
                }, 2000);

                // Останавливаем проверку через 5 минут
                setTimeout(() => {
                    clearInterval(checkStatus);
                    setIsProcessing(false);
                }, 300000);
            } else {
                const errorData = await response.json();
                setError(errorData.detail || 'Ошибка запуска аннотации');
                setIsProcessing(false);
            }
        } catch (err) {
            setError('Ошибка запуска аннотации');
            setIsProcessing(false);
            console.error('Ошибка аннотации:', err);
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
                                    <p className="text-sm text-gray-500">{getStatusText(doc.processing_status)}</p>
                                </div>
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

            {/* Нижняя левая - просмотр PDF */}
            <div className={s.bottomLeft}>
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold">Просмотр и аннотации</h2>
                    {selectedDocument && (
                        <button
                            onClick={downloadPDF}
                            className={`${s.button} px-4 py-2`}
                        >
                            Скачать PDF
                        </button>
                    )}
                </div>
                
                {selectedDocument ? (
                    <div className={s.pdfViewer}>
                        <iframe
                            ref={pdfViewerRef}
                            src={`http://localhost:8000/api/pdf/document/${selectedDocument.uid}/view`}
                            className="w-full h-full"
                            title="PDF Viewer"
                        />
                    </div>
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
