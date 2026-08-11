import { useMemo } from 'react';
import { marked, Renderer, type Tokens } from 'marked';
import markedKatex from 'marked-katex-extension';
import { MARKDOWN_PREVIEW_STYLES } from '../../../widgets/MarkdownEditor/lib/markdownStyles';

if (!(globalThis as unknown as Record<string, boolean>).__kmMarkedKatexRegistered) {
    marked.use(markedKatex({ throwOnError: false, nonStandard: true }));
    (globalThis as unknown as Record<string, boolean>).__kmMarkedKatexRegistered = true;
}

function escapeHtml(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function isSafeUrl(href: string): boolean {
    if (!href) return false;
    if (href.startsWith('/')) return true;
    return /^https?:\/\//i.test(href);
}

function tokensToText(tokens: Tokens.Link['tokens'] | undefined): string {
    if (!tokens) return '';
    return tokens.map((t) => ('text' in t ? t.text : '')).join('');
}

interface Props {
    value: string;
    className?: string;
}

export function MarkdownContent({ value, className }: Props) {
    const html = useMemo(() => {
        const renderer = new Renderer();
        renderer.html = ({ text }) => escapeHtml(text ?? '');
        renderer.image = ({ href, title, text }) => {
            if (!isSafeUrl(href ?? '')) return '';
            const alt = escapeHtml(text ?? '');
            const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
            return `<img src="${escapeHtml(href ?? '')}" alt="${alt}"${titleAttr} />`;
        };
        renderer.link = ({ href, title, tokens }) => {
            const text = tokensToText(tokens);
            if (!isSafeUrl(href ?? '')) return escapeHtml(text);
            const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
            return `<a href="${escapeHtml(href ?? '')}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
        };
        return marked.parse(value || '', { renderer, gfm: true, breaks: true }) as string;
    }, [value]);

    return (
        <>
            <style>{MARKDOWN_PREVIEW_STYLES}</style>
            <div
                className={`km-md-preview ${className ?? ''}`}
                dangerouslySetInnerHTML={{ __html: html }}
            />
        </>
    );
}
