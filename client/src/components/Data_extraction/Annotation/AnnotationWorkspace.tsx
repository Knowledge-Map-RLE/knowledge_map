import React, { useState, useEffect, useRef, useCallback } from 'react';
import AnnotationToolbar from './AnnotationToolbar';
import AnnotationPanel from './AnnotationPanel';
import RelationsPanel from './RelationsPanel';
import AnnotationFilters from './AnnotationFilters';
import EditorTabs from './EditorTabs';
import ErrorBoundary from '../../ErrorBoundary';
import PatternVisualization from '../PatternVisualization/PatternVisualization';
import SaveForTestsDialog from '../SaveForTestsDialog';
import { useAnnotations } from './hooks/useAnnotations';
import { useAnnotationOffsets } from './hooks/useAnnotationOffsets';
import { useRelations } from './hooks/useRelations';
import {
  Annotation,
  AnnotationRelation,
  autoAnnotateDocument,
  autoAnnotateMultilevel,
  MultiLevelAnalysisResponse,
  deleteAllAnnotations,
  exportAnnotationsYAML,
  importAnnotationsYAML,
} from '../../../services/api';
import './AnnotationWorkspace.css';

interface AnnotationWorkspaceProps {
  docId: string;
  text: string;
  readOnly?: boolean;
  onTextChange?: (text: string) => void;
  onSave?: () => Promise<void>;
  documentTitle?: string | null;
}

