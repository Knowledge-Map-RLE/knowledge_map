import React, { useState, useCallback, useRef, useMemo } from 'react';
import StructuredBlockEditor from './StructuredBlockEditor';
import StatementsPanel from './StatementsPanel';
import MarkdownPreview from './MarkdownPreview';
import AgentChat from './AgentChat';
import AuthorBadge from './AuthorBadge';
import { blocksToStatementsRaw } from './blockConverter';
import type { KnowledgeStatement, ArticleBlockData, AuthorInfo } from '../model';
import styles from '../Article_editor.module.css';

interface EditorWorkspaceProps {
    text: string;
    statements: KnowledgeStatement[];
    blocks: ArticleBlockData[];
    isParsing: boolean;
    parseProgress: { processed: number; total: number } | null;
    parseError: string | null;
    onAddBlock: (typeNumber: number) => void;
    onDeleteBlock: (instanceId: string) => void;
    onUpdateBlock: (instanceId: string, fieldKey: string, value: string | boolean) => void;
    onReorderBlocks: (fromIndex: number, toIndex: number) => void;
    onSave: () => void;
    saveStatus: string;
    docId?: string;
    articleUuid?: string;
    articleAuthor?: AuthorInfo | null;
    onUploadImage?: (key: string, file: File) => Promise<string>;
    onExtracted?: (docId: string, blocks: ArticleBlockData[]) => Promise<void>;
}

