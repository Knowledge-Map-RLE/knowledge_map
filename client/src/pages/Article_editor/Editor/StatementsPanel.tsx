import React, { forwardRef, useCallback, useEffect } from 'react';
import type { KnowledgeStatement } from '../model';
import styles from '../Article_editor.module.css';

interface StatementsPanelProps {
    statements: KnowledgeStatement[];
    selectedIndex: number | null;
    onSelectStatement: (index: number, stmt: KnowledgeStatement) => void;
    onScroll?: (scrollTop: number, scrollHeight: number) => void;
    highlightIndex?: number | null;
    isParsing?: boolean;
    parseProgress?: { processed: number; total: number } | null;
    parseError?: string | null;
    hasText?: boolean;
}

const StatementsPanel = forwardRef<HTMLDivElement, StatementsPanelProps>(({
    statements, selectedIndex, onSelectStatement, onScroll, highlightIndex, isParsing = false, parseProgress = null, parseError = null, hasText = false,
}, ref) => {
    const handleScroll = useCallback(() => {
        const el = (ref as React.RefObject<HTMLDivElement>).current;
        if (el && onScroll) {
            onScroll(el.scrollTop, el.scrollHeight);
        }
    }, [ref, onScroll]);

    useEffect(() => {
        if (highlightIndex !== null && highlightIndex !== undefined) {
            const el = (ref as React.RefObject<HTMLDivElement>).current;
            if (el) {
                const item = el.querySelector(`[data-stmt-idx="${highlightIndex}"]`);
                if (item) {
                    item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            }
        }
    }, [highlightIndex, ref]);

    return (
        <div
            ref={ref}
            onScroll={handleScroll}
            style={{ flex: 1, overflow: 'auto', position: 'relative' }}
        >
            {isParsing && (
                <div className={styles.overlay}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="10" stroke="#d1d5db" strokeWidth="4" />
                            <path d="M12 2a10 10 0 019.95 9" stroke="#6366f1" strokeWidth="4" strokeLinecap="round" />
                        </svg>
                        {parseProgress
                            ? `Парсинг... ${parseProgress.processed}/${parseProgress.total}`
                            : 'Парсинг...'}
                    </div>
                </div>
            )}
            {parseError && !isParsing && (
                <div style={{ padding: 12, margin: 8, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, color: '#dc2626', fontSize: 12 }}>
                    {parseError}
                </div>
            )}
            {statements.length === 0 && !isParsing && (
                <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
                    {hasText ? 'Нет утверждений' : 'Введите текст для получения утверждений'}
                </div>
            )}
            {statements.map((stmt, idx) => (
                <div
                    key={stmt.id || idx}
                    data-stmt-idx={idx}
                    className={`${styles.statementItem} ${selectedIndex === idx ? styles.selected : ''} ${highlightIndex === idx ? styles.selected : ''}`}
                    onClick={() => onSelectStatement(idx, stmt)}
                    style={highlightIndex === idx ? { background: '#fef3c7', outline: '1px solid #f59e0b' } : undefined}
                >
                    <div className={styles.statementId}>
                        {stmt.id ? stmt.id.substring(0, 8) + '...' : `#${idx + 1}`}
                    </div>
                    <div className={styles.statementTriple}>
                        <span className={styles.statementSubject}>{stmt.subject_text}</span>
                        <span className={styles.statementArrow}>→</span>
                        <span className={styles.statementPredicate}>{stmt.predicate}</span>
                        <span className={styles.statementArrow}>→</span>
                        <span className={styles.statementObject}>{stmt.object_text}</span>
                    </div>
                </div>
            ))}
        </div>
    );
});

StatementsPanel.displayName = 'StatementsPanel';

export default StatementsPanel;
