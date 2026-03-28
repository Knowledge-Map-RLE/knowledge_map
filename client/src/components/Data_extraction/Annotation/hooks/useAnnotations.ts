import { useState, useCallback, useRef } from 'react';
import {
  Annotation,
  createAnnotation,
  getAnnotations,
  deleteAnnotation,
  updateAnnotation,
} from '../../../../services/api';
import { getDefaultColor, ANNOTATION_TYPES } from '../annotationTypes';

interface UseAnnotationsOptions {
  docId: string;
  selectedCategories: string[];
  selectedSource: string | null;
}

export const useAnnotations = ({
  docId,
  selectedCategories,
  selectedSource,
}: UseAnnotationsOptions) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [annotationsByUid, setAnnotationsByUid] = useState<Map<string, Annotation>>(new Map());
  const [totalAnnotations, setTotalAnnotations] = useState(0);
  const [loading, setLoading] = useState(false);
  // Токен для отмены устаревших запросов
  const loadTokenRef = useRef(0);

  // Вспомогательная функция: синхронно обновляет и массив и Map
  const setAnnotationsBoth = useCallback((updater: Annotation[] | ((prev: Annotation[]) => Annotation[])) => {
    setAnnotations(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      setAnnotationsByUid(new Map(next.map(a => [a.uid, a])));
      return next;
    });
  }, []);

  const getTypesFilter = useCallback(() => {
    if (selectedCategories.length === 0) return null;

    const typesFilter: string[] = [];
    selectedCategories.forEach(category => {
      const types = Object.entries(ANNOTATION_TYPES)
        .filter(([_, typeInfo]) => typeInfo.category === category)
        .map(([typeName, _]) => typeName);
      typesFilter.push(...types);
    });
    return typesFilter;
  }, [selectedCategories]);

  const loadAnnotations = useCallback(async () => {
    const token = ++loadTokenRef.current;
    try {
      setLoading(true);
      const typesFilter = getTypesFilter();

      const response = await getAnnotations(
        docId,
        0,
        null,
        typesFilter,
        selectedSource
      );

      // Игнорируем ответ если успели запустить новый запрос
      if (token !== loadTokenRef.current) return;

      setAnnotationsBoth(response.annotations);
      setTotalAnnotations(response.total);
    } catch (error: any) {
      if (token !== loadTokenRef.current) return;
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки аннотаций:', error);
      }
      setAnnotationsBoth([]);
      setTotalAnnotations(0);
    } finally {
      if (token === loadTokenRef.current) setLoading(false);
    }
  }, [docId, selectedCategories, selectedSource, getTypesFilter, setAnnotationsBoth]);

  const createNewAnnotation = useCallback(async (
    start: number,
    end: number,
    text: string,
    type: string
  ): Promise<Annotation> => {
    const newAnnotation = await createAnnotation(docId, {
      text,
      annotation_type: type,
      start_offset: start,
      end_offset: end,
      color: getDefaultColor(type),
    });
    setAnnotationsBoth(prev => [...prev, newAnnotation]);
    return newAnnotation;
  }, [docId, setAnnotationsBoth]);

  const removeAnnotation = useCallback(async (annotationId: string) => {
    setAnnotationsBoth(prev => prev.filter(a => a.uid !== annotationId));
    try {
      await deleteAnnotation(annotationId);
    } catch (error) {
      await loadAnnotations(); // откат при ошибке
      throw error;
    }
  }, [loadAnnotations, setAnnotationsBoth]);

  const editAnnotation = useCallback(async (annotationId: string, annotationType: string) => {
    await updateAnnotation(annotationId, { annotation_type: annotationType });
    await loadAnnotations();
  }, [loadAnnotations]);

  return {
    annotations,
    annotationsByUid,
    setAnnotations: setAnnotationsBoth,
    totalAnnotations,
    loading,
    loadAnnotations,
    createNewAnnotation,
    removeAnnotation,
    editAnnotation,
  };
};
