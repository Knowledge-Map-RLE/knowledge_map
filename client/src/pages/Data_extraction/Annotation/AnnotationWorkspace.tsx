import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import AnnotationToolbar from './AnnotationToolbar';
import AnnotationPanel from './AnnotationPanel';
import RelationsPanel from './RelationsPanel';
import EditorTabsWithValidation from './EditorTabsWithValidation';
import ErrorBoundary from '../../../shared/ui/ErrorBoundary';
import { useRequireAuth } from '../../../shared/hooks/useRequireAuth';
import SaveForTestsDialog from '../SaveForTestsDialog';
import { useAnnotationsWS } from './hooks/useAnnotationsWS';
import { useAnnotationOffsets } from './hooks/useAnnotationOffsets';
import { useRelations } from './hooks/useRelations';
import {
  autoAnnotateMultilevel,
  getNlpTaskStatus,
  deleteAllAnnotations,
  createAnnotation,
  createAnnotationRelation,
  buildAnnotationsCSV,
  parseAnnotationsCSV,
  getDocumentAssets,
  batchUpdateAnnotationOffsets,
} from '../../../services/api';
import type {
  Annotation,
  AnnotationRelation,
} from '../../../services/api';
import './AnnotationWorkspace.css';

interface AnnotationWorkspaceProps {
  docId: string;
  text: string;
  readOnly?: boolean;
  onTextChange?: (text: string) => void;
  onSave?: () => Promise<void>;
  documentTitle?: string | null;
  onUpdateDocumentStatus?: (docId: string, newStatus: string) => void;
  onNlpProcessingChange?: (processing: boolean) => void;
}

