import React, { useEffect, useMemo, useRef, useState } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';
import { marked } from 'marked';
// @ts-ignore - package may not have types
import QuillMarkdown from 'quilljs-markdown';
// @ts-ignore - package exports function
// конвертер Delta -> Markdown (совместимость с разными типами экспорта)
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import * as QDTM from 'quill-delta-to-markdown';

type MarkdownEditorProps = {
    value: string;
    onChange: (markdown: string) => void;
    onExportAnnotations?: (json: any) => void;
    onImportAnnotations?: (json: any) => void;
    onEditorReady?: (rootEl: HTMLElement) => void;
};

export default function MarkdownEditor({ value, onChange, onExportAnnotations, onImportAnnotations, onEditorReady }: MarkdownEditorProps) {
    const editorContainerRef = useRef<HTMLDivElement | null>(null);
    const quillInstanceRef = useRef<Quill | null>(null);
    const [internalMarkdown, setInternalMarkdown] = useState<string>(value || '');
    const [selectedLabel, setSelectedLabel] = useState<string>('');
    const annotationsRef = useRef<Array<{ id: number; label: string; text: string }>>([]);
    const lastAppliedMarkdownRef = useRef<string>('');

    useEffect(() => {
        // Инициализация Quill один раз
        if (editorContainerRef.current && !quillInstanceRef.current) {
            quillInstanceRef.current = new Quill(editorContainerRef.current, {
                theme: 'snow',
                modules: {
                    toolbar: '#km-toolbar',
                },
            });

            const quill = quillInstanceRef.current;
            // Плагин markdown
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const md = new QuillMarkdown(quill, {});

            // Слушатель изменений: HTML -> Markdown через Turndown (динамический импорт)
            quill.on('text-change', async () => {
                const html = quill.root.innerHTML || '';
                let mdText = '';
                try {
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-ignore
                    const mod = await import('turndown');
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const TurndownService: any = (mod as any).default || (mod as any).TurndownService || (mod as any);
                    const td = new TurndownService();
                    mdText = td.turndown(html);
                } catch {
                    mdText = html.replace(/<[^>]*>/g, '');
                }
                setInternalMarkdown(mdText);
                onChange(mdText);
                lastAppliedMarkdownRef.current = mdText;
            });

            // Обработчики кастомного тулбара
            const toolbarRoot = document.getElementById('km-custom-controls');
            if (toolbarRoot) {
                const labelSelect = toolbarRoot.querySelector<HTMLSelectElement>('#km-label-select');
                const markBtn = toolbarRoot.querySelector<HTMLButtonElement>('#km-mark-btn');
                const exportBtn = toolbarRoot.querySelector<HTMLButtonElement>('#km-export-btn');
                const importInput = toolbarRoot.querySelector<HTMLInputElement>('#km-import-input');

                if (labelSelect) {
                    labelSelect.addEventListener('change', (e) => {
                        setSelectedLabel((e.target as HTMLSelectElement).value);
                    });
                }
                if (markBtn) {
                    markBtn.addEventListener('click', () => {
                        if (!selectedLabel) return;
                        const range = quill.getSelection();
                        if (!range || range.length === 0) return;
                        const selectedText = quill.getText(range.index, range.length).trim();
                        if (!selectedText) return;
                        // Применяем подсветку и оборачиваем в span с data-label через dangerouslyPasteHTML в текущий диапазон
                        const span = `<span data-label="${selectedLabel}" style="background: rgba(102,126,234,0.2); border-radius: 4px; padding: 2px 4px;">${selectedText}</span>`;
                        quill.deleteText(range.index, range.length);
                        quill.clipboard.dangerouslyPasteHTML(range.index, span, 'user');
                        annotationsRef.current.push({ id: Date.now(), label: selectedLabel, text: selectedText });
                    });
                }
                if (exportBtn) {
                    exportBtn.addEventListener('click', () => {
                        if (onExportAnnotations) {
                            onExportAnnotations({ annotations: annotationsRef.current.slice() });
                        }
                    });
                }
                if (importInput) {
                    importInput.addEventListener('change', async (e) => {
                        const file = (e.target as HTMLInputElement).files?.[0];
                        if (!file) return;
                        try {
                            const text = await file.text();
                            const json = JSON.parse(text);
                            if (onImportAnnotations) onImportAnnotations(json);
                        } catch { /* noop */ }
                    });
                }
            }

            // Сообщаем контейнер редактора для синхронизации скролла
            if (onEditorReady) {
                const scrollEl = quill.root.parentElement as HTMLElement; // .ql-editor контейнер скроллится внутри .ql-container
                if (scrollEl) onEditorReady(scrollEl);
            }
        }
    }, [onChange]);

    useEffect(() => {
        // Синхронизация внешнего Markdown → HTML → редактор (без сброса курсора, только при фактическом изменении)
        const quill = quillInstanceRef.current;
        if (!quill) return;
        if ((value || '') === lastAppliedMarkdownRef.current) return;
        setInternalMarkdown(value || '');
        const htmlFromMd = (marked.parse(value || '') as string) || '';
        const range = quill.getSelection();
        quill.clipboard.dangerouslyPasteHTML(htmlFromMd, 'silent');
        if (range) {
            // восстанавливаем выделение
            const length = quill.getLength();
            const index = Math.min(range.index, Math.max(0, length - 1));
            quill.setSelection(index, 0, 'silent');
        }
        lastAppliedMarkdownRef.current = value || '';
    }, [value]);

    // Дополнительной инициализации не требуется

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
            <div id="km-toolbar">
                <span className="ql-formats"> 
                    <select className="ql-header" defaultValue="">
                        <option value="1"></option>
                        <option value="2"></option>
                        <option value=""></option>
                    </select>
                    <button className="ql-bold"></button>
                    <button className="ql-italic"></button>
                    <button className="ql-underline"></button>
                    <button className="ql-strike"></button>
                    <button className="ql-blockquote"></button>
                    <button className="ql-code-block"></button>
                    <button className="ql-list" value="ordered"></button>
                    <button className="ql-list" value="bullet"></button>
                    <button className="ql-link"></button>
                    <button className="ql-image"></button>
                    <button className="ql-clean"></button>
                </span>
            </div>
            <div id="km-custom-controls" style={{ display:'flex', alignItems:'center', gap:8 }}>
                <select id="km-label-select" defaultValue="">
                    <option value="">Label…</option>
                    <option value="Organization">Organization</option>
                    <option value="Person">Person</option>
                    <option value="Disease">Disease</option>
                    <option value="Drug">Drug</option>
                    <option value="Treatment">Treatment</option>
                    <option value="Datetime">Datetime</option>
                    <option value="Gene">Gene</option>
                    <option value="Protein">Protein</option>
                </select>
                <button id="km-mark-btn" type="button">Разметить</button>
                <button id="km-export-btn" type="button">Экспорт</button>
                <label style={{ cursor:'pointer' }}>
                    Импорт
                    <input id="km-import-input" type="file" accept="application/json" style={{ display:'none' }} />
                </label>
            </div>
            <div style={{ flex: '1 1 auto', minHeight: 0 }}>
                <div ref={editorContainerRef} style={{ height: '100%' }} />
            </div>
        </div>
    );
}


