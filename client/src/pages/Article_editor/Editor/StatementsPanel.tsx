import React, { useCallback, useEffect, memo, useRef } from 'react';
import type { KnowledgeStatement } from '../model';
import styles from '../Article_editor.module.css';

function uuid8Time(uuid: string): string | null {
    try {
        const hex = uuid.replace(/-/g, '');
        if (hex.length < 16) return null;
        const tsUs = BigInt('0x' + hex.slice(0, 16));
        const ms = Number(tsUs / 1000n);
        const us = Number(tsUs % 1000n);
        const d = new Date(ms);
        const pad = (n: number, z = 2) => String(n).padStart(z, '0');
        return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(ms % 1000, 3)}${pad(us, 3)}`;
    } catch {
        return null;
    }
}

const StatementItem = memo(function StatementItem({
  stmt, idx, isSelected, isHighlighted, onSelect,
}: {
  stmt: KnowledgeStatement; idx: number; isSelected: boolean; isHighlighted: boolean;
  onSelect: (index: number, stmt: KnowledgeStatement) => void;
}) {
  const handleClick = useCallback(() => onSelect(idx, stmt), [idx, stmt, onSelect]);
  return (
    <div
      data-stmt-idx={idx}
      className={`${styles.statementItem} ${isSelected ? styles.selected : ''} ${isHighlighted ? styles.selected : ''}`}
      onClick={handleClick}
      style={isHighlighted ? { background: '#fef3c7', outline: '1px solid #f59e0b' } as const : undefined}
    >
      <div className={styles.statementId}>
        {stmt.id || `#${idx + 1}`}
        {stmt.id && <span className="ml-1.5" style={{ color: '#9ca3af', fontSize: 11 }}>{uuid8Time(stmt.id)}</span>}
      </div>
      <div className={styles.statementTriple}>
        <span className={styles.statementSubject}>{stmt.subject_text}</span>
        <span className={styles.statementArrow}>&rarr;</span>
        <span className={styles.statementPredicate}>{stmt.predicate}</span>
        <span className={styles.statementArrow}>&rarr;</span>
        <span className={styles.statementObject}>{stmt.object_text}</span>
      </div>
    </div>
  );
}, (prev, next) =>
  prev.idx === next.idx &&
  prev.isSelected === next.isSelected &&
  prev.isHighlighted === next.isHighlighted &&
  prev.stmt.id === next.stmt.id &&
  prev.stmt.subject_text === next.stmt.subject_text &&
  prev.stmt.predicate === next.stmt.predicate &&
  prev.stmt.object_text === next.stmt.object_text
);

interface StatementsPanelProps {
    statements: KnowledgeStatement[];
    selectedIndex: number | null;
    onSelectStatement: (index: number, stmt: KnowledgeStatement) => void;
    highlightIndex?: number | null;
    isParsing?: boolean;
    parseProgress?: { processed: number; total: number } | null;
    parseError?: string | null;
    hasText?: boolean;
}

const StatementsPanel: React.FC<StatementsPanelProps> = ({
    statements, selectedIndex, onSelectStatement, highlightIndex, isParsing = false, parseProgress = null, parseError = null, hasText = false,
}) => {
    const panelRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (highlightIndex !== null && highlightIndex !== undefined) {
            const el = panelRef.current;
            if (el) {
                const item = el.querySelector(`[data-stmt-idx="${highlightIndex}"]`);
                if (item) {
                    item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            }
        }
    }, [highlightIndex]);

    return (
        <div
            ref={panelRef}
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
                <StatementItem
                    key={stmt.id || `stmt-${idx}`}
                    stmt={stmt}
                    idx={idx}
                    isSelected={selectedIndex === idx}
                    isHighlighted={highlightIndex === idx}
                    onSelect={onSelectStatement}
                />
            ))}
        </div>
    );
};

export default StatementsPanel;
