import React, { useEffect, useRef, useState } from 'react';
import Quill from 'quill';
import 'quill/dist/quill.snow.css';
import { marked } from 'marked';
// @ts-ignore - package may not have types
import QuillMarkdown from 'quilljs-markdown';

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
        const htmlFromMd = (marked.parse(value || '') as string) || '';
        const range = quill.getSelection();
        quill.clipboard.dangerouslyPasteHTML(htmlFromMd, 'silent');
        if (range) {
            const length = quill.getLength();
            const index = Math.min(range.index, Math.max(0, length - 1));
            quill.setSelection(index, 0, 'silent');
        }
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
            <div style={{ flex: '1 1 auto', minHeight: 0 }}>
                <div ref={editorContainerRef} style={{ height: '100%' }} />
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
