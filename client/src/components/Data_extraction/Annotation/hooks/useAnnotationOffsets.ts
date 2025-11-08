import { useState, useCallback, useRef } from 'react';
import { Annotation, batchUpdateAnnotationOffsets, AnnotationOffsetUpdate, deleteAnnotation } from '../../../../services/api';

interface OffsetCalculationResult {
  changeStart: number;
  oldEnd: number;
  newEnd: number;
  delta: number;
}

const findTextChangeRange = (oldText: string, newText: string): OffsetCalculationResult => {
  let changeStart = 0;
  while (changeStart < Math.min(oldText.length, newText.length) && oldText[changeStart] === newText[changeStart]) {
    changeStart++;
  }

  let oldEnd = oldText.length;
  let newEnd = newText.length;
  while (oldEnd > changeStart && newEnd > changeStart && oldText[oldEnd - 1] === newText[newEnd - 1]) {
    oldEnd--;
    newEnd--;
  }

  const delta = (newEnd - changeStart) - (oldEnd - changeStart);

  return { changeStart, oldEnd, newEnd, delta };
};

interface CalculateOffsetsParams {
  annotation: Annotation;
  changeStart: number;
  oldEnd: number;
  newEnd: number;
  delta: number;
}

const calculateNewOffsets = ({ annotation, changeStart, oldEnd, newEnd, delta }: CalculateOffsetsParams) => {
  let newStart = annotation.start_offset;
  let newEnd_offset = annotation.end_offset;
  let shouldDelete = false;

  // Случай 1: Аннотация полностью ДО изменения - не трогаем
  if (annotation.end_offset <= changeStart) {
    // Ничего не делаем
  }
  // Случай 2: Аннотация полностью ПОСЛЕ изменения - сдвигаем на delta
  else if (annotation.start_offset >= oldEnd) {
    newStart = annotation.start_offset + delta;
    newEnd_offset = annotation.end_offset + delta;
  }
  // Случай 3: Аннотация начинается ДО изменения, но заканчивается ВНУТРИ или ПОСЛЕ
  else if (annotation.start_offset < changeStart && annotation.end_offset > changeStart) {
    if (annotation.end_offset <= oldEnd) {
      const newLength = newEnd - changeStart;
      if (newLength === 0) {
        shouldDelete = true;
      } else {
        newEnd_offset = changeStart + Math.max(0, annotation.end_offset - oldEnd) + newLength;
      }
    } else {
      newEnd_offset = annotation.end_offset + delta;
    }
  }
  // Случай 4: Аннотация полностью ВНУТРИ изменения
  else if (annotation.start_offset >= changeStart && annotation.end_offset <= oldEnd) {
    const relativeStart = annotation.start_offset - changeStart;
    const relativeEnd = annotation.end_offset - changeStart;
    const oldLength = oldEnd - changeStart;
    const newLength = newEnd - changeStart;

    if (oldLength > 0 && newLength > 0) {
      const scale = newLength / oldLength;
      newStart = changeStart + Math.floor(relativeStart * scale);
      newEnd_offset = changeStart + Math.ceil(relativeEnd * scale);
    } else if (newLength === 0) {
      shouldDelete = true;
    } else {
      newStart = changeStart;
      newEnd_offset = changeStart + 1;
    }
  }
  // Случай 5: Аннотация начинается ВНУТРИ изменения, но заканчивается ПОСЛЕ
  else if (annotation.start_offset >= changeStart && annotation.start_offset < oldEnd && annotation.end_offset > oldEnd) {
    const newLength = newEnd - changeStart;
    if (newLength === 0) {
      shouldDelete = true;
    } else {
      newStart = newEnd;
      newEnd_offset = annotation.end_offset + delta;
    }
  }

  // Валидация
  newStart = Math.max(0, newStart);
  newEnd_offset = Math.max(newStart + 1, newEnd_offset);

  return { newStart, newEnd: newEnd_offset, shouldDelete };
};

