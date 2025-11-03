import React, { useState, useEffect, useRef } from 'react';
import TextAnnotator from './TextAnnotator';
import AnnotationToolbar from './AnnotationToolbar';
import AnnotationPanel from './AnnotationPanel';
import RelationsPanel from './RelationsPanel';
import ErrorBoundary from '../../ErrorBoundary';
import {
  Annotation,
  AnnotationRelation,
  createAnnotation,
  getAnnotations,
  updateAnnotation,
  deleteAnnotation,
  createAnnotationRelation,
  getAnnotationRelations,
  deleteAnnotationRelation,
  analyzeText,
  NLPSuggestion,
  batchUpdateAnnotationOffsets,
  AnnotationOffsetUpdate,
} from '../../../services/api';
import { getDefaultColor } from './annotationTypes';
import './AnnotationWorkspace.css';

interface AnnotationWorkspaceProps {
  docId: string;
  text: string;
  readOnly?: boolean;
  onTextChange?: (text: string) => void;
  onSave?: () => Promise<void>; // Callback для кнопки "Сохранить"
}

const AnnotationWorkspace: React.FC<AnnotationWorkspaceProps> = ({
  docId,
  text,
  readOnly = false,
  onTextChange,
  onSave,
}) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [relations, setRelations] = useState<AnnotationRelation[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string>('#ffeb3b');
  const [selectedAnnotation, setSelectedAnnotation] = useState<Annotation | null>(null);
  const [relationMode, setRelationMode] = useState(false);
  const [showRelations, setShowRelations] = useState(false);
  const [loading, setLoading] = useState(false);
  const [nlpSuggestions, setNlpSuggestions] = useState<NLPSuggestion[]>([]);

  // Для мультиклассификации: храним выделенный текст
  const [pendingTextSelection, setPendingTextSelection] = useState<{start: number, end: number, text: string} | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);

  // Для работы с существующими аннотациями: храним группу аннотаций для фрагмента
  const [selectedAnnotationGroup, setSelectedAnnotationGroup] = useState<Annotation[]>([]);

  // Вкладка правой панели: 'annotations' или 'relations'
  const [activeTab, setActiveTab] = useState<'annotations' | 'relations'>('annotations');

  // Вкладка основной области: 'text' или 'annotator'
  const [mainTab, setMainTab] = useState<'text' | 'annotator'>('text');

  // Локальное состояние текста для редактора
  const [localText, setLocalText] = useState(text);

  // Визуальные аннотации с временно скорректированными offset (для отображения во время редактирования)
  const [visualAnnotations, setVisualAnnotations] = useState<Annotation[]>([]);

  // Ref для отслеживания предыдущего текста (для расчёта инкрементальных изменений offset)
  const previousTextRef = useRef(text);

  // Ref для отслеживания последнего СОХРАНЕННОГО состояния текста
  const savedTextRef = useRef(text);

  // Refs для сохранения позиции скролла
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const textAnnotatorRef = useRef<HTMLDivElement>(null);

  // Refs для хранения сохраненных позиций скролла между ре-рендерами
  const savedTextareaScrollTop = useRef<number>(0);
  const savedAnnotatorScrollTop = useRef<number>(0);

  // Флаг наличия несохраненных изменений offset
  const [hasUnsavedOffsets, setHasUnsavedOffsets] = useState(false);

  // Синхронизация с внешним text
  useEffect(() => {
    setLocalText(text);
    previousTextRef.current = text;
    savedTextRef.current = text;
  }, [text]);

  // Загрузка аннотаций при монтировании
  useEffect(() => {
    loadAnnotations();
    loadRelations();
  }, [docId]);

  // Сброс выделенных типов при изменении документа
  useEffect(() => {
    setPendingTextSelection(null);
    setSelectedTypes([]);
    setHasUnsavedOffsets(false);
    setAnnotationsToDelete(new Set());
  }, [docId]);

  // Синхронизация visualAnnotations с annotations (когда аннотации загружены с сервера)
  useEffect(() => {
    setVisualAnnotations(annotations);
  }, [annotations]);

  // Восстанавливаем позиции скролла после изменения visualAnnotations
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

  // State для хранения аннотаций, помеченных для удаления
  const [annotationsToDelete, setAnnotationsToDelete] = useState<Set<string>>(new Set());

  // Функция для мгновенного расчета визуальных offset (без сохранения в БД)
  const calculateVisualOffsets = (oldText: string, newText: string, anns: Annotation[]): Annotation[] => {
    if (anns.length === 0) return anns;
    if (oldText === newText) return anns;

    // Находим первую позицию изменения (с начала)
    let changeStart = 0;
    while (changeStart < Math.min(oldText.length, newText.length) && oldText[changeStart] === newText[changeStart]) {
      changeStart++;
    }

    // Находим последнюю позицию изменения (с конца)
    let oldEnd = oldText.length;
    let newEnd = newText.length;
    while (oldEnd > changeStart && newEnd > changeStart && oldText[oldEnd - 1] === newText[newEnd - 1]) {
      oldEnd--;
      newEnd--;
    }

    // Дельта изменения длины
    const delta = (newEnd - changeStart) - (oldEnd - changeStart);
    if (delta === 0) return anns;

    const newAnnotationsToDelete = new Set(annotationsToDelete);

    // Создаем новые аннотации с скорректированными offset
    const updatedAnns = anns.map((ann) => {
      let newStart = ann.start_offset;
      let newEnd = ann.end_offset;
      let shouldDelete = false;

      // Случай 1: Аннотация полностью ДО изменения - не трогаем
      if (ann.end_offset <= changeStart) {
        // Ничего не делаем
      }
      // Случай 2: Аннотация полностью ПОСЛЕ изменения - сдвигаем на delta
      else if (ann.start_offset >= oldEnd) {
        newStart = ann.start_offset + delta;
        newEnd = ann.end_offset + delta;
      }
      // Случай 3: Аннотация начинается ДО изменения, но заканчивается ВНУТРИ или ПОСЛЕ
      else if (ann.start_offset < changeStart && ann.end_offset > changeStart) {
        if (ann.end_offset <= oldEnd) {
          // Конец аннотации внутри изменения
          const newLength = newEnd - changeStart;
          if (newLength === 0) {
            // Весь аннотированный текст удален
            shouldDelete = true;
          } else {
            newEnd = changeStart + Math.max(0, ann.end_offset - oldEnd) + newLength;
          }
        } else {
          // Конец аннотации после изменения - сдвигаем конец
          newEnd = ann.end_offset + delta;
        }
      }
      // Случай 4: Аннотация полностью ВНУТРИ изменения
      else if (ann.start_offset >= changeStart && ann.end_offset <= oldEnd) {
        const relativeStart = ann.start_offset - changeStart;
        const relativeEnd = ann.end_offset - changeStart;
        const oldLength = oldEnd - changeStart;
        const newLength = newEnd - changeStart;

        if (oldLength > 0 && newLength > 0) {
          // Пропорциональное масштабирование
          const scale = newLength / oldLength;
          newStart = changeStart + Math.floor(relativeStart * scale);
          newEnd = changeStart + Math.ceil(relativeEnd * scale);
        } else if (newLength === 0) {
          // Весь измененный участок удален - аннотация тоже удаляется
          shouldDelete = true;
        } else {
          // oldLength === 0, т.е. вставка
          newStart = changeStart;
          newEnd = changeStart + 1;
        }
      }
      // Случай 5: Аннотация начинается ВНУТРИ изменения, но заканчивается ПОСЛЕ
      else if (ann.start_offset >= changeStart && ann.start_offset < oldEnd && ann.end_offset > oldEnd) {
        const newLength = newEnd - changeStart;
        if (newLength === 0) {
          // Начало аннотации было удалено
          shouldDelete = true;
        } else {
          newStart = newEnd;
          newEnd = ann.end_offset + delta;
        }
      }

      // Валидация
      newStart = Math.max(0, newStart);
      newEnd = Math.max(newStart + 1, newEnd);

      // ВАЖНАЯ ПРОВЕРКА: если аннотация пересекается с изменением,
      // проверяем что текст аннотации не изменился
      if (!shouldDelete && ann.start_offset < oldEnd && ann.end_offset > changeStart) {
        // Аннотация пересекается с измененным участком
        const oldAnnotatedText = oldText.substring(ann.start_offset, ann.end_offset);
        const newAnnotatedText = newText.substring(newStart, newEnd);

        if (oldAnnotatedText !== newAnnotatedText) {
          // Текст аннотации изменился - удаляем аннотацию
          shouldDelete = true;
          console.log(`Аннотация ${ann.uid} помечена для удаления (текст изменился: "${oldAnnotatedText}" -> "${newAnnotatedText}")`);
        }
      }

      if (shouldDelete) {
        newAnnotationsToDelete.add(ann.uid);
      }

      return { ...ann, start_offset: newStart, end_offset: newEnd };
    });

    // Обновляем список аннотаций для удаления
    setAnnotationsToDelete(newAnnotationsToDelete);

    // Фильтруем аннотации, помеченные для удаления
    return updatedAnns.filter(ann => !newAnnotationsToDelete.has(ann.uid));
  };

  const loadAnnotations = async () => {
    try {
      setLoading(true);
      const anns = await getAnnotations(docId);
      setAnnotations(anns);
    } catch (error: any) {
      // Игнорируем 404 - документ может еще не быть в Neo4j
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки аннотаций:', error);
      }
      setAnnotations([]);
    } finally {
      setLoading(false);
    }
  };

  const loadRelations = async () => {
    try {
      const rels = await getAnnotationRelations(docId);
      setRelations(rels);
    } catch (error: any) {
      // Игнорируем 404 - документ может еще не быть в Neo4j
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки связей:', error);
      }
      setRelations([]);
    }
  };

  // Публичная функция для сохранения offset аннотаций в БД (вызывается по кнопке "Сохранить")
  const saveAnnotationOffsets = async () => {
    if (!hasUnsavedOffsets && annotationsToDelete.size === 0) {
      console.log('Нет несохраненных изменений offset');
      return;
    }

    try {
      // Сохраняем текущую позицию скролла ОБЕИХ вкладок перед перезагрузкой
      savedTextareaScrollTop.current = textareaRef.current?.scrollTop || 0;
      savedAnnotatorScrollTop.current = textAnnotatorRef.current?.scrollTop || 0;

      // Сначала удаляем аннотации, помеченные для удаления
      if (annotationsToDelete.size > 0) {
        console.log(`Удаляем ${annotationsToDelete.size} аннотаций из БД (текст был удален)`);
        await Promise.all(
          Array.from(annotationsToDelete).map(uid => deleteAnnotation(uid))
        );
        setAnnotationsToDelete(new Set());
      }

      // Затем сохраняем offset рассчитанные от ПОСЛЕДНЕГО СОХРАНЕННОГО состояния до ТЕКУЩЕГО
      const oldText = savedTextRef.current;
      const newText = localText;

      if (oldText !== newText) {
        await saveOffsetsToDatabase(oldText, newText);
      }

      setHasUnsavedOffsets(false);

      // Обновляем savedTextRef после успешного сохранения
      savedTextRef.current = newText;

      // Перезагружаем аннотации для синхронизации
      await loadAnnotations();

      // Восстанавливаем позицию скролла после ре-рендера
      // Используем несколько requestAnimationFrame для надежности
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
      console.error('Ошибка сохранения offset и удаления аннотаций:', error);
      throw error;
    }
  };

  // Внутренняя функция для сохранения offset в БД
  const saveOffsetsToDatabase = async (oldText: string, newText: string) => {
    if (annotations.length === 0) return;
    if (oldText === newText) return;

    // Находим первую позицию изменения (с начала)
    let changeStart = 0;
    while (changeStart < Math.min(oldText.length, newText.length) && oldText[changeStart] === newText[changeStart]) {
      changeStart++;
    }

    // Находим последнюю позицию изменения (с конца)
    let oldEnd = oldText.length;
    let newEnd = newText.length;
    while (oldEnd > changeStart && newEnd > changeStart && oldText[oldEnd - 1] === newText[newEnd - 1]) {
      oldEnd--;
      newEnd--;
    }

    // Дельта изменения длины
    const delta = (newEnd - changeStart) - (oldEnd - changeStart);

    if (delta === 0) return; // Нет изменения длины

    console.log(`Сохранение offset в БД: changeStart=${changeStart}, oldEnd=${oldEnd}, newEnd=${newEnd}, delta=${delta}`);

    // Рассчитываем новые offset для всех аннотаций
    const updates: AnnotationOffsetUpdate[] = [];
    for (const ann of annotations) {
      let newStart = ann.start_offset;
      let newEnd = ann.end_offset;

      // Случай 1: Аннотация полностью ДО изменения - не трогаем
      if (ann.end_offset <= changeStart) {
        // Ничего не делаем
      }
      // Случай 2: Аннотация полностью ПОСЛЕ изменения - сдвигаем на delta
      else if (ann.start_offset >= oldEnd) {
        newStart = ann.start_offset + delta;
        newEnd = ann.end_offset + delta;
      }
      // Случай 3: Аннотация начинается ДО изменения, но заканчивается ВНУТРИ или ПОСЛЕ
      else if (ann.start_offset < changeStart && ann.end_offset > changeStart) {
        // Аннотация перекрывает начало изменения
        if (ann.end_offset <= oldEnd) {
          // Конец аннотации внутри изменения
          newEnd = changeStart + Math.max(0, ann.end_offset - oldEnd) + (newEnd - changeStart);
        } else {
          // Конец аннотации после изменения - сдвигаем конец
          newEnd = ann.end_offset + delta;
        }
      }
      // Случай 4: Аннотация полностью ВНУТРИ изменения
      else if (ann.start_offset >= changeStart && ann.end_offset <= oldEnd) {
        // Аннотация внутри изменяемого участка
        const relativeStart = ann.start_offset - changeStart;
        const relativeEnd = ann.end_offset - changeStart;
        const oldLength = oldEnd - changeStart;
        const newLength = newEnd - changeStart;

        if (oldLength > 0 && newLength > 0) {
          // Пропорциональное масштабирование
          const scale = newLength / oldLength;
          newStart = changeStart + Math.floor(relativeStart * scale);
          newEnd = changeStart + Math.ceil(relativeEnd * scale);
        } else if (newLength === 0) {
          // Текст удалён
          newStart = changeStart;
          newEnd = changeStart + 1;
        } else {
          // oldLength === 0, т.е. вставка
          newStart = changeStart;
          newEnd = changeStart + 1;
        }
      }
      // Случай 5: Аннотация начинается ВНУТРИ изменения, но заканчивается ПОСЛЕ
      else if (ann.start_offset >= changeStart && ann.start_offset < oldEnd && ann.end_offset > oldEnd) {
        // Начало внутри, конец после
        newStart = newEnd;
        newEnd = ann.end_offset + delta;
      }

      // Валидация: не допускаем отрицательных offset и end <= start
      newStart = Math.max(0, newStart);
      newEnd = Math.max(newStart + 1, newEnd);

      // Если offset изменились, добавляем в список обновлений
      if (newStart !== ann.start_offset || newEnd !== ann.end_offset) {
        updates.push({
          annotation_id: ann.uid,
          start_offset: newStart,
          end_offset: newEnd
        });
      }
    }

    if (updates.length === 0) {
      console.log('Нет аннотаций для обновления в БД');
      return;
    }

    console.log(`Сохраняем в БД ${updates.length} аннотаций...`);

    try {
      const response = await batchUpdateAnnotationOffsets({ updates });
      console.log(`Обновлено в БД ${response.updated_count} аннотаций`);

      if (response.errors.length > 0) {
        console.warn('Ошибки при обновлении:', response.errors);
      }

      // Перезагружаем аннотации для синхронизации
      await loadAnnotations();
    } catch (error) {
      console.error('Ошибка массового обновления offset:', error);
    }
  };

  // Обработка выделения текста - сохраняем выделенный текст для последующего назначения классов
  const handleTextSelect = (start: number, end: number, selectedText: string) => {
    if (readOnly) return;

    // Сохраняем выделенный текст и сбрасываем список выбранных типов
    setPendingTextSelection({ start, end, text: selectedText });
    setSelectedTypes([]);
  };

  // Обработчик переключения типа в toolbar (для мультиклассификации)
  const handleTypeToggle = async (type: string) => {
    // Если есть выделенный новый текст - мгновенно создаём/удаляем аннотацию
    if (pendingTextSelection) {
      const { start, end, text } = pendingTextSelection;

      // Проверяем, есть ли уже аннотация с таким типом для этого фрагмента
      const existingAnnotation = annotations.find(
        (ann) =>
          ann.start_offset === start &&
          ann.end_offset === end &&
          ann.annotation_type === type
      );

      if (existingAnnotation) {
        // Удаляем существующую аннотацию
        await handleAnnotationDelete(existingAnnotation.uid);
        setSelectedTypes((prev) => prev.filter((t) => t !== type));
      } else {
        // Создаём новую аннотацию
        try {
          const newAnnotation = await createAnnotation(docId, {
            text,
            annotation_type: type,
            start_offset: start,
            end_offset: end,
            color: getDefaultColor(type),
          });
          setAnnotations([...annotations, newAnnotation]);
          setSelectedTypes((prev) => [...prev, type]);
        } catch (error: any) {
          console.error('Ошибка создания аннотации:', error);
          if (error?.message?.includes('404')) {
            alert('Документ не найден в базе данных. Аннотации пока недоступны для этого документа.');
          } else {
            alert('Не удалось создать аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
          }
        }
      }
      return;
    }

    // Если выбрана существующая группа аннотаций - мгновенно добавляем/удаляем тип
    if (selectedAnnotationGroup.length > 0) {
      const fragment = selectedAnnotationGroup[0];
      const existingTypes = selectedAnnotationGroup.map((ann) => ann.annotation_type);

      if (existingTypes.includes(type)) {
        // Удаляем тип
        const annToDelete = selectedAnnotationGroup.find((ann) => ann.annotation_type === type);
        if (annToDelete) {
          await handleAnnotationDelete(annToDelete.uid);
        }
      } else {
        // Добавляем тип
        try {
          const newAnnotation = await createAnnotation(docId, {
            text: fragment.text,
            annotation_type: type,
            start_offset: fragment.start_offset,
            end_offset: fragment.end_offset,
            color: getDefaultColor(type),
          });

          // Перезагружаем аннотации с сервера для гарантированной синхронизации
          await loadAnnotations();

          // Обновляем выбранную группу - добавляем новую аннотацию
          setSelectedAnnotationGroup([...selectedAnnotationGroup, newAnnotation]);
        } catch (error: any) {
          console.error('Ошибка создания аннотации:', error);
          alert('Не удалось создать аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
        }
      }
    }
  };

  // Создание мультиклассовой аннотации
  const createMultiClassAnnotation = async () => {
    if (!pendingTextSelection || selectedTypes.length === 0) {
      alert('Выберите хотя бы один тип аннотации');
      return;
    }

    const { start, end, text } = pendingTextSelection;

    try {
      // Создаем аннотацию для каждого выбранного типа
      await Promise.all(
        selectedTypes.map((type) =>
          createAnnotation(docId, {
            text,
            annotation_type: type,
            start_offset: start,
            end_offset: end,
            color: getDefaultColor(type),
          })
        )
      );

      // Перезагружаем аннотации с сервера для гарантированной синхронизации
      await loadAnnotations();

      // Сбрасываем состояние после создания
      setPendingTextSelection(null);
      setSelectedTypes([]);
    } catch (error: any) {
      console.error('Ошибка создания аннотации:', error);
      if (error?.message?.includes('404')) {
        alert('Документ не найден в базе данных. Аннотации пока недоступны для этого документа.');
      } else {
        alert('Не удалось создать аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
      }
    }
  };

  const createNewAnnotation = async (
    start: number,
    end: number,
    selectedText: string,
    type: string,
    color: string
  ) => {
    try {
      const newAnnotation = await createAnnotation(docId, {
        text: selectedText,
        annotation_type: type,
        start_offset: start,
        end_offset: end,
        color: color,
      });
      setAnnotations([...annotations, newAnnotation]);
    } catch (error: any) {
      console.error('Ошибка создания аннотации:', error);
      if (error?.message?.includes('404')) {
        alert('Документ не найден в базе данных. Аннотации пока недоступны для этого документа.');
      } else {
        alert('Не удалось создать аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
      }
    }
  };

  // Обработчик выбора аннотации (или группы аннотаций)
  const handleAnnotationSelect = (annotation: Annotation | Annotation[]) => {
    if (Array.isArray(annotation)) {
      // Выбрана группа аннотаций
      setSelectedAnnotationGroup(annotation);
      setSelectedAnnotation(annotation[0] || null);
      // Сбрасываем pendingTextSelection и показываем типы в toolbar
      setPendingTextSelection(null);
      setSelectedTypes(annotation.map((ann) => ann.annotation_type));
    } else {
      // Выбрана одна аннотация - ищем ВСЕ аннотации с ТОЧНО такими же границами
      const group = annotations.filter(
        (ann) => ann.start_offset === annotation.start_offset && ann.end_offset === annotation.end_offset
      );
      setSelectedAnnotationGroup(group);
      setSelectedAnnotation(annotation);
      setPendingTextSelection(null);
      setSelectedTypes(group.map((ann) => ann.annotation_type));
    }
  };

  // Обработка удаления аннотации
  const handleAnnotationDelete = async (annotationId: string) => {
    try {
      await deleteAnnotation(annotationId);

      // Перезагружаем аннотации с сервера для гарантированной синхронизации
      await loadAnnotations();

      // Обновляем выбранную группу - удаляем из неё удалённую аннотацию
      const newGroup = selectedAnnotationGroup.filter((ann) => ann.uid !== annotationId);
      setSelectedAnnotationGroup(newGroup);

      if (newGroup.length === 0) {
        setSelectedAnnotation(null);
        setSelectedTypes([]);
      } else {
        setSelectedTypes(newGroup.map((ann) => ann.annotation_type));
      }
    } catch (error: any) {
      console.error('Ошибка удаления аннотации:', error);
      alert('Не удалось удалить аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
    }
  };

  // Обработка редактирования аннотации
  const handleAnnotationEdit = async (annotation: Annotation) => {
    const newType = prompt('Введите новый тип аннотации:', annotation.annotation_type);
    if (!newType) return;

    try {
      await updateAnnotation(annotation.uid, {
        annotation_type: newType,
      });

      // Перезагружаем аннотации с сервера для гарантированной синхронизации
      await loadAnnotations();
    } catch (error: any) {
      console.error('Ошибка обновления аннотации:', error);
      alert('Не удалось обновить аннотацию: ' + (error?.message || 'Неизвестная ошибка'));
    }
  };

  // Создание связи между аннотациями
  const handleRelationCreate = async (sourceId: string, targetId: string) => {
    const relationType = prompt('Введите тип связи:');
    if (!relationType) return;

    try {
      const newRelation = await createAnnotationRelation(sourceId, {
        target_id: targetId,
        relation_type: relationType,
      });
      setRelations([...relations, newRelation]);
      alert('Связь успешно создана!');
    } catch (error: any) {
      console.error('Ошибка создания связи:', error);
      if (error?.message?.includes('404')) {
        alert('Документ не найден в базе данных. Связи пока недоступны для этого документа.');
      } else {
        alert('Не удалось создать связь: ' + (error?.message || 'Неизвестная ошибка'));
      }
    }
  };

  // Удаление связи
  const handleRelationDelete = async (sourceId: string, targetId: string) => {
    try {
      await deleteAnnotationRelation(sourceId, targetId);
      setRelations(relations.filter(rel => !(rel.source_uid === sourceId && rel.target_uid === targetId)));
    } catch (error: any) {
      console.error('Ошибка удаления связи:', error);
      alert('Не удалось удалить связь: ' + (error?.message || 'Неизвестная ошибка'));
    }
  };

  // Редактирование связи (изменение типа)
  const handleRelationEdit = async (relation: AnnotationRelation) => {
    const newType = prompt('Введите новый тип связи:', relation.relation_type);
    if (!newType || newType === relation.relation_type) return;

    try {
      // Удаляем старую связь и создаём новую с новым типом
      await deleteAnnotationRelation(relation.source_uid, relation.target_uid);
      const newRelation = await createAnnotationRelation(relation.source_uid, {
        target_id: relation.target_uid,
        relation_type: newType,
      });
      setRelations(relations.map(rel =>
        rel.relation_uid === relation.relation_uid ? newRelation : rel
      ));
      alert('Тип связи успешно изменён!');
    } catch (error: any) {
      console.error('Ошибка редактирования связи:', error);
      alert('Не удалось изменить тип связи: ' + (error?.message || 'Неизвестная ошибка'));
    }
  };

  if (loading) {
    return <div className="loading-state">Загрузка аннотаций...</div>;
  }

  return (
    <ErrorBoundary>
      <div className="annotation-workspace">
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
            selectedTypes={selectedTypes}
            onTypeToggle={handleTypeToggle}
            hasPendingSelection={!!pendingTextSelection || selectedAnnotationGroup.length > 0}
          />
        </div>

        <div className="workspace-main">
          <div className="main-tabs">
            <button
              className={`tab-button ${mainTab === 'text' ? 'active' : ''}`}
              onClick={() => setMainTab('text')}
            >
              Редактор текста
            </button>
            <button
              className={`tab-button ${mainTab === 'annotator' ? 'active' : ''}`}
              onClick={() => setMainTab('annotator')}
            >
              Аннотатор
            </button>
            <div style={{ flex: 1 }}></div>
            <button
              className="save-button"
              onClick={async () => {
                try {
                  // Сначала вызываем сохранение offset аннотаций
                  await saveAnnotationOffsets();
                  // Затем вызываем родительский обработчик для сохранения текста
                  if (onSave) {
                    await onSave();
                  }
                } catch (error) {
                  console.error('Ошибка сохранения:', error);
                  alert('Не удалось сохранить изменения');
                }
              }}
              disabled={!hasUnsavedOffsets && annotationsToDelete.size === 0 && !onSave}
            >
              {(hasUnsavedOffsets || annotationsToDelete.size > 0) ? '💾 Сохранить *' : '💾 Сохранить'}
            </button>
          </div>

          <div className="main-content">
            <ErrorBoundary>
              <textarea
                ref={textareaRef}
                className="text-editor"
                value={localText}
                onChange={(e) => {
                  const newText = e.target.value;
                  const oldText = previousTextRef.current;

                  setLocalText(newText);
                  if (onTextChange) {
                    onTextChange(newText);
                  }

                  // МГНОВЕННО пересчитываем визуальные offset для корректного отображения
                  // ВАЖНО: пересчитываем от ТЕКУЩИХ visualAnnotations, а не от исходных annotations
                  if (oldText !== newText && visualAnnotations.length > 0) {
                    const updatedVisualAnnotations = calculateVisualOffsets(oldText, newText, visualAnnotations);
                    setVisualAnnotations(updatedVisualAnnotations);
                    setHasUnsavedOffsets(true); // Отмечаем, что есть несохраненные изменения
                  }

                  // Обновляем previousTextRef для следующего изменения
                  previousTextRef.current = newText;
                }}
                readOnly={readOnly}
                placeholder="Введите текст markdown..."
                style={{ display: mainTab === 'text' ? 'block' : 'none' }}
              />
              <div style={{ display: mainTab === 'annotator' ? 'block' : 'none', width: '100%', height: '100%' }}>
                <TextAnnotator
                  ref={textAnnotatorRef}
                  text={localText}
                  annotations={visualAnnotations}
                  relations={relations}
                  selectedAnnotationType={selectedType}
                  selectedColor={selectedColor}
                  onTextSelect={handleTextSelect}
                  onAnnotationClick={handleAnnotationSelect}
                  onAnnotationHover={() => {}}
                  relationMode={relationMode}
                  onRelationCreate={handleRelationCreate}
                  showRelations={showRelations}
                  editable={!readOnly}
                />
              </div>
            </ErrorBoundary>
          </div>
        </div>

        <div className="workspace-panel">
          <div className="panel-tabs">
            <button
              className={`tab-button ${activeTab === 'annotations' ? 'active' : ''}`}
              onClick={() => setActiveTab('annotations')}
            >
              Аннотации ({annotations.length})
            </button>
            <button
              className={`tab-button ${activeTab === 'relations' ? 'active' : ''}`}
              onClick={() => setActiveTab('relations')}
            >
              Связи ({relations.length})
            </button>
          </div>

          <ErrorBoundary>
            {activeTab === 'annotations' ? (
              <AnnotationPanel
                annotations={annotations}
                onAnnotationSelect={handleAnnotationSelect}
                onAnnotationDelete={handleAnnotationDelete}
                onAnnotationEdit={handleAnnotationEdit}
                selectedAnnotation={selectedAnnotation}
              />
            ) : (
              <RelationsPanel
                relations={relations}
                annotations={annotations}
                onRelationDelete={handleRelationDelete}
                onRelationEdit={handleRelationEdit}
              />
            )}
          </ErrorBoundary>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default AnnotationWorkspace;
