import React, { useState, useCallback, useRef, useMemo } from 'react';
import StructuredBlockEditor from './StructuredBlockEditor';
import StatementsPanel from './StatementsPanel';
import MarkdownPreview from './MarkdownPreview';
import type { KnowledgeStatement, ArticleBlockData } from '../model';
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
    onUploadImage?: (key: string, file: File) => Promise<string>;
}

const EditorWorkspace: React.FC<EditorWorkspaceProps> = ({
    text, statements, blocks,
    isParsing, parseProgress, parseError,
    onAddBlock, onDeleteBlock, onUpdateBlock, onReorderBlocks,
    onSave, saveStatus, docId, articleUuid, onUploadImage,
}) => {
    const [selectedStatementIdx, setSelectedStatementIdx] = useState<number | null>(null);
    const [selectedStatementStmt, setSelectedStatementStmt] = useState<KnowledgeStatement | null>(null);
    const [highlightStart, setHighlightStart] = useState<number | null>(null);
    const [highlightEnd, setHighlightEnd] = useState<number | null>(null);
    const [highlightIndex, setHighlightIndex] = useState<number | null>(null);

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
                            <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
                            <rect x="9" y="3" width="6" height="4" rx="1" />
                            <path d="M9 14l2 2 4-4" />
                        </svg>
                        {'\u0422\u0440\u0438\u043F\u043B\u0435\u0442\u044B'}
                        <span style={{ marginLeft: 8, fontSize: 11, color: '#9ca3af', fontWeight: 400 }}>
                            {statements.length > 0
                                ? statements.length
                                : ''}
                            {isParsing && parseProgress
                                ? ` ${parseProgress.processed}/${parseProgress.total}`
                                : isParsing
                                    ? ' ...'
                                    : ''}
                        </span>
                    </div>
                    <StatementsPanel
                        statements={statements}
                        selectedIndex={selectedStatement?.index ?? null}
                        onSelectStatement={handleSelectStatement}
                        highlightIndex={highlightIndex}
                        isParsing={isParsing}
                        parseProgress={parseProgress}
                        parseError={parseError}
                        hasText={text.length > 0}
                    />
                </div>
            </div>
        </div>
    );
};

export default EditorWorkspace;
