import React, { useEffect, useRef, useState, useCallback } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';
import { marked } from 'marked';
import 'katex/dist/katex.min.css';
import markedKatex from 'marked-katex-extension';
import renderMathInElement from 'katex/contrib/auto-render';
// @ts-ignore - package may not have types
import QuillMarkdown from 'quilljs-markdown';

marked.use(markedKatex({ throwOnError: false, nonStandard: true }));

type Annotation = {
    id: number;
    labels: string[]; // Мультиклассовая аннотация
    text: string;
    color: string;
    range: { index: number; length: number };
};

type MarkdownEditorProps = {
    value: string;
    onChange: (markdown: string) => void;
    onExportAnnotations?: (json: any) => void;
    onImportAnnotations?: (json: any) => void;
    onEditorReady?: (rootEl: HTMLElement) => void;
    readOnly?: boolean;
};

const AVAILABLE_LABELS = [
    'Organization', 'Person', 'Disease', 'Drug', 'Treatment',
    'Datetime', 'Gene', 'Protein', 'Location', 'Event'
];

const LABEL_COLORS: Record<string, string> = {
    'Organization': '#FF6B6B',
    'Person': '#4ECDC4',
    'Disease': '#FFD93D',
    'Drug': '#95E1D3',
    'Treatment': '#F38181',
    'Datetime': '#AA96DA',
    'Gene': '#FCBAD3',
    'Protein': '#A8D8EA',
    'Location': '#FCE38A',
    'Event': '#C7CEEA'
};

// Компонент предпросмотра в readOnly режиме — рендерит Markdown напрямую в HTML,
// минуя Quill (который стрипает KaTeX HTML через Delta).
const markdownPreviewStyles = `
.km-md-preview h1 { font-size: 2em; font-weight: 700; margin: 0.67em 0; }
.km-md-preview h2 { font-size: 1.5em; font-weight: 700; margin: 0.75em 0; }
.km-md-preview h3 { font-size: 1.25em; font-weight: 700; margin: 0.83em 0; }
.km-md-preview h4 { font-size: 1em; font-weight: 700; margin: 1.12em 0; }
.km-md-preview p { margin: 0.8em 0; line-height: 1.6; }
.km-md-preview ul { list-style-type: disc; padding-left: 2em; margin: 0.8em 0; }
.km-md-preview ol { list-style-type: decimal; padding-left: 2em; margin: 0.8em 0; }
.km-md-preview li { margin: 0.3em 0; }
.km-md-preview strong { font-weight: 700; }
.km-md-preview em { font-style: italic; }
.km-md-preview code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; font-size: 0.9em; }
.km-md-preview pre { background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0.8em 0; }
.km-md-preview pre code { background: none; padding: 0; }
.km-md-preview blockquote { border-left: 4px solid #ddd; padding-left: 1em; color: #666; margin: 0.8em 0; }
.km-md-preview a { color: #0066cc; text-decoration: underline; }
.km-md-preview img { max-width: 100%; height: auto; border-radius: 4px; margin: 8px 0; }
.km-md-preview figure { margin: 1.2em 0; text-align: center; }
.km-md-preview figure img { display: block; margin: 0 auto; }
.km-md-preview figcaption { font-size: 0.9em; color: #555; margin-top: 6px; font-style: italic; }
.km-md-preview table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
.km-md-preview th, .km-md-preview td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
.km-md-preview th { background: #f5f5f5; font-weight: 700; }

.km-katex-wrap { position: relative; display: inline-block; }
.km-katex-wrap.block { display: block; text-align: center; margin: 0.8em 0; }
.km-katex-copy {
    display: none; position: absolute; top: -6px; right: -6px;
    background: #fff; border: 1px solid #ccc; border-radius: 4px;
    padding: 2px 6px; font-size: 11px; cursor: pointer; color: #555;
    white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    line-height: 1.4; z-index: 10;
}
.km-katex-wrap:hover .km-katex-copy { display: block; }
.km-katex-copy.copied { background: #e6f4ea; color: #2a7a3b; border-color: #a5d6a7; }
`;

