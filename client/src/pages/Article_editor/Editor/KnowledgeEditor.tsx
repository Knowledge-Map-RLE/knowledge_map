import React, { forwardRef, useEffect, useCallback } from 'react';

interface KnowledgeEditorProps {
    text: string;
    onChange: (text: string) => void;
    onScroll?: (scrollTop: number, scrollHeight: number) => void;
    onCursorMove?: (offset: number) => void;
    highlightRange?: { start: number; end: number } | null;
    readOnly?: boolean;
}

const KnowledgeEditor = forwardRef<HTMLTextAreaElement, KnowledgeEditorProps>(({
    text, onChange, onScroll, onCursorMove, highlightRange, readOnly = false,
}, ref) => {
    const handleScroll = useCallback(() => {
        const el = (ref as React.RefObject<HTMLTextAreaElement>).current;
        if (el && onScroll) {
            onScroll(el.scrollTop, el.scrollHeight);
        }
    }, [ref, onScroll]);

    const handleMouseUp = useCallback(() => {
        const el = (ref as React.RefObject<HTMLTextAreaElement>).current;
        if (el && onCursorMove) {
            onCursorMove(el.selectionStart);
        }
    }, [ref, onCursorMove]);

    useEffect(() => {
        if (highlightRange) {
            const el = (ref as React.RefObject<HTMLTextAreaElement>).current;
            if (el) {
                el.focus();
                el.setSelectionRange(highlightRange.start, highlightRange.end);
            }
        }
    }, [highlightRange, ref]);

    return (
        <textarea
            ref={ref}
            value={text}
            onChange={e => onChange(e.target.value)}
            onScroll={handleScroll}
            onMouseUp={handleMouseUp}
            onKeyUp={handleMouseUp}
            readOnly={readOnly}
            style={{
                flex: 1,
                border: 'none',
                outline: 'none',
                resize: 'none',
                padding: '12px',
                fontFamily: "'Fira Code', 'Consolas', monospace",
                fontSize: '13px',
                lineHeight: '1.6',
                background: '#fafafa',
                color: '#1f2937',
                tabSize: 2,
                width: '100%',
                height: '100%',
                display: 'block',
            }}
            spellCheck={false}
        />
    );
});

KnowledgeEditor.displayName = 'KnowledgeEditor';

export default KnowledgeEditor;
