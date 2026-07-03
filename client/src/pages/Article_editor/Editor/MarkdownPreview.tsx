import React, { forwardRef, useCallback, useEffect, useMemo } from 'react';
import { marked } from 'marked';

const IMG_API = 'http://localhost:8000/api/data_extraction/documents';

interface MarkdownPreviewProps {
    text: string;
    docId?: string;
    onScroll?: (scrollTop: number, scrollHeight: number) => void;
    highlightRange?: { start: number; end: number } | null;
}

const MarkdownPreview = forwardRef<HTMLDivElement, MarkdownPreviewProps>(function MarkdownPreview(
    { text, docId, onScroll, highlightRange },
    ref
) {
    const handleScroll = useCallback(() => {
        const el = (ref as React.RefObject<HTMLDivElement>).current;
        if (el && onScroll) {
            onScroll(el.scrollTop, el.scrollHeight);
        }
    }, [ref, onScroll]);

    const rendered = useMemo(() => {
        let processed = text || '';
        if (docId) {
            processed = processed.replace(
                /!\[([^\]]*)\]\(([^)]+)\)/g,
                (_m, alt, src) => {
                    const fname = src.split('/').pop();
                    return `![${alt}](${IMG_API}/${docId}/images/${fname})`;
                }
            );
        }
        const raw = marked.parse(processed, { async: false }) as string;
        return raw;
    }, [text, docId]);

    useEffect(() => {
        if (highlightRange) {
            const el = (ref as React.RefObject<HTMLDivElement>).current;
            if (!el) return;
            const textNodes: Text[] = [];
            const walk = document.createTreeWalker(
                el, NodeFilter.SHOW_TEXT, null
            );
            let node: Text | null;
            while ((node = walk.nextNode() as Text | null)) {
                textNodes.push(node);
            }
            let offset = 0;
            for (const tn of textNodes) {
                const nextOffset = offset + tn.textContent!.length;
                if (offset <= highlightRange.start && highlightRange.start < nextOffset) {
                    const range = document.createRange();
                    range.setStart(tn, highlightRange.start - offset);
                    range.setEnd(tn, Math.min(highlightRange.end - offset, tn.textContent!.length));
                    const sel = window.getSelection();
                    sel?.removeAllRanges();
                    sel?.addRange(range);
                    tn.parentElement?.scrollIntoView({ block: 'nearest' });
                    break;
                }
                offset = nextOffset;
            }
        }
    }, [highlightRange, ref]);

    return (
        <div
            ref={ref}
            onScroll={handleScroll}
            className="article-markdown-preview"
            style={{
                flex: 1, overflow: 'auto', padding: '12px 16px',
                fontFamily: "'Georgia', 'Times New Roman', serif",
                fontSize: '14px', lineHeight: '1.7', color: '#374151',
            }}
            dangerouslySetInnerHTML={{ __html: rendered }}
        />
    );
});

export default MarkdownPreview;
