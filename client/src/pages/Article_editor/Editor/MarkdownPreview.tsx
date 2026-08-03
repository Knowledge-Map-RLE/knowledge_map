import React, { forwardRef, useEffect, useMemo, useDeferredValue } from 'react';
import { marked } from 'marked';

const IMG_API = 'http://localhost:8000/api/data_extraction/documents';

interface MarkdownPreviewProps {
    text: string;
    docId?: string;
    highlightRange?: { start: number; end: number } | null;
}

const MarkdownPreview = forwardRef<HTMLDivElement, MarkdownPreviewProps>(function MarkdownPreview(
    { text, docId, highlightRange },
    ref
) {
    // Defer the expensive markdown parse: the preview renders a slightly stale
    // version while the user types, keeping input latency low.
    const deferredText = useDeferredValue(text);

    const { yamlMeta, bodyHtml } = useMemo(() => {
        let processed = deferredText || '';
        let yamlMeta: Array<{ key: string; value: string }> | null = null;
        const yamlMatch = processed.match(/^---\n([\s\S]*?)\n---/);
        if (yamlMatch) {
            const raw = yamlMatch[1];
            yamlMeta = [];
            for (const line of raw.split('\n')) {
                const idx = line.indexOf(':');
                if (idx > 0) {
                    const k = line.slice(0, idx).trim();
                    const v = line.slice(idx + 1).trim().replace(/^"|"$/g, '');
                    if (k) yamlMeta.push({ key: k, value: v });
                }
            }
            processed = processed.slice(yamlMatch[0].length);
        }
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
        return { yamlMeta, bodyHtml: raw };
    }, [deferredText, docId]);

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
            className="article-markdown-preview"
            style={{
                flex: 1, overflow: 'auto', padding: '12px 16px',
                fontFamily: "'Georgia', 'Times New Roman', serif",
                fontSize: '14px', lineHeight: '1.7', color: '#374151',
            }}
        >
            {yamlMeta && (
                <div className="md-yaml-block">
                    {yamlMeta.map(({ key, value }) => (
                        <div key={key} className="md-yaml-line">
                            <span className="md-yaml-key">{key}</span>
                            <span className="md-yaml-value">{value}</span>
                        </div>
                    ))}
                </div>
            )}
            <div dangerouslySetInnerHTML={{ __html: bodyHtml }} />
        </div>
    );
});

export default MarkdownPreview;
