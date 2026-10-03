import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { getGoldArticleLocalization, type GoldArticleLocalization, type GoldArticleTextLocalization } from '../../services/api/article_editor';
import Header from '../../widgets/Header';
import MarkdownEditor from '../../widgets/MarkdownEditor';
import Document_downloader_ui, { type DocumentListHandle } from '../Data_extraction/Document_downloader_ui';
import EditorWorkspace from './Editor/EditorWorkspace';
import AgentChat from './Editor/AgentChat';
import PipelineVersions from './Editor/PipelineVersions';
import ArticleMap from './Editor/ArticleMap';
import EvidencePatterns from './Editor/EvidencePatterns';
import { ChatPanel } from '../Social_network/components/ChatPanel';
import type { ChatTarget } from '../Social_network/model';
import type { PDFDocument } from '../Data_extraction/model';
import type { ArticleBlockData } from './model';
import { useArticleState } from './hooks/useArticleState';
import { useAuth } from '../../entities/auth';
import { useRequireAuth } from '../../shared/hooks/useRequireAuth';
import { listGoldCases, createGoldCase, updateGoldCase } from '../../services/api/gold';
import type { ArticleEditorTab } from './model';
import styles from './Article_editor.module.css';

const ArticleEditorUI: React.FC = () => {
    const { t, i18n } = useTranslation();
    const locale = i18n.resolvedLanguage === 'ru' ? 'ru' : 'en';
    const [activeTab, setActiveTab] = useState<ArticleEditorTab>('editor');
    const [pipelineRefresh, setPipelineRefresh] = useState(0);
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
    const [selectedDocument, setSelectedDocument] = useState<PDFDocument | null>(null);
    const [chatTarget, setChatTarget] = useState<ChatTarget | null>(null);
    const noopRef = useRef<() => void>(() => {});
    const noopSetError = useRef<(e: string | null) => void>(() => {});
    const docListRef = useRef<DocumentListHandle>(null);
    const requireAuth = useRequireAuth();
    const { isAuthenticated, user } = useAuth();
    const [goldByDocId, setGoldByDocId] = useState<Record<string, string>>({});
    const [goldLocalization, setGoldLocalization] = useState<GoldArticleTextLocalization | null>(null);
    const [goldLocalizationError, setGoldLocalizationError] = useState<string | null>(null);
    const [goldLocalizationLoading, setGoldLocalizationLoading] = useState(false);
    const [goldStructureLocalization, setGoldStructureLocalization] = useState<GoldArticleLocalization | null>(null);
    const [goldStructureLocalizationError, setGoldStructureLocalizationError] = useState<string | null>(null);
    const [goldStructureLocalizationLoading, setGoldStructureLocalizationLoading] = useState(false);
    const refreshPipeline = useCallback(() => {
        setPipelineRefresh(value => value + 1);
    }, []);

    const reloadGoldIndex = useCallback(async () => {
        try {
            const res = await listGoldCases();
            setGoldByDocId(res.by_doc_id || {});
        } catch {
            setGoldByDocId({});
        }
    }, []);

    useEffect(() => {
        if (!isAuthenticated) return;
        void reloadGoldIndex();
    }, [isAuthenticated, reloadGoldIndex]);

    const openArticleChat = useCallback(() => {
        if (!selectedDocId) return;
        setChatTarget({
            type: 'article',
            uid: selectedDocId,
            label: selectedDocument?.title || selectedDocId,
        });
        setActiveTab('chat');
    }, [selectedDocId, selectedDocument]);

    useEffect(() => {
        if (selectedDocId) {
            setChatTarget({
                type: 'article',
                uid: selectedDocId,
label: selectedDocument?.title || selectedDocId,
            });
        }
    }, [selectedDocId, selectedDocument]);

    const {
        article, text, sourceMarkdown, statements, blocks, articleUuid, isParsing, parseProgress, parseError, saveStatus, notAnnotatedMessage,
        loadArticle, initNewArticle, applyExtractedBlocks, setText, addBlock, applyBlocks, triggerParse, save, uploadImage,
    } = useArticleState();

    useEffect(() => {
        if (!selectedDocId || selectedDocument?.is_gold_standard !== true || locale === 'en') {
            setGoldLocalization(null);
            setGoldLocalizationError(null);
            setGoldLocalizationLoading(false);
            setGoldStructureLocalization(null);
            setGoldStructureLocalizationError(null);
            setGoldStructureLocalizationLoading(false);
            return;
        }
        let active = true;
        setGoldLocalization(null);
        setGoldLocalizationError(null);
        setGoldLocalizationLoading(true);
        setGoldStructureLocalization(null);
        setGoldStructureLocalizationError(null);
        setGoldStructureLocalizationLoading(true);
        void getGoldArticleLocalization(selectedDocId, locale, 'article')
            .then(result => {
                if (active) setGoldLocalization(result);
            })
            .catch(error => {
                if (active) {
                    setGoldLocalizationError(error instanceof Error ? error.message : String(error));
                }
            })
            .finally(() => {
                if (active) setGoldLocalizationLoading(false);
            });
        void getGoldArticleLocalization(selectedDocId, locale, 'structure')
            .then(result => {
                if (active) setGoldStructureLocalization(result);
            })
            .catch(error => {
                if (active) {
                    setGoldStructureLocalizationError(error instanceof Error ? error.message : String(error));
                }
            })
            .finally(() => {
                if (active) setGoldStructureLocalizationLoading(false);
            });
        return () => { active = false; };
    }, [selectedDocId, selectedDocument?.is_gold_standard, locale]);

    const localizedGoldArticle = goldLocalization?.document_uid === selectedDocId && goldLocalization.locale === locale
        ? goldLocalization : null;
    const localizedGoldStructure = goldStructureLocalization?.document_uid === selectedDocId && goldStructureLocalization.locale === locale
        ? goldStructureLocalization : null;
    const goldTranslationRequired = selectedDocument?.is_gold_standard === true && locale === 'ru';
    const displayBlocks = goldTranslationRequired ? (localizedGoldStructure?.blocks ?? []) : blocks;
    const displayText = goldTranslationRequired ? (localizedGoldStructure?.article_markdown ?? '') : text;
    const displayMarkdown = goldTranslationRequired ? (localizedGoldArticle?.article_markdown ?? '') : sourceMarkdown;
    const goldTranslationUnavailable = goldTranslationRequired && !localizedGoldArticle && !goldLocalizationLoading;
    const goldStructureTranslationUnavailable = goldTranslationRequired && !localizedGoldStructure && !goldStructureLocalizationLoading;
    const renderGoldLocalizationStatus = (unavailable: boolean, error: string | null) => (
        <div>
            <div>
                {unavailable
                    ? t('articleEditor.localization.unavailable')
                    : t('articleEditor.localization.loading')}
            </div>
            {unavailable && error && (
                <div style={{ marginTop: 8, fontSize: 13, overflowWrap: 'anywhere' }}>
                    {error}
                </div>
            )}
        </div>
    );

    const handleSelectDocument = useCallback(async (doc: PDFDocument | null) => {
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
            await docListRef.current?.reloadDocuments();
        }
    }, [selectedDocId, save, notAnnotatedMessage]);

    /** Фиксирует текущие строки статьи как золотой эталон.
     *  Возвращает текст ошибки или null при успехе. */
    const handleFixGold = useCallback(async (): Promise<string | null> => {
        if (!selectedDocId) return t('articleEditor.errors.openArticleFirst');
        if (blocks.length === 0) return t('articleEditor.errors.noRowsToSave');
        try {
            await save(selectedDocId);
            await docListRef.current?.reloadDocuments();
            const slug = goldByDocId[selectedDocId];
            if (slug) {
                await updateGoldCase(slug, blocks);
            } else {
                const res = await createGoldCase(selectedDocId, blocks);
                setGoldByDocId((prev) => ({ ...prev, [selectedDocId]: res.slug }));
            }
            void reloadGoldIndex();
            return null;
        } catch (err) {
            return err instanceof Error ? err.message : String(err);
        }
    }, [selectedDocId, blocks, save, goldByDocId, reloadGoldIndex, t]);

    const handleExtracted = useCallback(async (docId: string, extractedBlocks: ArticleBlockData[]) => {
        await applyExtractedBlocks(docId, extractedBlocks);
    }, [applyExtractedBlocks]);

    const handleCreateNew = useCallback(async () => {
        if (!requireAuth()) return;
        const { createArticle } = await import('../../services/api/article_editor');
        const newArticleTitle = t('articleEditor.workspace.defaultTitle');
        const result = await createArticle(newArticleTitle);
        if (result?.uid) {
            initNewArticle(result.uid);
            setSelectedDocId(result.uid);
            setSelectedDocument({
                uid: result.uid,
                title: result.title,
                original_filename: result.original_filename,
                md5_hash: '',
                upload_date: new Date().toISOString(),
                processing_status: 'ready_for_annotation',
                is_processed: false,
            });
            addBlock('metadata', { title: result.title || newArticleTitle });
            await docListRef.current?.reloadDocuments();
            await new Promise(resolve => setTimeout(resolve, 0));
            await save(result.uid);
            await docListRef.current?.reloadDocuments();
        }
    }, [initNewArticle, addBlock, save, requireAuth, t]);

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
                        goldSlugsByUid={goldByDocId}
                    />
                </div>

                <div className={styles.rightPanel}>
                    <div className={styles.tabBar}>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'editor' ? styles.active : ''}`}
                            onClick={() => setActiveTab('editor')}
                        >
                            {t('articleEditor.tabs.editor')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'text' ? styles.active : ''}`}
                            onClick={() => setActiveTab('text')}
                        >
                            {t('articleEditor.tabs.text')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'graph' ? styles.active : ''}`}
                            onClick={() => setActiveTab('graph')}
                        >
                            {t('articleEditor.tabs.map')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'patterns' ? styles.active : ''}`}
                            onClick={() => setActiveTab('patterns')}
                        >
                            {t('articleEditor.tabs.patterns')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'pipeline' ? styles.active : ''}`}
                            onClick={() => setActiveTab('pipeline')}
                            disabled={!selectedDocId}
                            title={selectedDocId ? t('articleEditor.tabs.pipelineTitle') : t('articleEditor.errors.openArticleFirst')}
                        >
                            {t('articleEditor.tabs.pipeline')}
                        </button>
                        <button
                            className={`${styles.tabButton} ${activeTab === 'chat' ? styles.active : ''}`}
                            onClick={openArticleChat}
                            disabled={!selectedDocId}
                            title={selectedDocId ? t('articleEditor.tabs.discussionTitle') : t('articleEditor.errors.openOrCreateArticle')}
                        >
                            {t('articleEditor.tabs.discussion')}
                        </button>
                    </div>

                    <div className={styles.tabContent}>
                        {activeTab === 'editor' && (
                            goldTranslationRequired && !localizedGoldStructure ? (
                                <div role={goldStructureTranslationUnavailable ? 'alert' : 'status'} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32, color: '#6b7280', textAlign: 'center' }}>
                                    {renderGoldLocalizationStatus(goldStructureTranslationUnavailable, goldStructureLocalizationError)}
                                </div>
                            ) : notAnnotatedMessage ? (
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
                                            {t('articleEditor.errors.notAnnotatedTitle')}
                                        </p>
                                        <p style={{ fontSize: 14, color: '#856404', margin: 0, lineHeight: 1.5 }}>
                                            {notAnnotatedMessage}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <EditorWorkspace
                                    text={displayText}
                                    statements={statements}
                                    blocks={displayBlocks}
                                    isParsing={isParsing}
                                    parseProgress={parseProgress}
                                    parseError={parseError}
                                    onApplyBlocks={applyBlocks}
                                    onSave={handleSave}
                                    saveStatus={saveStatus}
                                    articleUuid={articleUuid ?? undefined}
                                    articleAuthor={article?.author ?? null}
                                    onUploadImage={uploadImage}
                                    onCreateNew={handleCreateNew}
                                    isGold={!!selectedDocId && !!goldByDocId[selectedDocId]}
                                    isGoldStandard={selectedDocument?.is_gold_standard === true}
                                    onFixGold={handleFixGold}
                                />
                             )
                         )}
                         {activeTab === 'text' && (
                             <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                                 {selectedDocId ? (
                                    goldTranslationRequired && !localizedGoldArticle ? (
                                        <div role={goldTranslationUnavailable ? 'alert' : 'status'} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 32, color: '#6b7280', textAlign: 'center' }}>
                                            {renderGoldLocalizationStatus(goldTranslationUnavailable, goldLocalizationError)}
                                        </div>
                                    ) : (
                                        <MarkdownEditor
                                            value={displayMarkdown}
                                            onChange={() => {}}
                                            readOnly={true}
                                        />
                                    )
                                 ) : (
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                         {t('articleEditor.empty.selectOrCreate')}
                                     </div>
                                 )}
                             </div>
                         )}
                         {activeTab === 'graph' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                {selectedDocId ? (
                                    <ArticleMap docId={selectedDocId} enabled={isAuthenticated} />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        {t('articleEditor.empty.selectOrCreate')}
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
                                        {t('articleEditor.empty.selectOrCreate')}
                                    </div>
                                )}
                            </div>
                        )}
                        {activeTab === 'pipeline' && (
                            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                {selectedDocId && isAuthenticated ? (
                                    <PipelineVersions docId={selectedDocId} refresh={pipelineRefresh} enabled />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        {!selectedDocId ? t('articleEditor.empty.selectOrCreate') : t('articleEditor.empty.loginForPipeline')}
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
                                        title={localizedGoldArticle?.title || selectedDocument?.title || t('articleEditor.tabs.discussionTitle')}
                                    />
                                ) : (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#6b7280', fontSize: 13 }}>
                                        {!selectedDocId ? t('articleEditor.empty.selectOrCreate') : t('articleEditor.empty.loginForDiscussion')}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                <div className={styles.aiColumn}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 2a10 10 0 100 20 10 10 0 000-20z" />
                            <circle cx="12" cy="12" r="3" />
                        </svg>
                        {t('articleEditor.aiAgent.title')}
                    </div>
                    <AgentChat
                        articleUuid={articleUuid}
                        blocks={blocks}
                        statements={statements}
                        text={text}
                        onExtracted={handleExtracted}
                        onPipelineUpdate={refreshPipeline}
                    />
                </div>
            </div>
        </main>
    );
};

export default ArticleEditorUI;
