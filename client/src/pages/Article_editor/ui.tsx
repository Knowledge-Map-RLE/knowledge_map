import React, { useState, useCallback, useEffect } from 'react';
import Header from '../../widgets/Header';
import Document_downloader_ui from '../Data_extraction/Document_downloader_ui';
import EditorWorkspace from './Editor/EditorWorkspace';
import ArticleMap from './Editor/ArticleMap';
import { LinguisticPatternAnalysis } from '../Data_extraction/Patterns';
import { useArticleState } from './hooks/useArticleState';
import type { ArticleEditorTab } from './model';
import styles from './Article_editor.module.css';

const ArticleEditorUI: React.FC = () => {
    const [activeTab, setActiveTab] = useState<ArticleEditorTab>('editor');
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
    const [selectedDocument, setSelectedDocument] = useState<any>(null);

    const {
        text, statements, isParsing, parseProgress, parseError, saveStatus,
        loadArticle, setText, triggerParse, save,
    } = useArticleState();

    const handleSelectDocument = useCallback(async (doc: any | null) => {
        setSelectedDocument(doc);
        if (doc && doc.uid) {
            setSelectedDocId(doc.uid);
            await loadArticle(doc.uid);
        } else {
            setSelectedDocId(null);
            setText('');
        }
    }, [loadArticle, setText]);

    const handleTextChange = useCallback((newText: string) => {
        setText(newText);
    }, [setText]);

    useEffect(() => {
        if (selectedDocId && text.length > 0) {
            triggerParse(selectedDocId);
        }
    }, [text, selectedDocId, triggerParse]);

    const handleSave = useCallback(async () => {
        if (selectedDocId) {
            await save(selectedDocId);
        }
    }, [selectedDocId, save]);

    const handleCreateNew = useCallback(async () => {
        const { createArticle } = await import('../../services/api/article_editor');
        const result = await createArticle('New Article');
        if (result?.uid) {
            setSelectedDocId(result.uid);
            setSelectedDocument({
                uid: result.uid,
                title: result.title,
                original_filename: result.original_filename,
                processing_status: 'ready_for_annotation',
                is_processed: false,
            });
            setText('');
        }
    }, [setText]);

    return (
        <main className={styles.ae}>
            <Header showSearch={true} className={styles.headerRow} />

            <div className={styles.mainRow}>
                <div className={styles.leftColumn}>
                    <Document_downloader_ui
                        selectedDocument={selectedDocument}
                        onSelectDocument={handleSelectDocument}
                        onDocumentsChange={() => {}}
                        error={null}
                        setError={() => {}}
                    />
                    <div style={{ padding: '8px 0', borderTop: '1px solid #e5e7eb', marginTop: 8 }}>
                        <button
                            onClick={handleCreateNew}
                            style={{
                                width: '100%', padding: '8px 12px', fontSize: 13, fontWeight: 500,
                                background: '#6366f1', color: 'white', border: 'none', borderRadius: 6,
                                cursor: 'pointer',
                            }}
                        >
                            + Новая статья
                        </button>
                    </div>
                </div>

                <div className={styles.rightPanel}>
                    <div className={styles.tabBar}>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'editor' ? styles.active : ''}`}
                            onClick={() => setActiveTab('editor')}
                        >
                            Редактор
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'graph' ? styles.active : ''}`}
                            onClick={() => setActiveTab('graph')}
                        >
                            Карта статьи
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'patterns' ? styles.active : ''}`}
                            onClick={() => setActiveTab('patterns')}
                        >
                            Паттерны
                        </button>
                    </div>

                    <div className={styles.tabContent}>
                        {activeTab === 'editor' && (
                            <EditorWorkspace
                                text={text}
                                statements={statements}
                                isParsing={isParsing}
                                parseProgress={parseProgress}
                                parseError={parseError}
                                onTextChange={handleTextChange}
                                onSave={handleSave}
                                saveStatus={saveStatus}
                                docId={selectedDocId ?? undefined}
                            />
                        )}
                        {activeTab === 'graph' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                {selectedDocId ? (
                                    <ArticleMap docId={selectedDocId} />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        Выберите файл или создайте новую статью
                                    </div>
                                )}
                            </div>
                        )}
                        {activeTab === 'patterns' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                {selectedDocId ? (
                                    <LinguisticPatternAnalysis docId={selectedDocId} />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        Выберите файл или создайте новую статью
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

export default ArticleEditorUI;