function MarkdownPreview({ value }: { value: string }) {
    const html = React.useMemo(() => marked.parse(value || '') as string, [value]);
    const containerRef = useRef<HTMLDivElement>(null);

    // Рендерим формулы внутри HTML-таблиц (marked не обрабатывает $...$ внутри HTML-блоков)
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;
        // Ищем таблицы с необработанными формулами
        const tables = container.querySelectorAll('table');
        tables.forEach((table) => {
            renderMathInElement(table, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false },
                ],
                throwOnError: false,
            });
        });
    }, [html]);

    // Оборачиваем каждый .katex элемент в wrapper с кнопкой копирования LaTeX
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        // Находим все корневые .katex элементы (не вложенные)
        const katexEls = container.querySelectorAll<HTMLElement>('.katex');
        katexEls.forEach((el) => {
            // Пропускаем уже обработанные и вложенные
            if (el.closest('.km-katex-wrap') || el.parentElement?.classList.contains('km-katex-wrap')) return;

            const latex = el.getAttribute('data-latex') || el.querySelector('annotation[encoding="application/x-tex"]')?.textContent || '';
            if (!latex) return;

            const isDisplay = el.classList.contains('katex-display') || el.closest('.katex-display') !== null;

            const wrap = document.createElement('span');
            wrap.className = `km-katex-wrap${isDisplay ? ' block' : ''}`;

            const btn = document.createElement('button');
            btn.className = 'km-katex-copy';
            btn.textContent = 'Copy LaTeX';
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(latex).then(() => {
                    btn.textContent = 'Скопировано!';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = 'Copy LaTeX';
                        btn.classList.remove('copied');
                    }, 1500);
                });
            });

            el.parentNode?.insertBefore(wrap, el);
            wrap.appendChild(el);
            wrap.appendChild(btn);
        });
    }, [html]);

    return (
        <>
            <style>{markdownPreviewStyles}</style>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
                <div
                    ref={containerRef}
                    className="km-md-preview"
                    style={{ padding: '12px 15px', lineHeight: '1.6', fontSize: '14px', maxWidth: '860px', margin: '0 auto' }}
                    dangerouslySetInnerHTML={{ __html: html }}
                />
            </div>
        </>
    );
}

