import { useState, useRef, useCallback, useEffect } from 'react';
import { getDocumentAssets, saveMarkdown } from '../../../services/api';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import type { PDFDocument, SaveStatus } from '../model';

interface UseDocumentStateResult {
    selectedDocument: PDFDocument | null;
    pdfUrl: string;
    sourceMarkdown: string;
    saveStatus: SaveStatus;
    lastSavedAt: Date | null;
    isSaving: boolean;
    selectDocument: (document: PDFDocument | null) => Promise<void>;
    handleSourceMarkdownChange: (newMarkdown: string) => void;
    handleManualSave: () => Promise<void>;
    updateDocumentStatus: (docId: string, newStatus: string) => void;
}

export function useDocumentState(
    onNlpProcessingChange?: (processing: boolean) => void
): UseDocumentStateResult {
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [pdfUrl, setPdfUrl] = useState<string>('');
    const [sourceMarkdown, setSourceMarkdown] = useState<string>('');
    const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
    const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    const saveTimeoutRef = useRef<number | null>(null);
    const selectTokenRef = useRef<number>(0);
    const requireAuth = useRequireAuth();

    const selectDocument = useCallback(async (document: PDFDocument | null) => {
        if (!document) {
            setSelectedDocument(null);
            setPdfUrl('');
            setSourceMarkdown('');
            return;
        }

        const token = ++selectTokenRef.current;

        setSelectedDocument(document);
        setSourceMarkdown('');

        if (document.uid.startsWith('upload_') || document.processing_status === 'uploading') {
            setPdfUrl('');
            return;
        }

        try {
            const assets = await getDocumentAssets(document.uid);
            if (token !== selectTokenRef.current) return;

            if (assets?.markdown) {
                setSourceMarkdown(assets.markdown);
            }

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
            if (token !== selectTokenRef.current) return;
            setPdfUrl('');
        }
    }, []);

    const updateDocumentStatus = useCallback((docId: string, newStatus: string) => {
        setSelectedDocument(prev => {
            if (prev && prev.uid === docId) {
                return { ...prev, processing_status: newStatus, is_processed: newStatus === 'annotated' };
            }
            return prev;
        });
    }, []);

    const handleSourceMarkdownChange = useCallback((newMarkdown: string) => {
        setSourceMarkdown(newMarkdown);
        setSaveStatus('idle');

        if (saveTimeoutRef.current) {
            window.clearTimeout(saveTimeoutRef.current);
        }
    }, []);

    const handleManualSave = useCallback(async () => {
        if (!selectedDocument) return;
        if (!requireAuth()) return;

        try {
            setSaveStatus('saving');
            setIsSaving(true);

            const result = await saveMarkdown(selectedDocument.uid, sourceMarkdown, true);

            // Статус 'Аннотирован' только для валидного markdown:
            // невалидный текст сохраняется, но статус не меняется
            if (result?.validation?.is_valid) {
                updateDocumentStatus(selectedDocument.uid, 'annotated');
            }

            setSaveStatus('saved');
            setLastSavedAt(new Date());

            setTimeout(() => {
                setSaveStatus('idle');
            }, 3000);
        } catch (err) {
            setSaveStatus('error');
            // Пробрасываем ошибку наверх для отображения в UI
            throw err;
        } finally {
            setIsSaving(false);
        }
    }, [selectedDocument, sourceMarkdown, updateDocumentStatus, requireAuth]);

    useEffect(() => {
        return () => {
            if (saveTimeoutRef.current) {
                window.clearTimeout(saveTimeoutRef.current);
            }
        };
    }, []);

    return {
        selectedDocument,
        pdfUrl,
        sourceMarkdown,
        saveStatus,
        lastSavedAt,
        isSaving,
        selectDocument,
        handleSourceMarkdownChange,
        handleManualSave,
        updateDocumentStatus,
    };
}
