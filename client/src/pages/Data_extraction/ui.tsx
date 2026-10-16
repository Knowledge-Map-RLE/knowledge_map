import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Header from '../../widgets/Header';
import MarkdownEditor from '../../widgets/MarkdownEditor';
import { AnnotationWorkspace } from './Annotation';
import { useAuth } from '../../entities/auth';
import { getDocumentProgress, reprocessDocument } from '../../services/api';

import Document_downloader_ui from './Document_downloader_ui';
import type { DocumentListHandle } from './Document_downloader_ui';
import { useDocumentState } from './hooks/useDocumentState';
import { ChatPanel } from '../Social_network/components/ChatPanel';
import type { ChatTarget } from '../Social_network/model';
import type { DataExtractionTab, PDFDocument } from './model';
import styles from './Data_extraction.module.css';

declare global {
    namespace NodeJS {
        interface Timeout {}
    }
}

const DataExtractionUI: React.FC = () => {
    const { t, i18n } = useTranslation();
    const { docId: routeDocId } = useParams<{ docId?: string }>();
    const navigate = useNavigate();
    const location = useLocation();
    const previousRouteDocId = useRef<string | undefined>(routeDocId);
    const [activeTab, setActiveTab] = useState<DataExtractionTab>('pdf');
    const [chatTarget, setChatTarget] = useState<ChatTarget | null>(null);
    const [isNlpProcessing, setIsNlpProcessing] = useState(false);
    const [isReprocessing, setIsReprocessing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const noopRef = useRef<() => void>(() => {});
    const documentListRef = useRef<DocumentListHandle>(null);
    const { isAuthenticated, user } = useAuth();
    const selectedDocumentIdRef = useRef<string | undefined>(undefined);

    const {
        selectedDocument,
        pdfUrl,
        sourceMarkdown,
        saveStatus,
        lastSavedAt,
        selectDocument,
        handleSourceMarkdownChange,
        handleManualSave,
        updateDocumentStatus,
    } = useDocumentState(setIsNlpProcessing);
    selectedDocumentIdRef.current = selectedDocument?.uid;

    const handleSelectDocument = useCallback((document: PDFDocument | null) => {
        void selectDocument(document);

        const nextPath = document && !document.uid.startsWith('upload_')
            ? `/data_extraction/${encodeURIComponent(document.uid)}`
            : '/data_extraction';
        if (location.pathname !== nextPath) navigate(nextPath);
    }, [location.pathname, navigate, selectDocument]);

    useEffect(() => {
        if (!routeDocId) {
            if (previousRouteDocId.current && selectedDocument?.uid === previousRouteDocId.current) {
                void selectDocument(null);
            }
            previousRouteDocId.current = undefined;
            return;
        }
        previousRouteDocId.current = routeDocId;
        if (selectedDocument?.uid === routeDocId) return;

        const linkedDocument: PDFDocument = {
            uid: routeDocId,
            original_filename: routeDocId,
            md5_hash: routeDocId,
            upload_date: new Date().toISOString(),
            processing_status: 'ready_for_annotation',
            is_processed: false,
        };
        void selectDocument(linkedDocument);
    }, [routeDocId, selectedDocument?.uid, selectDocument]);

    const openDocumentChat = useCallback(() => {
        if (!selectedDocument) return;
        setChatTarget({
            type: 'article',
            uid: selectedDocument.uid,
            label: selectedDocument.title || selectedDocument.original_filename,
        });
        setActiveTab('chat');
    }, [selectedDocument]);

    useEffect(() => {
        if (selectedDocument) {
            setChatTarget({
                type: 'article',
                uid: selectedDocument.uid,
                label: selectedDocument.title || selectedDocument.original_filename,
            });
        }
    }, [selectedDocument]);

    // После успешного сохранения перечитываем список документов,
    // чтобы статус 'Аннотирован' отобразился в левой колонке
    const handleSaveAndReload = async () => {
        await handleManualSave();
        await documentListRef.current?.reloadDocuments();
    };

    const handleReprocessDocument = useCallback(async () => {
        if (!selectedDocument || !isAuthenticated) return;

        const document = selectedDocument;
        const docId = document.uid;
        setError(null);
        setIsReprocessing(true);
        updateDocumentStatus(docId, 'pdf_to_markdown');

        try {
            await reprocessDocument(docId);
            const deadline = Date.now() + 60 * 60 * 1000;
            let processingObserved = true;

            while (Date.now() < deadline) {
                await new Promise((resolve) => window.setTimeout(resolve, 2000));
                const progress = await getDocumentProgress(docId);

                if (progress.processing_status === 'error' || progress.phase === 'error') {
                    throw new Error(progress.message || t('dataExtraction.errors.reprocess'));
                }

                if (
                    progress.processing_status === 'pdf_to_markdown'
                    || progress.percent > 0
                    || Boolean(progress.phase)
                ) {
                    processingObserved = true;
                }

                if (
                    processingObserved
                    && ['ready_for_annotation', 'annotated'].includes(progress.processing_status)
                ) {
                    if (selectedDocumentIdRef.current === docId) {
                        await selectDocument({
                            ...document,
                            processing_status: progress.processing_status,
                        });
                        await documentListRef.current?.reloadDocuments();
                    }
                    return;
                }
            }

            throw new Error(t('dataExtraction.errors.reprocessTimeout'));
        } catch (reprocessError) {
            if (selectedDocumentIdRef.current === docId) {
                updateDocumentStatus(docId, document.processing_status);
            }
            setError(
                reprocessError instanceof Error
                    ? reprocessError.message
                    : t('dataExtraction.errors.reprocess'),
            );
        } finally {
            setIsReprocessing(false);
        }
    }, [
        isAuthenticated,
        selectedDocument,
        selectDocument,
        t,
        updateDocumentStatus,
    ]);

    return (
        <main className={styles.dex}>
            <Header showSearch={true} className={styles.headerRow} />

            <div className={styles.mainRow}>
                <div className={styles.leftColumn}>
                    <Document_downloader_ui
                        ref={documentListRef}
                        selectedDocument={selectedDocument}
                        onSelectDocument={handleSelectDocument}
                        onDocumentsChange={noopRef.current}
                        error={error}
                        setError={setError}
                    />
                </div>

                <div className={styles.rightPanel}>
                    <div className={styles.tabBar}>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'markdown' ? styles.active : ''}`}
                            onClick={() => setActiveTab('markdown')}
                        >
                            {t('dataExtraction.tabs.markdown')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'annotator' ? styles.active : ''}`}
                            onClick={() => setActiveTab('annotator')}
                        >
                            {t('dataExtraction.tabs.annotator')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'pdf' ? styles.active : ''}`}
                            onClick={() => setActiveTab('pdf')}
                        >
                            {t('dataExtraction.tabs.pdf')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'chat' ? styles.active : ''}`}
                            onClick={openDocumentChat}
                            disabled={!selectedDocument}
                            title={selectedDocument ? t('dataExtraction.tabs.discussionTitle') : t('dataExtraction.empty.selectFirst')}
                        >
                            {t('dataExtraction.tabs.discussion')}
                        </button>

                        {isNlpProcessing && (
                            <div className={`${styles.saveIndicator} ${styles.saving}`} style={{ marginLeft: 'auto' }}>
                                <div className={styles.loadingSpinner} style={{ width: '12px', height: '12px' }}></div>
                                <span>{t('dataExtraction.status.nlp')}</span>
                            </div>
                        )}
                        {!isNlpProcessing && saveStatus !== 'idle' && (
                            <div className={`${styles.saveIndicator} ${styles[saveStatus]}`} style={{ marginLeft: 'auto' }}>
                                {saveStatus === 'saving' && <><div className={styles.loadingSpinner} style={{ width: '12px', height: '12px' }}></div><span>{t('dataExtraction.status.saving')}</span></>}
                                {saveStatus === 'saved' && <><span>✓</span><span>{t('dataExtraction.status.saved', { time: lastSavedAt ? new Date(lastSavedAt).toLocaleTimeString(i18n.resolvedLanguage === 'ru' ? 'ru-RU' : 'en-US') : '' })}</span></>}
                                {saveStatus === 'error' && <><span>✗</span><span>{t('dataExtraction.status.saveError')}</span></>}
                            </div>
                        )}
                        {selectedDocument && isAuthenticated && (
                            <button
                                className={styles.reprocessButton}
                                type="button"
                                onClick={() => void handleReprocessDocument()}
                                disabled={isReprocessing}
                                title={t('dataExtraction.actions.reprocessTitle')}
                            >
                                {isReprocessing
                                    ? t('dataExtraction.actions.reprocessing')
                                    : t('dataExtraction.actions.reprocess')}
                            </button>
                        )}
                    </div>

                    <div className={styles.tabContent}>
                        {activeTab === 'pdf' && (
                            <div className={styles.pdfViewer}>
                                {pdfUrl ? (
                                    <iframe
                                        title="PDF"
                                        src={pdfUrl}
                                        style={{ width: '100%', height: '100%', border: '0' }}
                                    />
                                ) : selectedDocument ? (
                                    <div className="w-full h-full flex flex-col items-center justify-center gap-3 px-8 text-center">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                        </svg>
                                        <p className="text-gray-500 font-medium">{t('dataExtraction.empty.pdfUnavailable')}</p>
                                    </div>
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">{t('dataExtraction.empty.selectFile')}</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'markdown' && (
                            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                                {selectedDocument ? (
                                    <MarkdownEditor
                                        value={sourceMarkdown}
                                        onChange={() => {}}
                                        readOnly={true}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">{t('dataExtraction.empty.selectFile')}</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'annotator' && (
                            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                                {selectedDocument && !['uploading', 'pdf_to_markdown'].includes(selectedDocument.processing_status) ? (
                                    <AnnotationWorkspace
                                        key={selectedDocument.uid}
                                        docId={selectedDocument.uid}
                                        text={sourceMarkdown}
                                        readOnly={false}
                                        onTextChange={handleSourceMarkdownChange}
                                        onSave={handleSaveAndReload}
                                        documentTitle={selectedDocument.title || selectedDocument.original_filename}
                                        onUpdateDocumentStatus={updateDocumentStatus}
                                        onNlpProcessingChange={setIsNlpProcessing}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">{t('dataExtraction.empty.selectFile')}</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'chat' && (
                            <div className={styles.chatContainer}>
                                {selectedDocument && isAuthenticated && user ? (
                                    <ChatPanel
                                        target={chatTarget}
                                        onOpenTarget={(t) => setChatTarget(t)}
                                        myUid={user.uid}
                                        hideRail
                                        title={selectedDocument.title || selectedDocument.original_filename || t('dataExtraction.tabs.discussionTitle')}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                                        {!selectedDocument ? t('dataExtraction.empty.selectFile') : t('dataExtraction.empty.loginForDiscussion')}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </main>
    );
};

export default DataExtractionUI;