export default function MarkdownEditor({ value, onChange, onExportAnnotations, onImportAnnotations, onEditorReady, readOnly = false }: MarkdownEditorProps) {
    const editorContainerRef = useRef<HTMLDivElement | null>(null);
    const quillInstanceRef = useRef<Quill | null>(null);
    const [internalMarkdown, setInternalMarkdown] = useState<string>(value || '');
    const annotationsRef = useRef<Annotation[]>([]);
    const lastAppliedMarkdownRef = useRef<string>('');

    // Модальное окно для выбора меток
    const [showLabelModal, setShowLabelModal] = useState(false);
    const [selectedRange, setSelectedRange] = useState<{ index: number; length: number } | null>(null);
    const [selectedText, setSelectedText] = useState('');
    const [selectedLabels, setSelectedLabels] = useState<string[]>([]);
    const [customColor, setCustomColor] = useState('#FFD93D');

    // Редактирование существующей аннотации
    const [editingAnnotation, setEditingAnnotation] = useState<Annotation | null>(null);

    useEffect(() => {
        // Инициализация Quill один раз
        if (editorContainerRef.current && !quillInstanceRef.current) {
            quillInstanceRef.current = new Quill(editorContainerRef.current, {
                theme: 'snow',
                readOnly: readOnly,
                modules: {
                    toolbar: readOnly ? false : '#km-toolbar',
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
                    const td = new TurndownService({
                        headingStyle: 'atx',
                        codeBlockStyle: 'fenced',
                    });

                    // Оставляем таблицы в HTML формате
                    td.addRule('preserveTables', {
                        filter: 'table',
                        replacement: function(content: string, node: any) {
                            return '\n' + node.outerHTML + '\n';
                        }
                    });

                    mdText = td.turndown(html);
                } catch {
                    mdText = html.replace(/<[^>]*>/g, '');
                }
                setInternalMarkdown(mdText);
                onChange(mdText);
                lastAppliedMarkdownRef.current = mdText;
            });

            // Обработчик выделения текста - открываем модальное окно (только если не readOnly)
            if (!readOnly) {
                quill.on('selection-change', (range) => {
                    if (range && range.length > 0) {
                        const text = quill.getText(range.index, range.length).trim();
                        if (text) {
                            // Проверяем, есть ли уже аннотация для этого диапазона
                            const existingAnnotation = annotationsRef.current.find(
                                ann => ann.range.index === range.index && ann.range.length === range.length
                            );

                            if (existingAnnotation) {
                                // Редактируем существующую аннотацию
                                setEditingAnnotation(existingAnnotation);
                                setSelectedLabels(existingAnnotation.labels);
                                setCustomColor(existingAnnotation.color);
                            } else {
                                // Новая аннотация
                                setEditingAnnotation(null);
                                setSelectedLabels([]);
                                setCustomColor('#FFD93D');
                            }

                            setSelectedRange(range);
                            setSelectedText(text);
                            setShowLabelModal(true);
                        }
                    }
                });
            }

            // Обработчики экспорта/импорта
            const toolbarRoot = document.getElementById('km-custom-controls');
            if (toolbarRoot) {
                const exportBtn = toolbarRoot.querySelector<HTMLButtonElement>('#km-export-btn');
                const importInput = toolbarRoot.querySelector<HTMLInputElement>('#km-import-input');

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
                const scrollEl = quill.root.parentElement as HTMLElement;
                if (scrollEl) onEditorReady(scrollEl);
            }
        }
    }, [onChange, onEditorReady, onExportAnnotations, onImportAnnotations]);

    useEffect(() => {
        // Синхронизация внешнего Markdown → HTML → редактор
        const quill = quillInstanceRef.current;
        if (!quill) return;

        if ((value || '') === lastAppliedMarkdownRef.current) return;
        setInternalMarkdown(value || '');
        const rawHtml = (marked.parse(value || '') as string) || '';
        const range = quill.getSelection();
        quill.clipboard.dangerouslyPasteHTML(rawHtml, 'silent');
        if (range) {
            const length = quill.getLength();
            const index = Math.min(range.index, Math.max(0, length - 1));
            quill.setSelection(index, 0, 'silent');
        }
        // Сбрасываем inline-стили Quill на таблицах (width:100%, table-layout:fixed)
        // которые мешают корректному отображению и горизонтальному скроллу через CSS.
        setTimeout(() => {
            const root = quill.root;
            root.querySelectorAll('table').forEach((table) => {
                (table as HTMLElement).style.removeProperty('width');
                (table as HTMLElement).style.removeProperty('table-layout');
            });
        }, 50);
        lastAppliedMarkdownRef.current = value || '';
    }, [value]);

    const handleLabelToggle = (label: string) => {
        setSelectedLabels(prev =>
            prev.includes(label)
                ? prev.filter(l => l !== label)
                : [...prev, label]
        );
    };

    const applyAnnotation = () => {
        const quill = quillInstanceRef.current;
        if (!quill || !selectedRange || selectedLabels.length === 0) return;

        if (editingAnnotation) {
            // Обновляем существующую аннотацию
            editingAnnotation.labels = selectedLabels;
            editingAnnotation.color = customColor;

            // Перерисовываем
            quill.deleteText(editingAnnotation.range.index, editingAnnotation.range.length);
            const labelsText = selectedLabels.join(', ');
            const span = `<span data-labels="${labelsText}" style="background: ${customColor}; border-radius: 4px; padding: 2px 4px; border: 2px solid #333;">${editingAnnotation.text}</span>`;
            quill.clipboard.dangerouslyPasteHTML(editingAnnotation.range.index, span, 'user');
        } else {
            // Создаём новую аннотацию
            const annotation: Annotation = {
                id: Date.now(),
                labels: selectedLabels,
                text: selectedText,
                color: customColor,
                range: selectedRange
            };

            annotationsRef.current.push(annotation);

            // Применяем подсветку с мультиклассовыми метками
            const labelsText = selectedLabels.join(', ');
            const span = `<span data-labels="${labelsText}" style="background: ${customColor}; border-radius: 4px; padding: 2px 4px; border: 2px solid #333;">${selectedText}</span>`;
            quill.deleteText(selectedRange.index, selectedRange.length);
            quill.clipboard.dangerouslyPasteHTML(selectedRange.index, span, 'user');
        }

        // Закрываем модальное окно
        setShowLabelModal(false);
        setSelectedRange(null);
        setSelectedText('');
        setSelectedLabels([]);
        setEditingAnnotation(null);
    };

    const cancelAnnotation = () => {
        setShowLabelModal(false);
        setSelectedRange(null);
        setSelectedText('');
        setSelectedLabels([]);
        setEditingAnnotation(null);
    };

    const deleteAnnotation = () => {
        const quill = quillInstanceRef.current;
        if (!quill || !editingAnnotation) return;

        // Удаляем аннотацию из массива
        annotationsRef.current = annotationsRef.current.filter(ann => ann.id !== editingAnnotation.id);

        // Убираем форматирование
        quill.deleteText(editingAnnotation.range.index, editingAnnotation.range.length);
        quill.insertText(editingAnnotation.range.index, editingAnnotation.text, 'user');

        setShowLabelModal(false);
        setEditingAnnotation(null);
    };

    // В режиме readOnly используем простой HTML-рендер чтобы KaTeX не стрипался Quill
    if (readOnly) {
        return <MarkdownPreview value={value} />;
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', position: 'relative' }}>
            {!readOnly && (
                <>
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
                        <span style={{ fontSize: 14, color: '#666' }}>
                            Выделите текст для аннотирования
                        </span>
                        <button id="km-export-btn" type="button" style={{ marginLeft: 'auto', padding: '6px 12px', borderRadius: 4, background: '#4CAF50', color: 'white', border: 'none', cursor: 'pointer' }}>
                            Экспорт
                        </button>
                        <label style={{ cursor:'pointer', padding: '6px 12px', borderRadius: 4, background: '#2196F3', color: 'white' }}>
                            Импорт
                            <input id="km-import-input" type="file" accept="application/json" style={{ display:'none' }} />
                        </label>
                    </div>
                </>
            )}
            {/* overflow-y: auto здесь — скролл у правого края всего блока, не у узкого .ql-editor */}
            <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
                <div ref={editorContainerRef} />
            </div>

            {/* Модальное окно для выбора меток */}
            {showLabelModal && (
                <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'rgba(0,0,0,0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1000
                }}>
                    <div style={{
                        background: 'white',
                        borderRadius: 8,
                        padding: 24,
                        maxWidth: 500,
                        width: '90%',
                        maxHeight: '80vh',
                        overflow: 'auto',
                        boxShadow: '0 4px 20px rgba(0,0,0,0.3)'
                    }}>
                        <h3 style={{ margin: '0 0 16px 0', fontSize: 18 }}>
                            {editingAnnotation ? 'Редактировать аннотацию' : 'Выберите метки для аннотации'}
                        </h3>
                        <div style={{
                            background: '#f5f5f5',
                            padding: 12,
                            borderRadius: 4,
                            marginBottom: 16,
                            fontSize: 14
                        }}>
                            <strong>Выделенный текст:</strong> {selectedText}
                        </div>

                        <div style={{ marginBottom: 16 }}>
                            <label style={{ display: 'block', marginBottom: 8, fontSize: 14, fontWeight: 600 }}>
                                Метки (можно выбрать несколько):
                            </label>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                {AVAILABLE_LABELS.map(label => (
                                    <button
                                        key={label}
                                        onClick={() => handleLabelToggle(label)}
                                        style={{
                                            padding: '8px 16px',
                                            borderRadius: 20,
                                            border: selectedLabels.includes(label) ? '2px solid #2196F3' : '2px solid #ddd',
                                            background: selectedLabels.includes(label) ? LABEL_COLORS[label] : 'white',
                                            color: selectedLabels.includes(label) ? '#000' : '#666',
                                            cursor: 'pointer',
                                            fontSize: 13,
                                            fontWeight: selectedLabels.includes(label) ? 600 : 400,
                                            transition: 'all 0.2s'
                                        }}
                                    >
                                        {label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div style={{ marginBottom: 20 }}>
                            <label style={{ display: 'block', marginBottom: 8, fontSize: 14, fontWeight: 600 }}>
                                Цвет подсветки:
                            </label>
                            <input
                                type="color"
                                value={customColor}
                                onChange={(e) => setCustomColor(e.target.value)}
                                style={{ width: '100%', height: 40, cursor: 'pointer', border: '2px solid #ddd', borderRadius: 4 }}
                            />
                        </div>

                        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                            {editingAnnotation && (
                                <button
                                    onClick={deleteAnnotation}
                                    style={{
                                        padding: '10px 20px',
                                        borderRadius: 4,
                                        border: 'none',
                                        background: '#f44336',
                                        color: 'white',
                                        cursor: 'pointer',
                                        fontSize: 14,
                                        fontWeight: 600,
                                        marginRight: 'auto'
                                    }}
                                >
                                    Удалить
                                </button>
                            )}
                            <button
                                onClick={cancelAnnotation}
                                style={{
                                    padding: '10px 20px',
                                    borderRadius: 4,
                                    border: '2px solid #ddd',
                                    background: 'white',
                                    color: '#666',
                                    cursor: 'pointer',
                                    fontSize: 14,
                                    fontWeight: 600
                                }}
                            >
                                Отмена
                            </button>
                            <button
                                onClick={applyAnnotation}
                                disabled={selectedLabels.length === 0}
                                style={{
                                    padding: '10px 20px',
                                    borderRadius: 4,
                                    border: 'none',
                                    background: selectedLabels.length > 0 ? '#4CAF50' : '#ccc',
                                    color: 'white',
                                    cursor: selectedLabels.length > 0 ? 'pointer' : 'not-allowed',
                                    fontSize: 14,
                                    fontWeight: 600
                                }}
                            >
                                {editingAnnotation ? 'Обновить' : 'Применить'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