export const useAnnotationOffsets = () => {
  const [annotationsToDelete, setAnnotationsToDelete] = useState<Set<string>>(new Set());
  const [hasUnsavedOffsets, setHasUnsavedOffsets] = useState(false);
  const savedTextRef = useRef<string>('');

  const calculateVisualOffsets = useCallback((oldText: string, newText: string, annotations: Annotation[]): Annotation[] => {
    if (annotations.length === 0 || oldText === newText) return annotations;

    const { changeStart, oldEnd, newEnd, delta } = findTextChangeRange(oldText, newText);
    if (delta === 0) return annotations;

    const newAnnotationsToDelete = new Set(annotationsToDelete);

    const updatedAnnotations = annotations.map((ann) => {
      const { newStart, newEnd, shouldDelete } = calculateNewOffsets({
        annotation: ann,
        changeStart,
        oldEnd,
        newEnd,
        delta
      });

      // Проверяем что текст аннотации не изменился
      if (!shouldDelete && ann.start_offset < oldEnd && ann.end_offset > changeStart) {
        const oldAnnotatedText = oldText.substring(ann.start_offset, ann.end_offset);
        const newAnnotatedText = newText.substring(newStart, newEnd);

        if (oldAnnotatedText !== newAnnotatedText) {
          newAnnotationsToDelete.add(ann.uid);
          console.log(`Аннотация ${ann.uid} помечена для удаления (текст изменился: "${oldAnnotatedText}" -> "${newAnnotatedText}")`);
          return { ...ann, start_offset: newStart, end_offset: newEnd };
        }
      }

      if (shouldDelete) {
        newAnnotationsToDelete.add(ann.uid);
      }

      return { ...ann, start_offset: newStart, end_offset: newEnd };
    });

    setAnnotationsToDelete(newAnnotationsToDelete);
    return updatedAnnotations.filter(ann => !newAnnotationsToDelete.has(ann.uid));
  }, [annotationsToDelete]);

  const saveAnnotationOffsets = useCallback(async (
    currentText: string,
    annotations: Annotation[],
    onReload: () => Promise<void>
  ) => {
    if (!hasUnsavedOffsets && annotationsToDelete.size === 0) {
      console.log('Нет несохраненных изменений offset');
      return;
    }

    try {
      // Удаляем аннотации, помеченные для удаления
      if (annotationsToDelete.size > 0) {
        console.log(`Удаляем ${annotationsToDelete.size} аннотаций из БД (текст был удален)`);
        await Promise.all(
          Array.from(annotationsToDelete).map(uid => deleteAnnotation(uid))
        );
        setAnnotationsToDelete(new Set());
      }

      // Сохраняем offset
      const oldText = savedTextRef.current;
      const newText = currentText;

      if (oldText !== newText && annotations.length > 0) {
        const { changeStart, oldEnd, newEnd, delta } = findTextChangeRange(oldText, newText);

        if (delta !== 0) {
          console.log(`Сохранение offset в БД: changeStart=${changeStart}, oldEnd=${oldEnd}, newEnd=${newEnd}, delta=${delta}`);

          const updates: AnnotationOffsetUpdate[] = [];
          for (const ann of annotations) {
            const { newStart, newEnd } = calculateNewOffsets({
              annotation: ann,
              changeStart,
              oldEnd,
              newEnd,
              delta
            });

            if (newStart !== ann.start_offset || newEnd !== ann.end_offset) {
              updates.push({
                annotation_id: ann.uid,
                start_offset: newStart,
                end_offset: newEnd
              });
            }
          }

          if (updates.length > 0) {
            console.log(`Сохраняем в БД ${updates.length} аннотаций...`);
            const response = await batchUpdateAnnotationOffsets({ updates });
            console.log(`Обновлено в БД ${response.updated_count} аннотаций`);

            if (response.errors.length > 0) {
              console.warn('Ошибки при обновлении:', response.errors);
            }
          }
        }
      }

      setHasUnsavedOffsets(false);
      savedTextRef.current = currentText;
      await onReload();
    } catch (error) {
      console.error('Ошибка сохранения offset и удаления аннотаций:', error);
      throw error;
    }
  }, [hasUnsavedOffsets, annotationsToDelete]);

  const resetUnsavedOffsets = useCallback(() => {
    setHasUnsavedOffsets(false);
    setAnnotationsToDelete(new Set());
  }, []);

  const setSavedText = useCallback((text: string) => {
    savedTextRef.current = text;
  }, []);

  return {
    calculateVisualOffsets,
    saveAnnotationOffsets,
    hasUnsavedOffsets,
    setHasUnsavedOffsets,
    annotationsToDelete,
    resetUnsavedOffsets,
    setSavedText,
  };
};
