import React, { useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react';
import s from './Data_extraction.module.css';
import { importAnnotations as apiImportAnnotations, exportAnnotations as apiExportAnnotations, getDocumentAssets, saveMarkdown } from '../../services/api';
import { AnnotationWorkspace } from './Annotation';
import MarkdownEditor from '../MarkdownEditor/MarkdownEditor';
import Header from '../Header';
import { PatternGenerator } from './Patterns';
import Document_downloader_ui from './Document_downloader_ui';
import type { DocumentListHandle } from './Document_downloader_ui';

// Для исправления ошибки с NodeJS.Timeout
declare global {
  namespace NodeJS {
    interface Timeout {}
  }
}

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
    const [activeTab, setActiveTab] = useState<'pdf' | 'markdown' | 'annotator'>('pdf');
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [pdfUrl, setPdfUrl] = useState<string>('');
    const [error, setError] = useState<string | null>(null);
    const [docId, setDocId] = useState<string>('');

    // Новый state для исходного markdown и auto-save
    const [sourceMarkdown, setSourceMarkdown] = useState<string>('');
    const [isSaving, setIsSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
    const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

    const saveTimeoutRef = useRef<number | null>(null);
    const docListRef = useRef<DocumentListHandle>(null);

    const selectDocument = async (document: PDFDocument | null) => {
        if (!document) {
            setSelectedDocument(null);
            setDocId('');
            setSourceMarkdown('');
            setPdfUrl('');
            return;
        }
        setSelectedDocument(document);
        setDocId(document.uid);
        // Загружаем markdown из S3
        try {
            const assets = await getDocumentAssets(document.uid);
            if (assets?.markdown) {
                setSourceMarkdown(assets.markdown);
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

    const updateDocumentStatus = (docId: string, newStatus: string) => {
        setSelectedDocument(prev => {
            if (prev && prev.uid === docId) {
                return { ...prev, processing_status: newStatus, is_processed: newStatus === 'annotated' };
            }
            return prev;
        });
    };

    // Обработчик изменений в markdown
    const handleSourceMarkdownChange = useCallback((newMarkdown: string) => {
        setSourceMarkdown(newMarkdown);
        setSaveStatus('idle');

        // Отменяем предыдущий таймер (если был)
        if (saveTimeoutRef.current) {
            window.clearTimeout(saveTimeoutRef.current);
        }
    }, []);

    // Функция для ручного сохранения markdown (вызывается по кнопке "Сохранить")
    const handleManualSave = useCallback(async () => {
        if (!selectedDocument) return;

        try {
            setSaveStatus('saving');
            setIsSaving(true);

            await saveMarkdown(selectedDocument.uid, sourceMarkdown);
            await docListRef.current?.reloadDocuments();

            setSaveStatus('saved');
            setLastSavedAt(new Date());
            console.log('Markdown сохранен в S3');
            
            // Update document status to 'annotated' after successful save
            updateDocumentStatus(selectedDocument.uid, 'annotated');

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
                window.clearTimeout(saveTimeoutRef.current);
            }
        };
    }, []);

    return (
        <main className={s.dex}>
            {/* Шапка */}
            <Header showSearch={true} className={s.headerRow} />

            {/* Основная строка */}
            <div className={s.mainRow}>
                {/* Левая колонка: Загруженные документы */}
                <div className={s.leftColumn}>
                    <Document_downloader_ui
                        ref={docListRef}
                        selectedDocument={selectedDocument}
                        onSelectDocument={selectDocument}
                        onDocumentsChange={() => {}}
                        error={error}
                        setError={setError}
                    />
                </div>

                {/* Правая панель: вкладки */}
                <div className={s.rightPanel}>
                    <div className={s.tabBar}>
                        <button
                            className={`${s.tabButton} ${activeTab === 'pdf' ? s.active : ''}`}
                            onClick={() => setActiveTab('pdf')}
                        >
                            Исходный PDF
                        </button>
                        <button
                            className={`${s.tabButton} ${activeTab === 'markdown' ? s.active : ''}`}
                            onClick={() => setActiveTab('markdown')}
                        >
                            Предпросмотр Markdown
                        </button>
                        <button
                            className={`${s.tabButton} ${activeTab === 'annotator' ? s.active : ''}`}
                            onClick={() => setActiveTab('annotator')}
                        >
                            Аннотатор
                        </button>
                        {saveStatus !== 'idle' && (
                            <div className={`${s.saveIndicator} ${s[saveStatus]}`} style={{ marginLeft: 'auto' }}>
                                {saveStatus === 'saving' && <><div className={s.loadingSpinner} style={{ width: '12px', height: '12px' }}></div><span>Сохранение...</span></>}
                                {saveStatus === 'saved' && <><span>✓</span><span>Сохранено {lastSavedAt ? new Date(lastSavedAt).toLocaleTimeString() : ''}</span></>}
                                {saveStatus === 'error' && <><span>✗</span><span>Ошибка сохранения</span></>}
                            </div>
                        )}
                    </div>

                    <div className={s.tabContent}>
                        {/* PDF */}
                        {activeTab === 'pdf' && (
                            <div id="km-pdf-pane" className={s.pdfViewer} style={{ overflow: 'auto', flex: 1, borderRadius: 0, border: 'none' }}>
                                {pdfUrl ? (
                                    <iframe
                                        id="km-pdf-viewer"
                                        title="PDF"
                                        src={pdfUrl}
                                        style={{ width: '100%', height: '100%', border: '0' }}
                                    />
                                ) : selectedDocument ? (
                                    <div className="w-full h-full flex flex-col items-center justify-center gap-3 px-8 text-center">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                        </svg>
                                        <p className="text-gray-500 font-medium">PDF недоступен для этого документа</p>
                                        <p className="text-gray-400 text-sm">Для статей из PubMed/PMC без открытого доступа PDF не предоставляется.<br/>Используйте вкладки <strong>Предпросмотр Markdown</strong> или <strong>Аннотатор</strong> для работы с текстом.</p>
                                    </div>
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
                                )}
                            </div>
                        )}

                        {/* Markdown */}
                        {activeTab === 'markdown' && (
                            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                                {selectedDocument ? (
                                    <MarkdownEditor
                                        value={sourceMarkdown}
                                        onChange={() => {}}
                                        readOnly={true}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                                        Выберите файл
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Аннотатор */}
                        {activeTab === 'annotator' && (
                            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                                {selectedDocument && docId ? (
                                    <AnnotationWorkspace
                                        docId={docId}
                                        text={sourceMarkdown}
                                        readOnly={false}
                                        onTextChange={handleSourceMarkdownChange}
                                        onSave={handleManualSave}
                                        documentTitle={selectedDocument.title || selectedDocument.original_filename}
                                        onUpdateDocumentStatus={updateDocumentStatus}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                                        Выберите файл
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </main>
    );
}
