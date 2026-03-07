import React, { useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react';
import s from './Data_extraction.module.css';
import { importAnnotations as apiImportAnnotations, exportAnnotations as apiExportAnnotations, getDocumentAssets, saveMarkdown } from '../../services/api';
import { AnnotationWorkspace } from './Annotation';
import MarkdownEditor from '../MarkdownEditor/MarkdownEditor';
import Project_title from '../Project_title';
import Search from '../Search';
import User from '../User';
import { PatternGenerator } from './Patterns';
import Document_downloader_ui from './Document_downloader_ui';

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

    const selectDocument = async (document: PDFDocument) => {
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
            <div className={s.headerRow}>
                <Project_title className={s.headerPanel} />
                <Search className={s.headerPanel} />
                <User className={s.headerPanel} />
            </div>

            {/* Основная строка: 3 колонки */}
            <div className={s.topRow}>
                {/* Левая колонка: Загрузка встроена в список документов */}
                <div className={s.leftColumn}>
                    <Document_downloader_ui
                        selectedDocument={selectedDocument}
                        onSelectDocument={selectDocument}
                        onDocumentsChange={() => {
                            // При изменении списка документов ничего дополнительно делать не нужно
                            // setSelectedDocument останется тем же, если документ все еще существует
                            // или станет null, если выбранного документа больше нет
                        }}
                        error={error}
                        setError={setError}
                    />
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
                                onUpdateDocumentStatus={updateDocumentStatus}
                            />
                        </div>
                    ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                            Выберите документ для аннотирования
                        </div>
                    )}
                </div>
            </div>
        </main>
    );
}