const EditorWorkspace: React.FC<EditorWorkspaceProps> = ({
    text, statements, blocks,
    isParsing, parseProgress, parseError,
    onAddBlock, onDeleteBlock, onUpdateBlock, onReorderBlocks,
    onSave, saveStatus, docId, articleUuid, articleAuthor, onUploadImage, onExtracted,
}) => {
    const [selectedStatementIdx, setSelectedStatementIdx] = useState<number | null>(null);
    const [selectedStatementStmt, setSelectedStatementStmt] = useState<KnowledgeStatement | null>(null);
    const [highlightStart, setHighlightStart] = useState<number | null>(null);
    const [highlightEnd, setHighlightEnd] = useState<number | null>(null);
    const [highlightIndex, setHighlightIndex] = useState<number | null>(null);
    const [showTriplets, setShowTriplets] = useState(false);
    const [copiedAll, setCopiedAll] = useState(false);
    const copyTimerRef = useRef<number | null>(null);

    // «Сырые» триплеты без резолва UUID-ссылок — показываем и копируем UUID как есть.
    const rawStatements = useMemo(
        () => blocksToStatementsRaw(blocks, articleUuid, statements),
        [blocks, articleUuid, statements],
    );

    const textRef = useRef(text);
    textRef.current = text;

    const selectedStatement = useMemo(() =>
        selectedStatementIdx !== null && selectedStatementStmt
            ? { index: selectedStatementIdx, stmt: selectedStatementStmt }
            : null,
        [selectedStatementIdx, selectedStatementStmt],
    );

    const highlightRange = useMemo(() =>
        highlightStart !== null && highlightEnd !== null
            ? { start: highlightStart, end: highlightEnd }
            : null,
        [highlightStart, highlightEnd],
    );

    const handleSelectStatement = useCallback((index: number, stmt: KnowledgeStatement) => {
        setSelectedStatementIdx(index);
        setSelectedStatementStmt(stmt);
        setHighlightIndex(index);
        const sentenceText = stmt.sentence_text || stmt.subject_text + ' \u2192 ' + stmt.predicate + ' \u2192 ' + stmt.object_text;
        const currentText = textRef.current;
        const idx = currentText.indexOf(sentenceText);
        if (idx >= 0) {
            setHighlightStart(idx);
            setHighlightEnd(idx + sentenceText.length);
        } else {
            setHighlightStart(null);
            setHighlightEnd(null);
        }
    }, []);

    const saveLabel = saveStatus === 'saving' ? '\u0421\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u0438\u0435...'
        : saveStatus === 'saved' ? '\u0421\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u043E'
        : saveStatus === 'error' ? '\u041E\u0448\u0438\u0431\u043A\u0430'
        : '\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C';

    const handleOpenTriplets = useCallback(() => setShowTriplets(true), []);
    const handleCloseTriplets = useCallback(() => setShowTriplets(false), []);

    const handleCopyAll = useCallback(async () => {
        if (rawStatements.length === 0) return;
        const text = rawStatements
            .map((s) => `${s.id}: ${s.subject_text} \u2192 ${s.predicate} \u2192 ${s.object_text}`)
            .join('\n');
        try {
            await navigator.clipboard.writeText(text);
            setCopiedAll(true);
            if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
            copyTimerRef.current = window.setTimeout(() => setCopiedAll(false), 1500);
        } catch { /* ignore */ }
    }, [rawStatements]);

    const handleClickStatement = useCallback((index: number, stmt: KnowledgeStatement) => {
        // Отображаем «сырой» триплет, но для подсветки в Markdown используем
        // резолвнутый вариант (тот же порядок/индекс).
        handleSelectStatement(index, statements[index] ?? stmt);
    }, [handleSelectStatement, statements]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px', borderBottom: '1px solid #e5e7eb',
                background: '#f9fafb', flexShrink: 0,
            }}>
                <div style={{ flex: 1 }} />
                <button
                    onClick={onSave}
                    style={{
                        padding: '4px 12px', fontSize: 12, fontWeight: 500,
                        background: saveStatus === 'saving' ? '#d1d5db'
                            : saveStatus === 'saved' ? '#d1fae5'
                            : saveStatus === 'error' ? '#fee2e2'
                            : '#6366f1',
                        color: saveStatus === 'saving' || saveStatus === 'idle' ? 'white' : '#374151',
                        border: 'none', borderRadius: 4, cursor: 'pointer',
                    }}
                >
                    {saveLabel}
                </button>
            </div>

            <div className={styles.editorColumns}>
                <div className={styles.editorColumn}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                        {'\u0421\u0442\u0440\u0443\u043A\u0442\u0443\u0440\u043D\u044B\u0435 \u0431\u043B\u043E\u043A\u0438'}
                        <AuthorBadge author={articleAuthor ?? null} label="Автор статьи" />
                        <div style={{ flex: 1 }} />
                        <button
                            className={styles.sbeTripletsBtn}
                            onClick={handleOpenTriplets}
                            title="Показать триплеты"
                        >
                            {'\u0422\u0440\u0438\u043F\u043B\u0435\u0442\u044B'}
                            {statements.length > 0 && (
                                <span className={styles.sbeTripletsCount}>{statements.length}</span>
                            )}
                        </button>
                    </div>
                    <StructuredBlockEditor
                        blocks={blocks}
                        onAddBlock={onAddBlock}
                        onDeleteBlock={onDeleteBlock}
                        onUpdateBlock={onUpdateBlock}
                        onReorderBlocks={onReorderBlocks}
                        articleUuid={articleUuid}
                        statements={statements}
                        onBlurSave={onSave}
                        onUploadImage={onUploadImage}
                    />
                </div>

                <div className={styles.editorColumnMd}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                            <line x1="16" y1="13" x2="8" y2="13" />
                            <line x1="16" y1="17" x2="8" y2="17" />
                            <polyline points="10 9 9 9 8 9" />
                        </svg>
                        Markdown
                    </div>
                    <MarkdownPreview
                        text={text}
                        docId={docId}
                        highlightRange={highlightRange}
                    />
                </div>

                <div className={styles.editorColumnSm}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 2a10 10 0 100 20 10 10 0 000-20z" />
                            <circle cx="12" cy="12" r="3" />
                        </svg>
                        {'AI \u0410\u0433\u0435\u043D\u0442'}
                    </div>
                    <AgentChat
                        articleUuid={articleUuid}
                        blocks={blocks}
                        statements={statements}
                        text={text}
                        onExtracted={onExtracted}
                    />
                </div>
            </div>

            {showTriplets && (
                <div className={styles.tripletModalOverlay} onClick={handleCloseTriplets}>
                    <div
                        className={styles.tripletModal}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className={styles.tripletModalHeader}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
                                <rect x="9" y="3" width="6" height="4" rx="1" />
                                <path d="M9 14l2 2 4-4" />
                            </svg>
                            {'\u0422\u0440\u0438\u043F\u043B\u0435\u0442\u044B'}
                            <span className={styles.tripletModalCount}>
                                {statements.length > 0
                                    ? statements.length
                                    : ''}
                                {isParsing && parseProgress
                                    ? ` ${parseProgress.processed}/${parseProgress.total}`
                                    : isParsing
                                        ? ' ...'
                                        : ''}
                            </span>
                            <div style={{ flex: 1 }} />
                            <button
                                className={styles.tripletCopyBtn}
                                onClick={handleCopyAll}
                                disabled={rawStatements.length === 0}
                                title="Копировать все триплеты в буфер обмена"
                            >
                                {copiedAll ? '\u2713 \u0421\u043A\u043E\u043F\u0438\u0440\u043E\u0432\u0430\u043D\u043E' : '\u2398 \u0421\u043A\u043E\u043F\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u0432\u0441\u0435'}
                            </button>
                            <button
                                className={styles.tripletCloseBtn}
                                onClick={handleCloseTriplets}
                                title="Закрыть"
                            >
                                &times;
                            </button>
                        </div>
                        <div className={styles.tripletModalBody}>
                            <StatementsPanel
                                statements={rawStatements}
                                selectedIndex={selectedStatement?.index ?? null}
                                onSelectStatement={handleClickStatement}
                                highlightIndex={highlightIndex}
                                isParsing={isParsing}
                                parseProgress={parseProgress}
                                parseError={parseError}
                                hasText={text.length > 0}
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default EditorWorkspace;