const AnnotationWorkspace: React.FC<AnnotationWorkspaceProps> = ({
  docId,
  text,
  readOnly = false,
  onTextChange,
  onSave,
  documentTitle = null,
}) => {
  // UI State
  const [mainTab, setMainTab] = useState<'text' | 'annotator'>('text');
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string>('#ffeb3b');
  const [relationMode, setRelationMode] = useState(false);
  const [showRelations, setShowRelations] = useState(false);
  const [largeLineHeight, setLargeLineHeight] = useState(false);
  const [isAutoAnnotating, setIsAutoAnnotating] = useState(false);
  const [graphData, setGraphData] = useState<MultiLevelAnalysisResponse['graph'] | null>(null);
  const [showSaveForTestsDialog, setShowSaveForTestsDialog] = useState(false);

  // Filter State
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [annotationsLimit, setAnnotationsLimit] = useState(1000);

  // Selection State
  const [pendingTextSelection, setPendingTextSelection] = useState<{
    start: number;
    end: number;
    text: string;
  } | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedAnnotation, setSelectedAnnotation] = useState<Annotation | null>(null);
  const [selectedAnnotationGroup, setSelectedAnnotationGroup] = useState<Annotation[]>([]);
  const [selectedRelation, setSelectedRelation] = useState<AnnotationRelation | null>(null);

  // Text State
  const [localText, setLocalText] = useState(text);
  const [visualAnnotations, setVisualAnnotations] = useState<Annotation[]>([]);
  const previousTextRef = useRef(text);

  // Scroll Refs
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const textAnnotatorRef = useRef<HTMLDivElement>(null);
  const savedTextareaScrollTop = useRef<number>(0);
  const savedAnnotatorScrollTop = useRef<number>(0);

  // Custom Hooks
  const {
    annotations,
    setAnnotations,
    totalAnnotations,
    loadedAnnotationsCount,
    loading,
    isLoadingMore,
    loadAnnotations,
    loadMoreAnnotations,
    createNewAnnotation,
    removeAnnotation,
    editAnnotation,
  } = useAnnotations({
    docId,
    selectedCategories,
    selectedSource,
    annotationsLimit,
  });

  const {
    calculateVisualOffsets,
    saveAnnotationOffsets,
    hasUnsavedOffsets,
    setHasUnsavedOffsets,
    annotationsToDelete,
    resetUnsavedOffsets,
    setSavedText,
  } = useAnnotationOffsets();

  const {
    relations,
    loadRelations,
    createRelation,
    removeRelation,
    editRelation,
  } = useRelations(docId);

  // Sync with external text
  useEffect(() => {
    setLocalText(text);
    previousTextRef.current = text;
    setSavedText(text);
  }, [text, setSavedText]);

  // Load data on mount and filter changes
  useEffect(() => {
    loadAnnotations();
    loadRelations();
  }, [loadAnnotations, loadRelations]);

  // Reset state on document change
  useEffect(() => {
    setPendingTextSelection(null);
    setSelectedTypes([]);
    resetUnsavedOffsets();
  }, [docId, resetUnsavedOffsets]);

  // Sync visual annotations
  useEffect(() => {
    setVisualAnnotations(annotations);
  }, [annotations]);

  // Restore scroll positions
  useEffect(() => {
    if (savedTextareaScrollTop.current > 0 || savedAnnotatorScrollTop.current > 0) {
      requestAnimationFrame(() => {
        if (textareaRef.current && savedTextareaScrollTop.current > 0) {
          textareaRef.current.scrollTop = savedTextareaScrollTop.current;
        }
        if (textAnnotatorRef.current && savedAnnotatorScrollTop.current > 0) {
          textAnnotatorRef.current.scrollTop = savedAnnotatorScrollTop.current;
        }
      });
    }
  }, [visualAnnotations]);

  // Text change handler
  const handleTextChange = useCallback((newText: string) => {
    const oldText = previousTextRef.current;
    setLocalText(newText);

    if (onTextChange) {
      onTextChange(newText);
    }

    if (oldText !== newText && visualAnnotations.length > 0) {
      const updatedVisualAnnotations = calculateVisualOffsets(oldText, newText, visualAnnotations);
      setVisualAnnotations(updatedVisualAnnotations);
      setHasUnsavedOffsets(true);
    }

    previousTextRef.current = newText;
  }, [visualAnnotations, calculateVisualOffsets, setHasUnsavedOffsets, onTextChange]);

  // Text selection handler
  const handleTextSelect = useCallback((start: number, end: number, selectedText: string) => {
    if (readOnly) return;
    setPendingTextSelection({ start, end, text: selectedText });
    setSelectedTypes([]);
  }, [readOnly]);

  // Type toggle handler
  const handleTypeToggle = useCallback(async (type: string) => {
    if (pendingTextSelection) {
      const { start, end, text: selectionText } = pendingTextSelection;
      const existingAnnotation = annotations.find(
        (ann) =>
          ann.start_offset === start &&
          ann.end_offset === end &&
          ann.annotation_type === type
      );

      if (existingAnnotation) {
        await removeAnnotation(existingAnnotation.uid);
        setSelectedTypes((prev) => prev.filter((t) => t !== type));
      } else {
        try {
          await createNewAnnotation(start, end, selectionText, type);
          setSelectedTypes((prev) => [...prev, type]);
        } catch (error: any) {
          handleAnnotationError(error);
        }
      }
      return;
    }

    if (selectedAnnotationGroup.length > 0) {
      const fragment = selectedAnnotationGroup[0];
      const existingTypes = selectedAnnotationGroup.map((ann) => ann.annotation_type);

      if (existingTypes.includes(type)) {
        const annToDelete = selectedAnnotationGroup.find((ann) => ann.annotation_type === type);
        if (annToDelete) {
          await removeAnnotation(annToDelete.uid);
        }
      } else {
        try {
          const newAnnotation = await createNewAnnotation(
            fragment.start_offset,
            fragment.end_offset,
            fragment.text,
            type
          );
          await loadAnnotations();
          setSelectedAnnotationGroup([...selectedAnnotationGroup, newAnnotation]);
        } catch (error: any) {
          handleAnnotationError(error);
        }
      }
    }
  }, [pendingTextSelection, selectedAnnotationGroup, annotations, createNewAnnotation, removeAnnotation, loadAnnotations]);

  // Annotation selection handler
  const handleAnnotationSelect = useCallback((annotation: Annotation | Annotation[]) => {
    if (Array.isArray(annotation)) {
      setSelectedAnnotationGroup(annotation);
      setSelectedAnnotation(annotation[0] || null);
      setPendingTextSelection(null);
      setSelectedTypes(annotation.map((ann) => ann.annotation_type));
    } else {
      const group = annotations.filter(
        (ann) => ann.start_offset === annotation.start_offset && ann.end_offset === annotation.end_offset
      );
      setSelectedAnnotationGroup(group);
      setSelectedAnnotation(annotation);
      setPendingTextSelection(null);
      setSelectedTypes(group.map((ann) => ann.annotation_type));
    }
  }, [annotations]);

  // Annotation delete handler
  const handleAnnotationDelete = useCallback(async (annotationId: string) => {
    try {
      await removeAnnotation(annotationId);
      const newGroup = selectedAnnotationGroup.filter((ann) => ann.uid !== annotationId);
      setSelectedAnnotationGroup(newGroup);

      if (newGroup.length === 0) {
        setSelectedAnnotation(null);
        setSelectedTypes([]);
      } else {
        setSelectedTypes(newGroup.map((ann) => ann.annotation_type));
      }
    } catch (error: any) {
      console.error('Не удалось удалить аннотацию:', error?.message || error);
    }
  }, [removeAnnotation, selectedAnnotationGroup]);

  // Annotation edit handler
  const handleAnnotationEdit = useCallback(async (annotation: Annotation) => {
    const newType = prompt('Введите новый тип аннотации:', annotation.annotation_type);
    if (!newType) return;

    try {
      await editAnnotation(annotation.uid, newType);
    } catch (error: any) {
      console.error('Не удалось обновить аннотацию:', error?.message || error);
    }
  }, [editAnnotation]);

  // Relation create handler
  const handleRelationCreate = useCallback(async (sourceId: string, targetId: string) => {
    const relationType = prompt('Введите тип связи:');
    if (!relationType) return;

    try {
      await createRelation(sourceId, targetId, relationType);
      console.log('Связь успешно создана');
    } catch (error: any) {
      handleRelationError(error);
    }
  }, [createRelation]);

  // Relation delete handler
  const handleRelationDelete = useCallback(async (sourceId: string, targetId: string) => {
    try {
      await removeRelation(sourceId, targetId);
    } catch (error: any) {
      console.error('Не удалось удалить связь:', error?.message || error);
    }
  }, [removeRelation]);

  // Relation click handler
  const handleRelationClick = useCallback((relation: AnnotationRelation) => {
    setSelectedRelation(relation);
  }, []);

  // Relation edit handler
  const handleRelationEdit = useCallback(async (relation: AnnotationRelation) => {
    const newType = prompt('Введите новый тип связи:', relation.relation_type);
    if (!newType || newType === relation.relation_type) return;

    try {
      await editRelation(relation, newType);
      console.log('Тип связи успешно изменён');
    } catch (error: any) {
      console.error('Не удалось изменить тип связи:', error?.message || error);
    }
  }, [editRelation]);

  // Auto-annotate handler
  const handleAutoAnnotate = useCallback(async () => {
    if (isAutoAnnotating) return;

    const confirmed = confirm(
      'Запустить автоматическую аннотацию с помощью spaCy?\n\n' +
      'Это создаст аннотации для всех найденных лингвистических сущностей:\n' +
      '• Части речи (существительные, глаголы, прилагательные, и т.д.)\n' +
      '• Члены предложения (подлежащее, сказуемое, дополнение, и т.д.)\n' +
      '• Именованные сущности (персоны, места, организации, и т.д.)\n' +
      '• Морфологические признаки (время, род, число, падеж, и т.д.)\n\n' +
      'Процесс может занять несколько минут для больших документов.'
    );

    if (!confirmed) return;

    setIsAutoAnnotating(true);

    try {
      const result = await autoAnnotateDocument(docId);

      console.log(
        'Автоаннотация завершена успешно!\n' +
        `Создано аннотаций: ${result.created_annotations}\n` +
        `Создано связей: ${result.created_relations}\n` +
        `Обработано символов: ${result.text_length}\n` +
        `Использованные процессоры: ${result.processors_used.join(', ')}`
      );

      await loadAnnotations();
      await loadRelations();
    } catch (error: any) {
      console.error(
        'Не удалось выполнить автоаннотацию:',
        error?.message || error,
        '\n\nПроверьте, что:\n' +
        '• Документ сохранен в базе данных\n' +
        '• Markdown файл доступен\n' +
        '• Сервер NLP запущен и доступен'
      );
    } finally {
      setIsAutoAnnotating(false);
    }
  }, [isAutoAnnotating, docId, loadAnnotations, loadRelations]);

  // Multi-level auto-annotate handler
  const handleMultiLevelAnnotate = useCallback(async () => {
    if (isAutoAnnotating) return;

    const confirmed = confirm(
      'Запустить многоуровневый NLP-анализ с голосованием?\n\n' +
      'Эта система использует несколько NLP-моделей (spaCy + NLTK) с голосованием для повышения точности:\n' +
      '• Level 1: Токенизация и сегментация предложений\n' +
      '• Level 2: Морфология и части речи (POS tagging)\n' +
      '• Level 3: Синтаксис и зависимости (dependency parsing)\n\n' +
      'Принимаются только аннотации, где минимум 2 модели согласны.\n' +
      'Результаты будут показаны в аннотаторе и в виде графа ниже.\n\n' +
      'Процесс может занять 5-10 минут для больших документов.'
    );

    if (!confirmed) return;

    setIsAutoAnnotating(true);

    try {
      const result = await autoAnnotateMultilevel(
        docId,
        true,  // enable_voting
        3,     // max_level
        true,  // create_annotations
        0.8    // min_confidence
      );

      // Store graph data for visualization
      setGraphData(result.graph);

      console.log(
        'Multi-level анализ завершен успешно!\n' +
        `Создано аннотаций: ${result.annotations_count || 0}\n` +
        `Agreement score: ${(result.summary?.agreement_score || 0).toFixed(2)}\n` +
        `Предложений: ${result.summary?.total_sentences || 0}\n` +
        `Токенов: ${result.summary?.total_tokens || 0}\n` +
        `Время обработки: ${result.processing_time.toFixed(2)}s\n` +
        `Уровни обработки: ${result.processed_levels.join(', ')}\n\n` +
        `Граф построен: ${result.graph.nodes.length} узлов, ${result.graph.edges.length} связей`
      );

      await loadAnnotations();
      await loadRelations();
    } catch (error: any) {
      console.error(
        'Не удалось выполнить multi-level анализ:',
        error?.message || error,
        '\n\nПроверьте, что:\n' +
        '• Документ сохранен в базе данных\n' +
        '• Markdown файл доступен\n' +
        '• NLP модели установлены (spaCy, NLTK)\n' +
        '• Сервер NLP запущен и доступен'
      );
    } finally {
      setIsAutoAnnotating(false);
    }
  }, [isAutoAnnotating, docId, loadAnnotations, loadRelations]);

  // Save handler
  const handleSave = useCallback(async () => {
    try {
      savedTextareaScrollTop.current = textareaRef.current?.scrollTop || 0;
      savedAnnotatorScrollTop.current = textAnnotatorRef.current?.scrollTop || 0;

      await saveAnnotationOffsets(localText, annotations, loadAnnotations);

      if (onSave) {
        await onSave();
      }

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (textareaRef.current) {
            textareaRef.current.scrollTop = savedTextareaScrollTop.current;
          }
          if (textAnnotatorRef.current) {
            textAnnotatorRef.current.scrollTop = savedAnnotatorScrollTop.current;
          }
        });
      });
    } catch (error) {
      console.error('Ошибка сохранения:', error);
    }
  }, [localText, annotations, saveAnnotationOffsets, loadAnnotations, onSave]);

  // Delete all annotations handler
  const handleDeleteAllAnnotations = useCallback(async () => {
    const confirmed = confirm(
      'Вы уверены, что хотите удалить все аннотации этого документа?\n\n' +
      'Это действие нельзя отменить!'
    );

    if (!confirmed) return;

    try {
      const result = await deleteAllAnnotations(docId);

      console.log(
        'Все аннотации успешно удалены!\n' +
        `Удалено аннотаций: ${result.deleted_count}`
      );

      await loadAnnotations();
      await loadRelations();

      setSelectedAnnotation(null);
      setSelectedAnnotationGroup([]);
      setSelectedTypes([]);
    } catch (error: any) {
      console.error(
        'Не удалось удалить аннотации:',
        error?.message || error
      );
    }
  }, [docId, loadAnnotations, loadRelations]);

  // Export YAML handler
  const handleExportYAML = useCallback(async () => {
    try {
      const blob = await exportAnnotationsYAML(docId);

      // Создать ссылку для скачивания
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `annotations_${docId}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      console.log('Аннотации экспортированы в YAML');
    } catch (error: any) {
      console.error(
        'Не удалось экспортировать аннотации:',
        error?.message || error
      );
    }
  }, [docId]);

  // Import YAML handler
  const handleImportYAML = useCallback(async (file: File) => {
    try {
      const result = await importAnnotationsYAML(docId, file);

      console.log(
        'Импорт завершен успешно!\n' +
        `Создано аннотаций: ${result.created_annotations} из ${result.total_in_file.annotations}\n` +
        `Создано связей: ${result.created_relations} из ${result.total_in_file.relations}\n` +
        (result.created_annotations < result.total_in_file.annotations ?
          'Некоторые аннотации были пропущены из-за невалидных данных.' : '')
      );

      // Перезагрузить аннотации и связи
      await loadAnnotations();
      await loadRelations();
    } catch (error: any) {
      console.error(
        'Не удалось импортировать аннотации:',
        error?.message || error
      );
    }
  }, [docId, loadAnnotations, loadRelations]);

  // Filter handlers
  const handleResetFilters = useCallback(() => {
    setSelectedCategories([]);
    setSelectedSource(null);
  }, []);

  // Error handlers
  const handleAnnotationError = (error: any) => {
    if (error?.message?.includes('404')) {
      console.error('Документ не найден в базе данных. Аннотации пока недоступны для этого документа.');
    } else {
      console.error('Не удалось создать аннотацию:', error?.message || error);
    }
  };

  const handleRelationError = (error: any) => {
    if (error?.message?.includes('404')) {
      console.error('Документ не найден в базе данных. Связи пока недоступны для этого документа.');
    } else {
      console.error('Не удалось создать связь:', error?.message || error);
    }
  };

  if (loading) {
    return <div className="loading-state">Загрузка аннотаций...</div>;
  }

  const hasUnsavedChanges = hasUnsavedOffsets || annotationsToDelete.size > 0 || !!onSave;

  return (
    <ErrorBoundary>
      <div className="annotation-workspace-container">
        <div className="annotation-workspace">
          {/* Toolbar */}
          <div className="workspace-toolbar">
          <AnnotationToolbar
            selectedType={selectedType}
            selectedColor={selectedColor}
            onTypeSelect={setSelectedType}
            onColorChange={setSelectedColor}
            relationMode={relationMode}
            onRelationModeToggle={() => setRelationMode(!relationMode)}
            showRelations={showRelations}
            onShowRelationsToggle={() => setShowRelations(!showRelations)}
            largeLineHeight={largeLineHeight}
            onLineHeightToggle={() => setLargeLineHeight(!largeLineHeight)}
            selectedTypes={selectedTypes}
            onTypeToggle={handleTypeToggle}
            hasPendingSelection={!!pendingTextSelection || selectedAnnotationGroup.length > 0}
          />
        </div>

        {/* Main Editor */}
        <div className="workspace-main">
          <ErrorBoundary>
            <EditorTabs
              mainTab={mainTab}
              localText={localText}
              visualAnnotations={visualAnnotations}
              relations={relations}
              selectedType={selectedType}
              selectedColor={selectedColor}
              relationMode={relationMode}
              showRelations={showRelations}
              largeLineHeight={largeLineHeight}
              readOnly={readOnly}
              onTabChange={setMainTab}
              onTextChange={handleTextChange}
              onTextSelect={handleTextSelect}
              onAnnotationClick={handleAnnotationSelect}
              onRelationCreate={handleRelationCreate}
              onAutoAnnotate={handleAutoAnnotate}
              onMultiLevelAnnotate={handleMultiLevelAnnotate}
              onSave={handleSave}
              onDeleteAllAnnotations={handleDeleteAllAnnotations}
              isAutoAnnotating={isAutoAnnotating}
              hasUnsavedChanges={hasUnsavedChanges}
              textareaRef={textareaRef}
              textAnnotatorRef={textAnnotatorRef}
              selectedRelation={selectedRelation}
              onRelationClick={handleRelationClick}
              onRelationDelete={handleRelationDelete}
              onExportCSV={handleExportYAML}
              onImportCSV={handleImportYAML}
              onSaveForTests={() => setShowSaveForTestsDialog(true)}
            />
          </ErrorBoundary>
        </div>

        {/* Filters Panel */}
        <div className="workspace-filters">
          <AnnotationFilters
            totalAnnotations={totalAnnotations}
            loadedAnnotationsCount={loadedAnnotationsCount}
            annotationsLimit={annotationsLimit}
            selectedCategories={selectedCategories}
            selectedSource={selectedSource}
            isLoadingMore={isLoadingMore}
            onCategoriesChange={setSelectedCategories}
            onSourceChange={setSelectedSource}
            onLimitChange={setAnnotationsLimit}
            onLoadMore={loadMoreAnnotations}
            onResetFilters={handleResetFilters}
          />
        </div>

        {/* Annotations Panel */}
        <div className="workspace-annotations-panel">
          <div className="panel-tabs">
            <div style={{ padding: '12px 16px', fontWeight: 'bold', fontSize: '14px', color: '#2196f3' }}>
              Аннотации ({annotations.length}{totalAnnotations > annotations.length ? ` из ${totalAnnotations}` : ''})
            </div>
          </div>
          <ErrorBoundary>
            <AnnotationPanel
              annotations={annotations}
              onAnnotationSelect={handleAnnotationSelect}
              onAnnotationDelete={handleAnnotationDelete}
              onAnnotationEdit={handleAnnotationEdit}
              selectedAnnotation={selectedAnnotation}
            />
          </ErrorBoundary>
        </div>

        {/* Relations Panel */}
        <div className="workspace-relations-panel">
          <div className="panel-tabs">
            <div style={{ padding: '12px 16px', fontWeight: 'bold', fontSize: '14px', color: '#2196f3' }}>
              Связи ({relations.length})
            </div>
          </div>
          <ErrorBoundary>
            <RelationsPanel
              relations={relations}
              annotations={annotations}
              onRelationDelete={handleRelationDelete}
              onRelationEdit={handleRelationEdit}
            />
          </ErrorBoundary>
        </div>
        </div>

        {/* Pattern Visualization (below main workspace) */}
        {graphData && (
          <ErrorBoundary>
            <PatternVisualization graphData={graphData} />
          </ErrorBoundary>
        )}

        {/* Save For Tests Dialog */}
        {showSaveForTestsDialog && (
          <SaveForTestsDialog
            docId={docId}
            documentTitle={documentTitle}
            onClose={() => setShowSaveForTestsDialog(false)}
          />
        )}
      </div>
    </ErrorBoundary>
  );
};

export default AnnotationWorkspace;