const AnnotationWorkspace: React.FC<AnnotationWorkspaceProps> = ({
  docId,
  text,
  readOnly = false,
  onTextChange,
  onSave,
  documentTitle = null,
  onUpdateDocumentStatus,
  onNlpProcessingChange,
}) => {
  const requireAuth = useRequireAuth();

  // UI State
  const [mainTab, setMainTab] = useState<'text' | 'annotator'>('text');
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string>('#ffeb3b');
  const [relationMode, setRelationMode] = useState(false);
  const [showRelations, setShowRelations] = useState(false);
  const [largeLineHeight, setLargeLineHeight] = useState(false);
  const [isAutoAnnotating, setIsAutoAnnotating] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<number | null>(null);
  const [showSaveForTestsDialog, setShowSaveForTestsDialog] = useState(false);

  // Filter State
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());

  // Selection State
  const [pendingTextSelection, setPendingTextSelection] = useState<{
    start: number;
    end: number;
    text: string;
  } | null>(null);
  // Ref-зеркало для горячего пути — не теряется при React Strict Mode re-renders
  const pendingTextSelectionRef = useRef<{
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
  // shiftedAnnotations: null = не активен (отображаем visibleAnnotations), иначе — preview сдвига
  const [shiftedAnnotations, setShiftedAnnotations] = useState<Annotation[] | null>(null);
  const previousTextRef = useRef(text);
  // localTextRef — горячий путь при печати: не вызывает ре-рендер
  const localTextRef = useRef(text);
  // visualAnnotationsRef — горячий путь в колбэках: всегда актуален, не вызывает ре-рендер
  const visualAnnotationsRef = useRef<Annotation[]>([]);

  // Undo/Redo стек для текста
  const undoStackRef = useRef<string[]>([]);
  const redoStackRef = useRef<string[]>([]);
  const [undoRedoVersion, setUndoRedoVersion] = useState(0);

  // Scroll Refs
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const textAnnotatorRef = useRef<HTMLDivElement>(null);
  const savedTextareaScrollTop = useRef<number>(0);
  const savedAnnotatorScrollTop = useRef<number>(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isImportingRef = useRef(false);

  // Cursor position for shift functionality
  const [cursorPosition, setCursorPosition] = useState<number | null>(null);
  const shiftDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shiftSaveRef = useRef<Annotation[]>([]);

  // Import progress
  const [importProgress, setImportProgress] = useState<{ current: number; total: number } | null>(null);

  // Custom Hooks
  const {
    annotations,
    totalAnnotations,
    loading,
    loadAnnotations,
    createNewAnnotation,
    removeAnnotation,
    editAnnotation,
  } = useAnnotationsWS({
    docId,
    selectedCategories,
    selectedSource,
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

  // Стабильный ref для аннотаций — не вызывает пересоздание useCallback в useRelations
  const annotationsRef = useRef(annotations);
  annotationsRef.current = annotations;

  const {
    relations,
    loadRelations,
    createRelation,
    removeRelation,
    editRelation,
  } = useRelations(docId, annotationsRef);

  // Клиентская фильтрация по типам — мгновенно, без запроса к серверу
  const visibleAnnotations = useMemo(
    () => hiddenTypes.size === 0
      ? annotations
      : annotations.filter(a => !hiddenTypes.has(a.annotation_type)),
    [annotations, hiddenTypes]
  );

  // visualAnnotations: shiftedAnnotations при активном preview сдвига, иначе visibleAnnotations.
  // Вычисляется в рендере — без useEffect, без лишнего ре-рендера при загрузке аннотаций.
  const visualAnnotations = shiftedAnnotations ?? visibleAnnotations;
  // Синхронизируем ref без ре-рендера — используется в горячих колбэках
  visualAnnotationsRef.current = visualAnnotations;

  const handleTypeVisibilityToggle = useCallback((type: string, visible: boolean) => {
    setHiddenTypes(prev => {
      const next = new Set(prev);
      if (visible) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const handleShowAllTypes = useCallback(() => {
    setHiddenTypes(new Set());
  }, []);

  // Sync with external text
  useEffect(() => {
    setLocalText(text);
    localTextRef.current = text;
    previousTextRef.current = text;
    setSavedText(text);
  }, [text, setSavedText]);

  // Загрузка аннотаций: при смене документа и при смене фильтров.
  // loadAnnotations пересоздаётся при смене docId или фильтров — этого достаточно.
  // Важно: этот эффект идёт ПОСЛЕ useEffect([docId]) в useAnnotationsWS,
  // поэтому destroyedRef уже сброшен в false к моменту вызова.
  useEffect(() => {
    loadAnnotations();
    loadRelations();
  }, [loadAnnotations, loadRelations]);

  // Reset state on document change
  useEffect(() => {
    setPendingTextSelection(null);
    pendingTextSelectionRef.current = null;
    setSelectedTypes([]);
    resetUnsavedOffsets();
    setShiftedAnnotations(null);
  }, [docId, resetUnsavedOffsets]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

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
  }, [visibleAnnotations]);

  // Text change handler
  // Намеренно НЕ вызываем setLocalText — только обновляем ref.
  // setLocalText вызывается с debounce через scheduleLocalTextSync ниже,
  // чтобы не вызывать ре-рендер всего дерева при каждом нажатии клавиши.
  const scheduleLocalTextSyncRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTextChange = useCallback((newText: string) => {
    const oldText = previousTextRef.current;

    if (oldText !== newText) {
      // Сохраняем предыдущее состояние в стек undo
      undoStackRef.current.push(oldText);
      if (undoStackRef.current.length > 100) undoStackRef.current.shift();
      // Новое изменение сбрасывает redo
      redoStackRef.current = [];
    }

    // Обновляем ref немедленно — без ре-рендера
    localTextRef.current = newText;

    // Синхронизируем React state с debounce 300ms для валидации и textarea
    if (scheduleLocalTextSyncRef.current) clearTimeout(scheduleLocalTextSyncRef.current);
    scheduleLocalTextSyncRef.current = setTimeout(() => {
      setLocalText(localTextRef.current);
    }, 300);

    if (onTextChange) {
      onTextChange(newText);
    }

    if (oldText !== newText && visualAnnotationsRef.current.length > 0) {
      const updatedVisualAnnotations = calculateVisualOffsets(oldText, newText, visualAnnotationsRef.current);
      setShiftedAnnotations(updatedVisualAnnotations);
      setHasUnsavedOffsets(true);
    }

    previousTextRef.current = newText;
  }, [calculateVisualOffsets, setHasUnsavedOffsets, onTextChange]);

  const handleUndo = useCallback(() => {
    if (undoStackRef.current.length === 0) return;
    const current = previousTextRef.current;
    const prev = undoStackRef.current.pop()!;
    redoStackRef.current.push(current);
    previousTextRef.current = prev;
    localTextRef.current = prev;
    setLocalText(prev);
    setUndoRedoVersion(v => v + 1);
    if (visualAnnotationsRef.current.length > 0) {
      const updated = calculateVisualOffsets(current, prev, visualAnnotationsRef.current);
      setShiftedAnnotations(updated);
      setHasUnsavedOffsets(true);
    }
    if (onTextChange) onTextChange(prev);
  }, [onTextChange, calculateVisualOffsets, setHasUnsavedOffsets]);

  const handleRedo = useCallback(() => {
    if (redoStackRef.current.length === 0) return;
    const current = previousTextRef.current;
    const next = redoStackRef.current.pop()!;
    undoStackRef.current.push(current);
    previousTextRef.current = next;
    localTextRef.current = next;
    setLocalText(next);
    setUndoRedoVersion(v => v + 1);
    if (visualAnnotationsRef.current.length > 0) {
      const updated = calculateVisualOffsets(current, next, visualAnnotationsRef.current);
      setShiftedAnnotations(updated);
      setHasUnsavedOffsets(true);
    }
    if (onTextChange) onTextChange(next);
  }, [onTextChange, calculateVisualOffsets, setHasUnsavedOffsets]);

  // Text selection handler
  const handleTextSelect = useCallback((start: number, end: number, selectedText: string) => {
    if (readOnly) return;
    // Если выделение пустое (клинули вне текста) — не трогаем pending selection
    if (!selectedText || selectedText.trim().length === 0) return;
    const selection = { start, end, text: selectedText };
    setPendingTextSelection(selection);
    pendingTextSelectionRef.current = selection;
    setSelectedTypes([]);
  }, [readOnly]);

  // Type toggle handler
  const handleTypeToggle = useCallback(async (type: string) => {
    if (!requireAuth()) return;

    // Приоритет 1: есть pending text selection из редактора (state или ref)
    const selection = pendingTextSelection ?? pendingTextSelectionRef.current;
    if (selection && selection.text) {
      const { start, end, text: selectionText } = selection;
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
          await createNewAnnotation(start, end, selectionText, type, selectedColor);
          setSelectedTypes((prev) => prev.includes(type) ? prev : [...prev, type]);
        } catch (error: any) {
          handleAnnotationError(error);
        }
      }
      // Сбрасываем pending selection после создания/удаления
      setPendingTextSelection(null);
      pendingTextSelectionRef.current = null;
      return;
    }

    // Приоритет 2: есть выбранная группа аннотаций
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
            type,
            selectedColor,
          );
          await loadAnnotations();
          setSelectedAnnotationGroup([...selectedAnnotationGroup, newAnnotation]);
        } catch (error: any) {
          handleAnnotationError(error);
        }
      }
      return;
    }

    // Нет валидного выделения — сообщаем пользователю
    console.warn('handleTypeToggle: нет выделения текста или выбранной аннотации');
  }, [pendingTextSelection, selectedAnnotationGroup, annotations, createNewAnnotation, removeAnnotation, loadAnnotations, selectedColor, requireAuth]);

  // Annotation selection handler
  const handleAnnotationSelect = useCallback((annotation: Annotation | Annotation[]) => {
    if (Array.isArray(annotation)) {
      setSelectedAnnotationGroup(annotation);
      setSelectedAnnotation(annotation[0] || null);
      setPendingTextSelection(null);
      pendingTextSelectionRef.current = null;
      setSelectedTypes(annotation.map((ann) => ann.annotation_type));
    } else {
      const group = annotations.filter(
        (ann) => ann.start_offset === annotation.start_offset && ann.end_offset === annotation.end_offset
      );
      setSelectedAnnotationGroup(group);
      setSelectedAnnotation(annotation);
      setPendingTextSelection(null);
      pendingTextSelectionRef.current = null;
      setSelectedTypes(group.map((ann) => ann.annotation_type));
    }
  }, [annotations]);

  // Annotation delete handler
  const handleAnnotationDelete = useCallback(async (annotationId: string) => {
    if (!requireAuth()) return;

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
  }, [removeAnnotation, selectedAnnotationGroup, requireAuth]);

  // Annotation edit handler
  const handleAnnotationEdit = useCallback(async (annotation: Annotation) => {
    if (!requireAuth()) return;
    const newType = prompt('Введите новый тип аннотации:', annotation.annotation_type);
    if (!newType) return;

    try {
      await editAnnotation(annotation.uid, newType);
    } catch (error: any) {
      console.error('Не удалось обновить аннотацию:', error?.message || error);
    }
  }, [editAnnotation, requireAuth]);

  // Relation create handler
  const handleRelationCreate = useCallback(async (sourceId: string, targetId: string) => {
    if (!requireAuth()) return;
    const relationType = prompt('Введите тип связи:');
    if (!relationType) return;

    try {
      await createRelation(sourceId, targetId, relationType);
      console.log('Связь успешно создана');
    } catch (error: any) {
      handleRelationError(error);
    }
  }, [createRelation, requireAuth]);

  // Relation delete handler
  const handleRelationDelete = useCallback(async (sourceId: string, targetId: string) => {
    if (!requireAuth()) return;
    try {
      await removeRelation(sourceId, targetId);
    } catch (error: any) {
      console.error('Не удалось удалить связь:', error?.message || error);
    }
  }, [removeRelation, requireAuth]);

  // Relation click handler
  const handleRelationClick = useCallback((relation: AnnotationRelation) => {
    setSelectedRelation(relation);
  }, []);

  // Relation edit handler
  const handleRelationEdit = useCallback(async (relation: AnnotationRelation) => {
    if (!requireAuth()) return;
    const newType = prompt('Введите новый тип связи:', relation.relation_type);
    if (!newType || newType === relation.relation_type) return;

    try {
      await editRelation(relation, newType);
      console.log('Тип связи успешно изменён');
    } catch (error: any) {
      console.error('Не удалось изменить тип связи:', error?.message || error);
    }
  }, [editRelation, requireAuth]);

  // Multi-level auto-annotate handler
  const handleMultiLevelAnnotate = useCallback(async () => {
    if (isAutoAnnotating) return;
    if (!requireAuth()) return;

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
    setAnalysisProgress(0);
    if (onNlpProcessingChange) onNlpProcessingChange(true);

    // Update document status to 'processing' when multi-level analysis starts
    if (onUpdateDocumentStatus) {
        onUpdateDocumentStatus(docId, 'processing');
    }

    // Имитация прогресса до получения реального статуса
    const progressInterval = setInterval(() => {
      setAnalysisProgress(prev => {
        if (prev === null) return 0;
        const next = prev + Math.floor(Math.random() * 3) + 1;
        return next > 90 ? 90 : next;
      });
    }, 1000);
    progressIntervalRef.current = progressInterval;

    try {
      await autoAnnotateMultilevel(
        docId,
        true,  // enable_voting
        3,     // max_level
        true,  // create_annotations
        0.8    // min_confidence
      );

      // Очищаем предыдущий polling если был
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);

      // Поллим только лёгкий статус-эндпоинт — без перезагрузки аннотаций
      // Аннотации загружаем один раз по завершении задачи
      const startedAt = Date.now();
      const MAX_WAIT_MS = 600_000; // 10 минут

      pollIntervalRef.current = setInterval(async () => {
        try {
          const { status, error } = await getNlpTaskStatus(docId);

          const stopPolling = () => {
            if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; }
            if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
          };

            if (status === 'done') {
                stopPolling();
                setAnalysisProgress(100);
                await loadAnnotations();
                await loadRelations();
                setIsAutoAnnotating(false);
                setAnalysisProgress(null);
                if (onNlpProcessingChange) onNlpProcessingChange(false);
                // Статус 'annotated' НЕ проставляется здесь: он назначается только
                // после сохранения валидного markdown (PUT /documents/{id}/markdown).
                return;
            }

          if (status === 'error') {
            stopPolling();
            console.error('NLP анализ завершился с ошибкой:', error);
            setIsAutoAnnotating(false);
            setAnalysisProgress(null);
            if (onNlpProcessingChange) onNlpProcessingChange(false);
            return;
          }

          // Таймаут ожидания
          if (Date.now() - startedAt > MAX_WAIT_MS) {
            stopPolling();
            setIsAutoAnnotating(false);
            setAnalysisProgress(null);
            if (onNlpProcessingChange) onNlpProcessingChange(false);
          }
        } catch {
          // сетевая ошибка при поллинге — продолжаем
        }
      }, 3000);

    } catch (error: any) {
      console.error('Не удалось запустить multi-level анализ:', error?.message || error);
      if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
      setIsAutoAnnotating(false);
      setAnalysisProgress(null);
      if (onNlpProcessingChange) onNlpProcessingChange(false);
    }
  }, [isAutoAnnotating, docId, loadAnnotations, loadRelations, onNlpProcessingChange, onUpdateDocumentStatus, requireAuth]);

  // Save handler
  const handleSave = useCallback(async () => {
    if (!requireAuth()) return;
    try {
      savedTextareaScrollTop.current = textareaRef.current?.scrollTop || 0;
      savedAnnotatorScrollTop.current = textAnnotatorRef.current?.scrollTop || 0;

      await saveAnnotationOffsets(localTextRef.current, annotations, loadAnnotations);

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
  }, [annotations, saveAnnotationOffsets, loadAnnotations, onSave, requireAuth]);

  // Delete all annotations handler
  const handleDeleteAllAnnotations = useCallback(async () => {
    if (!requireAuth()) return;
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
  }, [docId, loadAnnotations, loadRelations, requireAuth]);

  // Export CSV handler
  const handleExportCSV = useCallback(() => {
    try {
      const csvContent = buildAnnotationsCSV(annotations, relations);
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `annotations_${docId}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      console.log('Аннотации экспортированы в CSV');
    } catch (error: any) {
      console.error('Не удалось экспортировать аннотации:', error?.message || error);
    }
  }, [docId, annotations, relations]);

  // Download Markdown as ZIP handler
  const handleDownloadMarkdown = useCallback(async () => {
    try {
      const assets = await getDocumentAssets(docId);
      if (!assets.success || !assets.markdown) {
        console.error('Не удалось получить данные документа');
        return;
      }

      const JSZip = (await import('jszip')).default;
      const zip = new JSZip();

      let mdContent = assets.markdown;
      const imageFolder = zip.folder('images')!;

      // Найти все изображения в markdown (абсолютные URL)
      const imgRegex = /!\[([^\]]*)\]\(<?(https?:\/\/[^)>\s]+)>?\)/g;
      const imageMap = new Map<string, string>(); // url → localFilename

      let match: RegExpExecArray | null;
      while ((match = imgRegex.exec(assets.markdown)) !== null) {
        const url = match[2];
        if (!imageMap.has(url)) {
          const filename = url.split('/').pop()?.split('?')[0] || `image_${imageMap.size}.png`;
          imageMap.set(url, filename);
        }
      }

      // Скачать все изображения и добавить в ZIP
      for (const [url, filename] of imageMap) {
        try {
          const res = await fetch(url);
          if (res.ok) {
            const blob = await res.blob();
            imageFolder.file(filename, blob);
            mdContent = mdContent.replaceAll(url, `images/${filename}`);
          }
        } catch {
          console.warn(`Не удалось скачать изображение: ${url}`);
        }
      }

      // Убрать угловые скобки вокруг локальных путей, если были
      mdContent = mdContent.replace(/!\[([^\]]*)\]\(<(images\/[^>]+)>\)/g, '![$1]($2)');

      zip.file('document.md', mdContent);

      const zipBlob = await zip.generateAsync({ type: 'blob' });
      const zipUrl = window.URL.createObjectURL(zipBlob);
      const a = document.createElement('a');
      a.href = zipUrl;
      const safeTitle = (documentTitle || 'document').replace(/[^a-zA-Zа-яА-Я0-9_\- ]/g, '').trim().replace(/\s+/g, '_');
      a.download = `${safeTitle}_${docId}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(zipUrl);
      console.log('Markdown с изображениями экспортирован в ZIP');
    } catch (error: any) {
      console.error('Не удалось создать ZIP-архив:', error?.message || error);
    }
  }, [docId, documentTitle]);

  // Import CSV handler
  const handleImportCSV = useCallback(async (file: File) => {
    if (!requireAuth()) return;
    if (isImportingRef.current) return;
    isImportingRef.current = true;
    try {
      const csvText = await file.text();
      const { annotations: annData, relations: relData } = parseAnnotationsCSV(csvText);

      const total = annData.length;
      setImportProgress({ current: 0, total });

      // Строим карту старый uid → новый uid для корректного создания связей
      const uidMap = new Map<string, string>();
      let createdAnnotations = 0;
      let skippedAnnotations = 0;

      for (let i = 0; i < annData.length; i++) {
        const ann = annData[i];
        const annText = ann.text ?? '';

        // Точное совпадение по тексту аннотации в документе (без fuzzy-окна)
        const idx = annText ? localTextRef.current.indexOf(annText) : -1;
        if (idx === -1) {
          console.warn(`[import] Не найден текст аннотации в документе, пропускаем: "${annText.slice(0, 60)}"`);
          skippedAnnotations++;
          setImportProgress({ current: i + 1, total });
          continue;
        }

        const created = await createAnnotation(docId, {
          text: annText,
          annotation_type: ann.annotation_type ?? '',
          start_offset: idx,
          end_offset: idx + annText.length,
          color: ann.color || '#ffeb3b',
          confidence: ann.confidence,
        });
        if (ann.uid) uidMap.set(ann.uid, created.uid);
        createdAnnotations++;
        setImportProgress({ current: i + 1, total });
      }

      let createdRelations = 0;
      for (const rel of relData) {
        const newSource = uidMap.get(rel.source_uid!) ?? rel.source_uid!;
        const newTarget = uidMap.get(rel.target_uid!) ?? rel.target_uid!;
        await createAnnotationRelation(newSource, {
          target_id: newTarget,
          relation_type: rel.relation_type ?? '',
        });
        createdRelations++;
      }

      console.log(
        `Импорт CSV завершен: создано аннотаций ${createdAnnotations}, пропущено ${skippedAnnotations}, связей ${createdRelations}`
      );

      await loadAnnotations();
      await loadRelations();
    } catch (error: any) {
      console.error('Не удалось импортировать аннотации:', error?.message || error);
    } finally {
      isImportingRef.current = false;
      setImportProgress(null);
    }
  }, [docId, loadAnnotations, loadRelations, requireAuth]);

  // Cursor position handler (called from TextAnnotator on mouseup/keyup)
  const handleCursorMove = useCallback((pos: number) => {
    setCursorPosition(pos);
  }, []);

  // Shift annotations right/left of cursor position
  const handleShift = useCallback((direction: 'left' | 'right') => {
    if (cursorPosition === null) return;
    const delta = direction === 'right' ? 1 : -1;

    setShiftedAnnotations(prev => {
      const base = prev ?? visibleAnnotations;
      const shifted = base.map(ann =>
        ann.start_offset >= cursorPosition
          ? { ...ann, start_offset: Math.max(0, ann.start_offset + delta), end_offset: Math.max(1, ann.end_offset + delta) }
          : ann
      );
      shiftSaveRef.current = shifted;
      return shifted;
    });

    if (shiftDebounceRef.current) clearTimeout(shiftDebounceRef.current);
    shiftDebounceRef.current = setTimeout(async () => {
      const current = shiftSaveRef.current;
      const original = annotationsRef.current;
      const updates = current
        .filter(ann => {
          const orig = original.find(a => a.uid === ann.uid);
          return orig && (orig.start_offset !== ann.start_offset || orig.end_offset !== ann.end_offset);
        })
        .map(ann => ({ annotation_id: ann.uid, start_offset: ann.start_offset, end_offset: ann.end_offset }));
      if (updates.length > 0) {
        try {
          await batchUpdateAnnotationOffsets({ updates });
          await loadAnnotations();
        } catch (error) {
          console.error('Ошибка при сохранении сдвига аннотаций:', error);
        }
      }
      // Сбрасываем preview — теперь отображаем свежие данные из loadAnnotations
      setShiftedAnnotations(null);
    }, 1500);
  }, [cursorPosition, loadAnnotations, visibleAnnotations]);

  // Filter handlers
  const handleResetFilters = useCallback(() => {
    setSelectedCategories([]);
    setSelectedSource(null);
    setHiddenTypes(new Set());
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
            onTypeSelect={setSelectedType}
            onColorChange={setSelectedColor}
            selectedTypes={selectedTypes}
            onTypeToggle={handleTypeToggle}
            hasPendingSelection={!!pendingTextSelection || selectedAnnotationGroup.length > 0}
          />
        </div>

        {/* Main Editor */}
        <div className="workspace-main">
          <ErrorBoundary>
            <EditorTabsWithValidation
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
              onMultiLevelAnnotate={handleMultiLevelAnnotate}
              analysisProgress={analysisProgress}
              onSave={handleSave}
              onDeleteAllAnnotations={handleDeleteAllAnnotations}
              isAutoAnnotating={isAutoAnnotating}
              hasUnsavedChanges={hasUnsavedChanges}
              textareaRef={textareaRef}
              textAnnotatorRef={textAnnotatorRef}
              selectedRelation={selectedRelation}
              onRelationClick={handleRelationClick}
              onRelationDelete={handleRelationDelete}
              onExportCSV={handleExportCSV}
              onImportCSV={handleImportCSV}
              importProgress={importProgress}
              onDownloadMarkdown={handleDownloadMarkdown}
              onSaveForTests={() => setShowSaveForTestsDialog(true)}
              onColorChange={setSelectedColor}
              onRelationModeToggle={() => setRelationMode(!relationMode)}
              onShowRelationsToggle={() => setShowRelations(!showRelations)}
              onLineHeightToggle={() => setLargeLineHeight(!largeLineHeight)}
              filterProps={{
                totalAnnotations,
                selectedCategories,
                selectedSource,
                onCategoriesChange: setSelectedCategories,
                onSourceChange: setSelectedSource,
                onResetFilters: handleResetFilters,
                annotations,
                hiddenTypes,
                onTypeVisibilityToggle: handleTypeVisibilityToggle,
                onShowAllTypes: handleShowAllTypes,
              }}
              onUndo={handleUndo}
              onRedo={handleRedo}
              forceTextVersion={undoRedoVersion}
              onShiftLeft={() => handleShift('left')}
              onShiftRight={() => handleShift('right')}
              hasCursor={cursorPosition !== null}
              onCursorMove={handleCursorMove}
            />
          </ErrorBoundary>
        </div>

        {/* Annotations + Relations stacked vertically */}
        <div className="workspace-side-panels">
          <div className="workspace-annotations-panel">
            <div className="panel-tabs">
              <div style={{ padding: '8px 12px', fontWeight: 'bold', fontSize: '13px', color: '#2196f3' }}>
                Аннотации ({annotations.length}{totalAnnotations > annotations.length ? ` из ${totalAnnotations}` : ''})
              </div>
            </div>
            <ErrorBoundary>
              <AnnotationPanel
                annotations={visibleAnnotations}
                onAnnotationSelect={handleAnnotationSelect}
                onAnnotationDelete={handleAnnotationDelete}
                onAnnotationEdit={handleAnnotationEdit}
                selectedAnnotation={selectedAnnotation}
                cursorPosition={cursorPosition}
              />
            </ErrorBoundary>
          </div>

          <div className="workspace-relations-panel">
            <div className="panel-tabs">
              <div style={{ padding: '8px 12px', fontWeight: 'bold', fontSize: '13px', color: '#2196f3' }}>
                Связи ({relations.length})
              </div>
            </div>
            <ErrorBoundary>
              <RelationsPanel
                relations={relations}
                onRelationDelete={handleRelationDelete}
                onRelationEdit={handleRelationEdit}
              />
            </ErrorBoundary>
          </div>
        </div>
        </div>


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
