import React, { useState } from 'react';
import Header from '../../widgets/Header';
import MarkdownEditor from '../../widgets/MarkdownEditor';
import { AnnotationWorkspace } from './Annotation';
import { LinguisticPatternAnalysis } from './Patterns';

import { ArticleActionGraph } from './Patterns/ArticleActionGraph';
import { ArticleLinguisticGraph } from './Patterns/ArticleLinguisticGraph';
import Document_downloader_ui from './Document_downloader_ui';
import type { DocumentListHandle } from './Document_downloader_ui';
import { useDocumentState } from './hooks/useDocumentState';
import type { DataExtractionTab } from './model';
import styles from './Data_extraction.module.css';

declare global {
    namespace NodeJS {
        interface Timeout {}
    }
}

const DataExtractionUI: React.FC = () => {
    const [activeTab, setActiveTab] = useState<DataExtractionTab>('pdf');
    const [isNlpProcessing, setIsNlpProcessing] = useState(false);

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

    return (
        <main className={styles.dex}>
            <Header showSearch={true} className={styles.headerRow} />

            <div className={styles.mainRow}>
                <div className={styles.leftColumn}>
                    <Document_downloader_ui
                        selectedDocument={selectedDocument}
                        onSelectDocument={selectDocument}
                        onDocumentsChange={() => {}}
                        error={null}
                        setError={() => {}}
                    />
                </div>

                <div className={styles.rightPanel}>
                    <div className={styles.tabBar}>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'markdown' ? styles.active : ''}`}
                            onClick={() => setActiveTab('markdown')}
                        >
                            Предпросмотр Markdown
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'annotator' ? styles.active : ''}`}
                            onClick={() => setActiveTab('annotator')}
                        >
                            Аннотатор
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'pdf' ? styles.active : ''}`}
                            onClick={() => setActiveTab('pdf')}
                        >
                            Исходный PDF
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'patterns' ? styles.active : ''}`}
                            onClick={() => setActiveTab('patterns')}
                        >
                            Паттерны
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'linguistic-graph' ? styles.active : ''}`}
                            onClick={() => setActiveTab('linguistic-graph')}
                        >
                            Лингвистический граф
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'graph' ? styles.active : ''}`}
                            onClick={() => setActiveTab('graph')}
                        >
                            Карта статьи
                        </button>

                        {isNlpProcessing && (
                            <div className={`${styles.saveIndicator} ${styles.saving}`} style={{ marginLeft: 'auto' }}>
                                <div className={styles.loadingSpinner} style={{ width: '12px', height: '12px' }}></div>
                                <span>NLP анализ...</span>
                            </div>
                        )}
                        {!isNlpProcessing && saveStatus !== 'idle' && (
                            <div className={`${styles.saveIndicator} ${styles[saveStatus]}`} style={{ marginLeft: 'auto' }}>
                                {saveStatus === 'saving' && <><div className={styles.loadingSpinner} style={{ width: '12px', height: '12px' }}></div><span>Сохранение...</span></>}
                                {saveStatus === 'saved' && <><span>✓</span><span>Сохранено {lastSavedAt ? new Date(lastSavedAt).toLocaleTimeString() : ''}</span></>}
                                {saveStatus === 'error' && <><span>✗</span><span>Ошибка сохранения</span></>}
                            </div>
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
                                        <p className="text-gray-500 font-medium">PDF недоступен для этого документа</p>
                                    </div>
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
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
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
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
                                        onSave={handleManualSave}
                                        documentTitle={selectedDocument.title || selectedDocument.original_filename}
                                        onUpdateDocumentStatus={updateDocumentStatus}
                                        onNlpProcessingChange={setIsNlpProcessing}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'patterns' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
                                {selectedDocument ? (
                                    <LinguisticPatternAnalysis docId={selectedDocument.uid} />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'linguistic-graph' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
                                {selectedDocument ? (
                                    <ArticleLinguisticGraph docId={selectedDocument.uid} />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
                                )}
                            </div>
                        )}

                        {activeTab === 'graph' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
                                {selectedDocument ? (
                                    <ArticleActionGraph docId={selectedDocument.uid} />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">Выберите файл</div>
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
