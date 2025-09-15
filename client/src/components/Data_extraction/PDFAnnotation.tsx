import React, { useState, useRef, useEffect } from 'react';
import s from './PDFAnnotation.module.css';

interface Annotation {
    id: string;
    type: 'entity' | 'relation';
    content: string;
    start: number;
    end: number;
    label: string;
    confidence?: number;
    page?: number;
    bbox?: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
}

interface Relation {
    id: string;
    source: string;
    target: string;
    type: string;
    confidence?: number;
}

interface PDFAnnotationProps {
    documentId: string;
    onAnnotationsChange: (annotations: Annotation[], relations: Relation[]) => void;
}

export default function PDFAnnotation({ documentId, onAnnotationsChange }: PDFAnnotationProps) {
    const [annotations, setAnnotations] = useState<Annotation[]>([]);
    const [relations, setRelations] = useState<Relation[]>([]);
    const [selectedText, setSelectedText] = useState<string>('');
    const [selectedLabel, setSelectedLabel] = useState<string>('');
    const [isSelecting, setIsSelecting] = useState(false);
    const [showRelationModal, setShowRelationModal] = useState(false);
    const [relationType, setRelationType] = useState<string>('');
    const [selectedAnnotations, setSelectedAnnotations] = useState<string[]>([]);
    const [manualTextInput, setManualTextInput] = useState<string>('');
    const [showTextInput, setShowTextInput] = useState(false);
    
    const pdfContainerRef = useRef<HTMLDivElement>(null);
    const iframeRef = useRef<HTMLIFrameElement>(null);

    const labels = [
        { value: 'disease', label: 'Заболевание', color: '#ff6b6b' },
        { value: 'symptom', label: 'Симптом', color: '#4ecdc4' },
        { value: 'treatment', label: 'Лечение', color: '#45b7d1' },
        { value: 'drug', label: 'Препарат', color: '#96ceb4' },
        { value: 'anatomy', label: 'Анатомия', color: '#feca57' },
        { value: 'procedure', label: 'Процедура', color: '#ff9ff3' }
    ];

    const relationTypes = [
        { value: 'causes', label: 'Вызывает' },
        { value: 'treats', label: 'Лечит' },
        { value: 'affects', label: 'Влияет на' },
        { value: 'prevents', label: 'Предотвращает' },
        { value: 'indicates', label: 'Указывает на' },
        { value: 'contraindicates', label: 'Противопоказан при' }
    ];

    const handleTextSelection = () => {
        const selection = window.getSelection();
        if (selection && selection.toString().trim()) {
            setSelectedText(selection.toString().trim());
            setIsSelecting(true);
        }
    };

    const addAnnotation = () => {
        if (!selectedText || !selectedLabel) return;

        const newAnnotation: Annotation = {
            id: `ann_${Date.now()}`,
            type: 'entity',
            content: selectedText,
            start: 0, // В реальном проекте нужно вычислять позицию в тексте
            end: selectedText.length,
            label: selectedLabel,
            confidence: 1.0
        };

        setAnnotations(prev => [...prev, newAnnotation]);
        setSelectedText('');
        setSelectedLabel('');
        setIsSelecting(false);
        
        // Уведомляем родительский компонент
        onAnnotationsChange(annotations, relations);
    };

    const addAnnotationFromInput = () => {
        if (!manualTextInput || !selectedLabel) return;

        const newAnnotation: Annotation = {
            id: `ann_${Date.now()}`,
            type: 'entity',
            content: manualTextInput,
            start: 0,
            end: manualTextInput.length,
            label: selectedLabel,
            confidence: 1.0
        };

        setAnnotations(prev => [...prev, newAnnotation]);
        setManualTextInput('');
        setSelectedLabel('');
        setShowTextInput(false);
        
        // Уведомляем родительский компонент
        onAnnotationsChange(annotations, relations);
    };

    const addRelation = () => {
        if (selectedAnnotations.length !== 2 || !relationType) return;

        const newRelation: Relation = {
            id: `rel_${Date.now()}`,
            source: selectedAnnotations[0],
            target: selectedAnnotations[1],
            type: relationType,
            confidence: 1.0
        };

        setRelations(prev => [...prev, newRelation]);
        setSelectedAnnotations([]);
        setRelationType('');
        setShowRelationModal(false);
        
        // Уведомляем родительский компонент
        onAnnotationsChange(annotations, relations);
    };

    const deleteAnnotation = (id: string) => {
        setAnnotations(prev => prev.filter(ann => ann.id !== id));
        setRelations(prev => prev.filter(rel => rel.source !== id && rel.target !== id));
        onAnnotationsChange(annotations, relations);
    };

    const deleteRelation = (id: string) => {
        setRelations(prev => prev.filter(rel => rel.id !== id));
        onAnnotationsChange(annotations, relations);
    };

    const exportAnnotations = () => {
        const data = {
            annotations,
            relations,
            documentId,
            timestamp: new Date().toISOString()
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `annotations_${documentId}.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className={s.annotationContainer}>
            {/* Панель инструментов */}
            <div className={s.toolbar}>
                <div className={s.toolbarSection}>
                    <h3>Создание аннотаций</h3>
                    <div className={s.instructionText}>
                        <p>📝 <strong>Способ 1:</strong> Выделите текст в PDF ниже и выберите тип сущности</p>
                        <p>✏️ <strong>Способ 2:</strong> Введите текст вручную</p>
                    </div>
                    
                    {isSelecting && (
                        <div className={s.selectionPanel}>
                            <p>Выбранный текст: <strong>"{selectedText}"</strong></p>
                            <select 
                                value={selectedLabel} 
                                onChange={(e) => setSelectedLabel(e.target.value)}
                                className={s.labelSelect}
                            >
                                <option value="">Выберите тип сущности</option>
                                {labels.map(label => (
                                    <option key={label.value} value={label.value}>
                                        {label.label}
                                    </option>
                                ))}
                            </select>
                            <button 
                                onClick={addAnnotation}
                                disabled={!selectedLabel}
                                className={s.addButton}
                            >
                                Добавить аннотацию
                            </button>
                            <button 
                                onClick={() => setIsSelecting(false)}
                                className={s.cancelButton}
                            >
                                Отмена
                            </button>
                        </div>
                    )}

                    {!isSelecting && (
                        <div className={s.manualInputSection}>
                            <button 
                                onClick={() => setShowTextInput(!showTextInput)}
                                className={s.toggleButton}
                            >
                                {showTextInput ? 'Скрыть ручной ввод' : 'Ввести текст вручную'}
                            </button>
                            
                            {showTextInput && (
                                <div className={s.inputPanel}>
                                    <textarea
                                        value={manualTextInput}
                                        onChange={(e) => setManualTextInput(e.target.value)}
                                        placeholder="Введите текст для аннотации..."
                                        className={s.textInput}
                                        rows={3}
                                    />
                                    <select 
                                        value={selectedLabel} 
                                        onChange={(e) => setSelectedLabel(e.target.value)}
                                        className={s.labelSelect}
                                    >
                                        <option value="">Выберите тип сущности</option>
                                        {labels.map(label => (
                                            <option key={label.value} value={label.value}>
                                                {label.label}
                                            </option>
                                        ))}
                                    </select>
                                    <button 
                                        onClick={addAnnotationFromInput}
                                        disabled={!manualTextInput || !selectedLabel}
                                        className={s.addButton}
                                    >
                                        Добавить аннотацию
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className={s.toolbarSection}>
                    <h3>Связи</h3>
                    <button 
                        onClick={() => setShowRelationModal(true)}
                        disabled={annotations.length < 2}
                        className={s.relationButton}
                    >
                        Добавить связь
                    </button>
                </div>

                <div className={s.toolbarSection}>
                    <button onClick={exportAnnotations} className={s.exportButton}>
                        Экспорт аннотаций
                    </button>
                </div>
            </div>

            {/* PDF просмотр */}
            <div className={s.pdfContainer} ref={pdfContainerRef}>
                <div className={s.pdfHeader}>
                    <h4>PDF документ</h4>
                    <p className={s.pdfHint}>💡 Попробуйте выделить текст в PDF для создания аннотации</p>
                </div>
                <iframe
                    ref={iframeRef}
                    src={`http://localhost:8000/api/pdf/document/${documentId}/view`}
                    className={s.pdfViewer}
                    title="PDF Viewer"
                    onMouseUp={handleTextSelection}
                />
            </div>

            {/* Список аннотаций */}
            <div className={s.annotationsPanel}>
                <h3>Аннотации ({annotations.length})</h3>
                <div className={s.annotationsList}>
                    {annotations.map(annotation => (
                        <div key={annotation.id} className={s.annotationItem}>
                            <div className={s.annotationHeader}>
                                <span 
                                    className={s.annotationLabel}
                                    style={{ 
                                        backgroundColor: labels.find(l => l.value === annotation.label)?.color 
                                    }}
                                >
                                    {labels.find(l => l.value === annotation.label)?.label}
                                </span>
                                <button 
                                    onClick={() => deleteAnnotation(annotation.id)}
                                    className={s.deleteButton}
                                >
                                    ×
                                </button>
                            </div>
                            <p className={s.annotationContent}>"{annotation.content}"</p>
                        </div>
                    ))}
                </div>

                <h3>Связи ({relations.length})</h3>
                <div className={s.relationsList}>
                    {relations.map(relation => {
                        const sourceAnn = annotations.find(a => a.id === relation.source);
                        const targetAnn = annotations.find(a => a.id === relation.target);
                        const relType = relationTypes.find(r => r.value === relation.type);
                        
                        return (
                            <div key={relation.id} className={s.relationItem}>
                                <div className={s.relationContent}>
                                    <span className={s.relationSource}>"{sourceAnn?.content}"</span>
                                    <span className={s.relationType}>{relType?.label}</span>
                                    <span className={s.relationTarget}>"{targetAnn?.content}"</span>
                                </div>
                                <button 
                                    onClick={() => deleteRelation(relation.id)}
                                    className={s.deleteButton}
                                >
                                    ×
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Модальное окно для создания связей */}
            {showRelationModal && (
                <div className={s.modalOverlay}>
                    <div className={s.modal}>
                        <h3>Создать связь</h3>
                        <div className={s.relationForm}>
                            <div className={s.formGroup}>
                                <label>Источник:</label>
                                <select 
                                    value={selectedAnnotations[0] || ''}
                                    onChange={(e) => setSelectedAnnotations([e.target.value, selectedAnnotations[1]])}
                                >
                                    <option value="">Выберите источник</option>
                                    {annotations.map(ann => (
                                        <option key={ann.id} value={ann.id}>
                                            {labels.find(l => l.value === ann.label)?.label}: "{ann.content}"
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className={s.formGroup}>
                                <label>Тип связи:</label>
                                <select 
                                    value={relationType}
                                    onChange={(e) => setRelationType(e.target.value)}
                                >
                                    <option value="">Выберите тип связи</option>
                                    {relationTypes.map(type => (
                                        <option key={type.value} value={type.value}>
                                            {type.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className={s.formGroup}>
                                <label>Цель:</label>
                                <select 
                                    value={selectedAnnotations[1] || ''}
                                    onChange={(e) => setSelectedAnnotations([selectedAnnotations[0], e.target.value])}
                                >
                                    <option value="">Выберите цель</option>
                                    {annotations.filter(ann => ann.id !== selectedAnnotations[0]).map(ann => (
                                        <option key={ann.id} value={ann.id}>
                                            {labels.find(l => l.value === ann.label)?.label}: "{ann.content}"
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className={s.modalButtons}>
                                <button onClick={addRelation} className={s.addButton}>
                                    Создать связь
                                </button>
                                <button 
                                    onClick={() => setShowRelationModal(false)}
                                    className={s.cancelButton}
                                >
                                    Отмена
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
