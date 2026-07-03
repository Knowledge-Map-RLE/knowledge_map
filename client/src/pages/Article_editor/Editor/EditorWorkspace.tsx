import React, { useState, useCallback, useRef, useEffect } from 'react';
import KnowledgeEditor from './KnowledgeEditor';
import StatementsPanel from './StatementsPanel';
import MarkdownPreview from './MarkdownPreview';
import type { KnowledgeStatement } from '../model';
import styles from '../Article_editor.module.css';

interface EditorWorkspaceProps {
    text: string;
    statements: KnowledgeStatement[];
    isParsing: boolean;
    parseProgress: { processed: number; total: number } | null;
    parseError: string | null;
    onTextChange: (text: string) => void;
    onSave: () => void;
    saveStatus: string;
    docId?: string;
}

type SyncSource = 'editor' | 'statements' | 'preview' | null;

const EditorWorkspace: React.FC<EditorWorkspaceProps> = ({
    text, statements, isParsing, parseProgress, parseError, onTextChange, onSave, saveStatus, docId,
}) => {
    const [selectedStatement, setSelectedStatement] = useState<{ index: number; stmt: KnowledgeStatement } | null>(null);
    const [highlightRange, setHighlightRange] = useState<{ start: number; end: number } | null>(null);
    const [highlightIndex, setHighlightIndex] = useState<number | null>(null);
    const scrollSyncSource = useRef<SyncSource>(null);

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const statementsRef = useRef<HTMLDivElement>(null);
    const previewRef = useRef<HTMLDivElement>(null);

    const isSyncing = useRef(false);

    const syncScroll = useCallback((source: SyncSource, scrollTop: number, scrollHeight: number) => {
        if (isSyncing.current) return;
        isSyncing.current = true;

        const syncTo = (el: HTMLElement | null) => {
            if (el && scrollHeight > 0 && el.scrollHeight > 0) {
                const ratio = scrollTop / scrollHeight;
                el.scrollTop = ratio * el.scrollHeight;
            }
        };

        requestAnimationFrame(() => {
            if (source !== 'editor') syncTo(textareaRef.current);
            if (source !== 'statements') syncTo(statementsRef.current);
            if (source !== 'preview') syncTo(previewRef.current);
            setTimeout(() => { isSyncing.current = false; }, 50);
        });
    }, []);

    const handleEditorScroll = useCallback((scrollTop: number, scrollHeight: number) => {
        syncScroll('editor', scrollTop, scrollHeight);
    }, [syncScroll]);

    const handleStatementsScroll = useCallback((scrollTop: number, scrollHeight: number) => {
        syncScroll('statements', scrollTop, scrollHeight);
    }, [syncScroll]);

    const handlePreviewScroll = useCallback((scrollTop: number, scrollHeight: number) => {
        syncScroll('preview', scrollTop, scrollHeight);
    }, [syncScroll]);

    const handleCursorMove = useCallback((offset: number) => {
        if (statements.length === 0) return;
        for (let i = 0; i < statements.length; i++) {
            const stmt = statements[i];
            const sentenceText = stmt.sentence_text || stmt.subject_text + ' ' + stmt.predicate + ' ' + stmt.object_text;
            const idx = text.indexOf(sentenceText);
            if (idx >= 0 && offset >= idx && offset <= idx + sentenceText.length) {
                setHighlightIndex(i);
                setHighlightRange({ start: idx, end: idx + sentenceText.length });
                return;
            }
        }
        setHighlightIndex(null);
        setHighlightRange(null);
    }, [text, statements]);

    const handleSelectStatement = useCallback((index: number, stmt: KnowledgeStatement) => {
        setSelectedStatement({ index, stmt });
        setHighlightIndex(index);
        const sentenceText = stmt.sentence_text || stmt.subject_text + ' → ' + stmt.predicate + ' → ' + stmt.object_text;
        const idx = text.indexOf(sentenceText);
        if (idx >= 0) {
            setHighlightRange({ start: idx, end: idx + sentenceText.length });
        }
    }, [text]);

    const saveLabel = saveStatus === 'saving' ? 'Сохранение...'
        : saveStatus === 'saved' ? 'Сохранено'
        : saveStatus === 'error' ? 'Ошибка'
        : 'Сохранить';

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px', borderBottom: '1px solid #e5e7eb',
                background: '#f9fafb', flexShrink: 0,
            }}>
                <span style={{ fontSize: 12, color: '#6b7280' }}>
                    {statements.length > 0 ? `${statements.length} утверждений` : 'Нет утверждений'}
                    {isParsing && parseProgress
                        ? ` (парсинг ${parseProgress.processed}/${parseProgress.total})`
                        : isParsing
                            ? ' (парсинг...)'
                            : ''}
                </span>
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
                        Редактор
                    </div>
                    <KnowledgeEditor
                        ref={textareaRef}
                        text={text}
                        onChange={onTextChange}
                        onScroll={handleEditorScroll}
                        onCursorMove={handleCursorMove}
                        highlightRange={highlightRange}
                    />
                </div>

                <div className={styles.editorColumn}>
                    <div className={styles.editorColumnHeader}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
                            <rect x="9" y="3" width="6" height="4" rx="1" />
                            <path d="M9 14l2 2 4-4" />
                        </svg>
                        Утверждения
                    </div>
                    <StatementsPanel
                        ref={statementsRef}
                        statements={statements}
                        selectedIndex={selectedStatement?.index ?? null}
                        onSelectStatement={handleSelectStatement}
                        onScroll={handleStatementsScroll}
                        highlightIndex={highlightIndex}
                        isParsing={isParsing}
                        parseProgress={parseProgress}
                        parseError={parseError}
                        hasText={text.length > 0}
                    />
                </div>

                <div className={styles.editorColumn}>
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
                        ref={previewRef}
                        text={text}
                        docId={docId}
                        onScroll={handlePreviewScroll}
                        highlightRange={highlightRange}
                    />
                </div>
            </div>
        </div>
    );
};

export default EditorWorkspace;
