import React, { useState, useCallback, useEffect, useRef } from 'react';
import Header from '../../widgets/Header';
import Document_downloader_ui, { type DocumentListHandle } from '../Data_extraction/Document_downloader_ui';
import EditorWorkspace from './Editor/EditorWorkspace';
import ArticleMap from './Editor/ArticleMap';
import EvidencePatterns from './Editor/EvidencePatterns';
import { ChatPanel } from '../Social_network/components/ChatPanel';
import type { ChatTarget } from '../Social_network/model';
import { useArticleState } from './hooks/useArticleState';
import { useAuth } from '../../entities/auth';
import { useRequireAuth } from '../../shared/hooks/useRequireAuth';
import type { ArticleEditorTab } from './model';
import styles from './Article_editor.module.css';

const ArticleEditorUI: React.FC = () => {
    const [activeTab, setActiveTab] = useState<ArticleEditorTab>('editor');
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
    const [selectedDocument, setSelectedDocument] = useState<any>(null);
    const [chatTarget, setChatTarget] = useState<ChatTarget | null>(null);
    const noopRef = useRef<() => void>(() => {});
    const noopSetError = useRef<(e: string | null) => void>(() => {});
    const docListRef = useRef<DocumentListHandle>(null);
    const requireAuth = useRequireAuth();
    const { isAuthenticated, user } = useAuth();

    const openArticleChat = useCallback(() => {
        if (!selectedDocId) return;
        setChatTarget({
            type: 'article',
            uid: selectedDocId,
            label: (selectedDocument as any)?.title || selectedDocId,
        });
        setActiveTab('chat');
    }, [selectedDocId, selectedDocument]);

    useEffect(() => {
        if (selectedDocId) {
            setChatTarget({
                type: 'article',
                uid: selectedDocId,
                label: (selectedDocument as any)?.title || selectedDocId,
            });
        }
    }, [selectedDocId, selectedDocument]);

    const {
        text, statements, blocks, articleUuid, isParsing, parseProgress, parseError, saveStatus, notAnnotatedMessage,
        loadArticle, initNewArticle, applyExtractedBlocks, setText, addBlock, updateBlock, deleteBlock, reorderBlocks, triggerParse, save, uploadImage,
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

    useEffect(() => {
        if (isAuthenticated && selectedDocId && text.length > 0 && !notAnnotatedMessage && blocks.length === 0) {
            triggerParse(selectedDocId);
        }
    }, [text, selectedDocId, triggerParse, notAnnotatedMessage, blocks.length, isAuthenticated]);

    const handleSave = useCallback(async () => {
        if (selectedDocId && !notAnnotatedMessage) {
            await save(selectedDocId);
        }
    }, [selectedDocId, save, notAnnotatedMessage]);

    const handleExtracted = useCallback(async (docId: string, extractedBlocks: any[]) => {
        await applyExtractedBlocks(docId, extractedBlocks);
    }, [applyExtractedBlocks]);

    const handleCreateNew = useCallback(async () => {
        if (!requireAuth()) return;
        const { createArticle } = await import('../../services/api/article_editor');
        const result = await createArticle('Новая статья');
        if (result?.uid) {
            initNewArticle(result.uid);
            setSelectedDocId(result.uid);
            setSelectedDocument({
                uid: result.uid,
                title: result.title,
                original_filename: result.original_filename,
                processing_status: 'ready_for_annotation',
                is_processed: false,
            });
            addBlock(1, { title: result.title || 'Новая статья' });
            await docListRef.current?.reloadDocuments();
            await new Promise(resolve => setTimeout(resolve, 0));
            await save(result.uid);
        }
    }, [initNewArticle, addBlock, save, requireAuth]);

    return (
        <main className={styles.ae}>
            <Header showSearch={true} className={styles.headerRow} />

            <div className={styles.mainRow}>
                <div className={styles.leftColumn}>
                    <Document_downloader_ui
                        ref={docListRef}
                        selectedDocument={selectedDocument}
                        onSelectDocument={handleSelectDocument}
                        onDocumentsChange={noopRef.current}
                        error={null}
                        setError={noopSetError.current}
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
                        <button
                            className={`${styles.tabButton} ${activeTab === 'chat' ? styles.active : ''}`}
                            onClick={openArticleChat}
                            disabled={!selectedDocId}
                            title={selectedDocId ? 'Обсуждение статьи' : 'Сначала откройте или создайте статью'}
                        >
                            Обсуждение
                        </button>
                    </div>

                    <div className={styles.tabContent}>
                        {activeTab === 'editor' && (
                            notAnnotatedMessage ? (
                                <div style={{
                                    flex: 1, display: 'flex', flexDirection: 'column',
                                    alignItems: 'center', justifyContent: 'center',
                                    padding: 40, textAlign: 'center',
                                }}>
                                    <div style={{
                                        background: '#fff3cd', border: '1px solid #ffc107',
                                        borderRadius: 8, padding: '24px 32px', maxWidth: 480,
                                    }}>
                                        <p style={{ fontSize: 16, fontWeight: 600, color: '#856404', margin: '0 0 8px' }}>
                                            ⚠ Документ не аннотирован
                                        </p>
                                        <p style={{ fontSize: 14, color: '#856404', margin: 0, lineHeight: 1.5 }}>
                                            {notAnnotatedMessage}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <EditorWorkspace
                                    text={text}
                                    statements={statements}
                                    blocks={blocks}
                                    isParsing={isParsing}
                                    parseProgress={parseProgress}
                                    parseError={parseError}
                                    onAddBlock={addBlock}
                                    onDeleteBlock={deleteBlock}
                                    onUpdateBlock={updateBlock}
                                    onReorderBlocks={reorderBlocks}
                                    onSave={handleSave}
                                    saveStatus={saveStatus}
                                    docId={selectedDocId ?? undefined}
                                    articleUuid={articleUuid ?? undefined}
                                    onUploadImage={uploadImage}
                                    onExtracted={handleExtracted}
                                />
                            )
                        )}
                        {activeTab === 'graph' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                {selectedDocId ? (
                                    <ArticleMap blocks={blocks} />
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
                                    <EvidencePatterns docId={selectedDocId} />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        Выберите файл или создайте новую статью
                                    </div>
                                )}
                            </div>
                        )}
                        {activeTab === 'chat' && (
                            <div className={styles.chatContainer}>
                                {selectedDocId && isAuthenticated && user ? (
                                    <ChatPanel
                                        target={chatTarget}
                                        onOpenTarget={(t) => setChatTarget(t)}
                                        myUid={user.uid}
                                        hideRail
                                        title={(selectedDocument as any)?.title || 'Обсуждение статьи'}
                                    />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        {!selectedDocId ? 'Выберите файл или создайте новую статью' : 'Войдите в аккаунт, чтобы участвовать в обсуждении'}
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
