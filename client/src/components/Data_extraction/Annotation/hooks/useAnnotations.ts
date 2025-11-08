import { useState, useCallback } from 'react';
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
  annotationsLimit: number;
}

export const useAnnotations = ({
  docId,
  selectedCategories,
  selectedSource,
  annotationsLimit,
}: UseAnnotationsOptions) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [totalAnnotations, setTotalAnnotations] = useState(0);
  const [loadedAnnotationsCount, setLoadedAnnotationsCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

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
    try {
      setLoading(true);
      const typesFilter = getTypesFilter();

      const response = await getAnnotations(
        docId,
        0,
        annotationsLimit,
        typesFilter,
        selectedSource
      );

      setAnnotations(response.annotations);
      setTotalAnnotations(response.total);
      setLoadedAnnotationsCount(response.annotations.length);

      if (response.total > annotationsLimit && selectedCategories.length === 0 && selectedSource === null) {
        console.warn(
          `Загружено ${response.annotations.length} из ${response.total} аннотаций. ` +
          `Нажмите "Загрузить еще" для загрузки следующих аннотаций или используйте фильтры.`
        );
      }
    } catch (error: any) {
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки аннотаций:', error);
      }
      setAnnotations([]);
      setTotalAnnotations(0);
      setLoadedAnnotationsCount(0);
    } finally {
      setLoading(false);
    }
  }, [docId, selectedCategories, selectedSource, annotationsLimit, getTypesFilter]);

  const loadMoreAnnotations = useCallback(async () => {
    if (isLoadingMore || loadedAnnotationsCount >= totalAnnotations) return;

    try {
      setIsLoadingMore(true);
      const typesFilter = getTypesFilter();

      const response = await getAnnotations(
        docId,
        loadedAnnotationsCount,
        annotationsLimit,
        typesFilter,
        selectedSource
      );

      setAnnotations(prevAnnotations => [...prevAnnotations, ...response.annotations]);
      setLoadedAnnotationsCount(prevCount => prevCount + response.annotations.length);

      console.log(`Загружено еще ${response.annotations.length} аннотаций (всего: ${loadedAnnotationsCount + response.annotations.length} из ${totalAnnotations})`);
    } catch (error: any) {
      console.error('Ошибка загрузки дополнительных аннотаций:', error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [docId, loadedAnnotationsCount, totalAnnotations, annotationsLimit, selectedSource, getTypesFilter, isLoadingMore]);

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
    setAnnotations(prev => [...prev, newAnnotation]);
    return newAnnotation;
  }, [docId]);

  const removeAnnotation = useCallback(async (annotationId: string) => {
    await deleteAnnotation(annotationId);
    await loadAnnotations();
  }, [loadAnnotations]);

  const editAnnotation = useCallback(async (annotationId: string, annotationType: string) => {
    await updateAnnotation(annotationId, { annotation_type: annotationType });
    await loadAnnotations();
  }, [loadAnnotations]);

  return {
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
  };
};
