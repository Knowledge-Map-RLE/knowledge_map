import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import StatementsPanel from './StatementsPanel';
import AuthorBadge from './AuthorBadge';
import WysiwygEditor from './wysiwyg/WysiwygEditor';
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
    onApplyBlocks: (next: ArticleBlockData[]) => void;
    onSave: () => void;
    saveStatus: string;
    articleUuid?: string;
    articleAuthor?: AuthorInfo | null;
    onUploadImage?: (key: string, file: File) => Promise<string>;
    onCreateNew?: () => void;
    /** Текущая статья уже является золотым эталоном. */
    isGold?: boolean;
    /** Фиксирует текущие строки как эталон; возвращает текст ошибки или null. */
    onFixGold?: () => Promise<string | null>;
}

type FixStatus = 'idle' | 'busy' | 'ok' | 'error';

const EditorWorkspace: React.FC<EditorWorkspaceProps> = ({
    text, statements, blocks,
    isParsing, parseProgress, parseError,
    onApplyBlocks,
    onSave, saveStatus, articleUuid, articleAuthor, onUploadImage, onCreateNew,
    isGold = false, onFixGold,
}) => {
    const [selectedStatementIdx, setSelectedStatementIdx] = useState<number | null>(null);
    const [selectedStatementStmt, setSelectedStatementStmt] = useState<KnowledgeStatement | null>(null);
    const [highlightIndex, setHighlightIndex] = useState<number | null>(null);
    const [showTriplets, setShowTriplets] = useState(false);
    const [copiedAll, setCopiedAll] = useState(false);
    const [copiedMarkdown, setCopiedMarkdown] = useState(false);
    const copyTimerRef = useRef<number | null>(null);
    const copyMdTimerRef = useRef<number | null>(null);
    const [fixStatus, setFixStatus] = useState<FixStatus>('idle');
    const [fixMessage, setFixMessage] = useState('');
    const fixTimerRef = useRef<number | null>(null);
    const autosaveTimerRef = useRef<number | null>(null);

    useEffect(() => () => {
        if (autosaveTimerRef.current !== null) window.clearTimeout(autosaveTimerRef.current);
    }, []);

    // «Сырые» триплеты без резолва UUID-ссылок — показываем и копируем UUID как есть.
    const rawStatements = useMemo(
        () => blocksToStatementsRaw(blocks, articleUuid, statements),
        [blocks, articleUuid, statements],
    );

    const selectedStatement = useMemo(() =>
        selectedStatementIdx !== null && selectedStatementStmt
            ? { index: selectedStatementIdx, stmt: selectedStatementStmt }
            : null,
        [selectedStatementIdx, selectedStatementStmt],
    );

    const saveLabel = saveStatus === 'saving' ? '\u0421\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u0438\u0435...'
        : saveStatus === 'saved' ? '\u0421\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u043E'
        : saveStatus === 'error' ? '\u041E\u0448\u0438\u0431\u043A\u0430'
        : '\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C';

    const handleOpenTriplets = useCallback(() => setShowTriplets(true), []);
    const handleCloseTriplets = useCallback(() => setShowTriplets(false), []);

    /** Автосохранение: любое поле структурной строки потеряло фокус.
     *  Debounce нужен, т.к. capture-фаза blur родителя срабатывает раньше
     *  внутреннего onBlur поля (list-поля коммитят значение именно там),
     *  а также объединяет быстрые переходы между полями в один запрос. */
    const handleEditorBlurCapture = useCallback(() => {
        if (!onSave) return;
        if (autosaveTimerRef.current !== null) window.clearTimeout(autosaveTimerRef.current);
        autosaveTimerRef.current = window.setTimeout(() => {
            autosaveTimerRef.current = null;
            if (blocks.length === 0) return;
            void onSave();
        }, 600);
    }, [onSave, blocks.length]);

    const handleFixGold = useCallback(async () => {
        if (!onFixGold || fixStatus === 'busy') return;
        setFixStatus('busy');
        setFixMessage('');
        const error = await onFixGold();
        setFixStatus(error ? 'error' : 'ok');
        setFixMessage(error || 'Эталон сохранён в eval/gold — закоммитьте изменения');
        if (fixTimerRef.current !== null) window.clearTimeout(fixTimerRef.current);
        fixTimerRef.current = window.setTimeout(() => setFixStatus('idle'), 6000);
    }, [onFixGold, fixStatus]);

    const fixLabel = fixStatus === 'busy' ? '\u0424\u0438\u043A\u0441\u0430\u0446\u0438\u044F...'
        : fixStatus === 'ok' ? '\u042D\u0442\u0430\u043B\u043E\u043D \u0441\u043E\u0445\u0440\u0430\u043D\u0451\u043D'
        : fixStatus === 'error' ? '\u041E\u0448\u0438\u0431\u043A\u0430 \u0444\u0438\u043A\u0441\u0430\u0446\u0438\u0438'
        : isGold ? '\u041E\u0431\u043D\u043E\u0432\u0438\u0442\u044C \u044D\u0442\u0430\u043B\u043E\u043D'
        : '\u0417\u0430\u0444\u0438\u043A\u0441\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u043A\u0430\u043A \u044D\u0442\u0430\u043B\u043E\u043D';

    const handleCopyAll = useCallback(async () => {
        if (rawStatements.length === 0) return;
        const content = rawStatements
            .map((s) => `${s.id}: ${s.subject_text} \u2192 ${s.predicate} \u2192 ${s.object_text}`)
            .join('\n');
        try {
            await navigator.clipboard.writeText(content);
            setCopiedAll(true);
            if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
            copyTimerRef.current = window.setTimeout(() => setCopiedAll(false), 1500);
        } catch { /* ignore */ }
    }, [rawStatements]);

    /** Markdown статьи — тот же, что рендерился в колонке «Markdown»:
     *  генерируется из структурных строк с резолвом UUID (useArticleState). */
    const handleCopyMarkdown = useCallback(async () => {
        if (!text.trim()) return;
        try {
            await navigator.clipboard.writeText(text);
            setCopiedMarkdown(true);
            if (copyMdTimerRef.current !== null) window.clearTimeout(copyMdTimerRef.current);
            copyMdTimerRef.current = window.setTimeout(() => setCopiedMarkdown(false), 1500);
        } catch { /* ignore */ }
    }, [text]);

    const handleClickStatement = useCallback((index: number, stmt: KnowledgeStatement) => {
        setSelectedStatementIdx(index);
        setSelectedStatementStmt(stmt);
        setHighlightIndex(index);
    }, []);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px', borderBottom: '1px solid #e5e7eb',
                background: '#f9fafb', flexShrink: 0,
            }}>
                <button
                    onClick={onCreateNew}
                    style={{
                        padding: '4px 12px', fontSize: 12, fontWeight: 500,
                        background: '#6366f1', color: 'white',
                        border: 'none', borderRadius: 4, cursor: 'pointer',
                    }}
                >
                    + Новая статья
                </button>
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
                {onFixGold && (
                    <>
                        <button
                            onClick={handleFixGold}
                            disabled={fixStatus === 'busy' || blocks.length === 0}
                            title="Сохранить текущие строки как золотой эталон (только администраторы)"
                            style={{
                                padding: '4px 12px', fontSize: 12, fontWeight: 500,
                                background: fixStatus === 'busy' ? '#d1d5db'
                                    : fixStatus === 'ok' ? '#d1fae5'
                                    : fixStatus === 'error' ? '#fee2e2'
                                    : isGold ? '#059669' : '#0ea5e9',
                                color: fixStatus === 'busy' || fixStatus === 'idle' ? 'white' : '#374151',
                                border: 'none', borderRadius: 4, cursor: 'pointer',
                            }}
                        >
                            {fixLabel}
                        </button>
                        {isGold && (
                            <span
                                title="Статья является золотым эталоном (eval/gold)"
                                style={{
                                    padding: '2px 8px', fontSize: 11, fontWeight: 600,
                                    background: '#ecfdf5', color: '#047857',
                                    border: '1px solid #a7f3d0', borderRadius: 10,
                                }}
                            >
                                эталон
                            </span>
                        )}
                        {fixMessage && (
                            <span
                                style={{ fontSize: 11, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                title={fixMessage}
                            >
                                {fixMessage}
                            </span>
                        )}
                    </>
                )}
            </div>

            <div className={styles.editorColumns}>
                <div className={styles.editorColumnWysiwyg} onBlurCapture={handleEditorBlurCapture}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="4" y1="6" x2="20" y2="6" />
                            <line x1="4" y1="12" x2="14" y2="12" />
                            <line x1="4" y1="18" x2="17" y2="18" />
                        </svg>
                        WYSIWYG
                        <AuthorBadge author={articleAuthor ?? null} label="Автор статьи" />
                        <span className={styles.editorColumnHint}>
                            {'/\u2014 \u043A\u043E\u043C\u0430\u043D\u0434\u044B, Tab \u2014 \u043F\u043E\u043B\u044F, Ctrl+Z'}
                        </span>
                        <button
                            className={styles.editorHeaderIconBtn}
                            onClick={handleCopyMarkdown}
                            disabled={!text.trim()}
                            title="Скопировать Markdown в буфер обмена"
                        >
                            {copiedMarkdown ? (
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="20 6 9 17 4 12" />
                                </svg>
                            ) : (
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <rect x="9" y="9" width="13" height="13" rx="2" />
                                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                                </svg>
                            )}
                        </button>
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
                    <WysiwygEditor
                        blocks={blocks}
                        statements={statements}
                        articleUuid={articleUuid}
                        onApply={onApplyBlocks}
                        onUploadImage={onUploadImage}
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
