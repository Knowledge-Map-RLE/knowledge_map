import { useState, useCallback, useRef, MutableRefObject } from 'react';
import {
  Annotation,
  AnnotationRelation,
  getAnnotationRelations,
  createAnnotationRelation,
  deleteAnnotationRelation,
} from '../../../../services/api';

const enrich = (
  rel: AnnotationRelation,
  annotationsRef: MutableRefObject<Annotation[]>
): AnnotationRelation => {
  const src = annotationsRef.current.find(a => a.uid === rel.source_uid);
  const tgt = annotationsRef.current.find(a => a.uid === rel.target_uid);
  return {
    ...rel,
    source_annotation_type: src?.annotation_type,
    source_text: src?.text,
    target_annotation_type: tgt?.annotation_type,
    target_text: tgt?.text,
  };
};

export const useRelations = (docId: string, annotationsRef: MutableRefObject<Annotation[]>) => {
  const [relations, setRelations] = useState<AnnotationRelation[]>([]);

  const loadRelations = useCallback(async () => {
    try {
      const rels = await getAnnotationRelations(docId);
      setRelations(rels.map(rel => enrich(rel, annotationsRef)));
    } catch (error: any) {
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки связей:', error);
      }
      setRelations([]);
    }
  }, [docId, annotationsRef]);

  const createRelation = useCallback(async (sourceId: string, targetId: string, relationType: string) => {
    const newRelation = await createAnnotationRelation(sourceId, {
      target_id: targetId,
      relation_type: relationType,
    });
    const enriched = enrich(newRelation, annotationsRef);
    setRelations(prev => [...prev, enriched]);
    return enriched;
  }, [annotationsRef]);

  const removeRelation = useCallback(async (sourceId: string, targetId: string) => {
    await deleteAnnotationRelation(sourceId, targetId);
    setRelations(prev => prev.filter(rel => !(rel.source_uid === sourceId && rel.target_uid === targetId)));
  }, []);

  const editRelation = useCallback(async (relation: AnnotationRelation, newType: string) => {
    await deleteAnnotationRelation(relation.source_uid, relation.target_uid);
    const newRelation = await createAnnotationRelation(relation.source_uid, {
      target_id: relation.target_uid,
      relation_type: newType,
    });
    const enriched = enrich(newRelation, annotationsRef);
    setRelations(prev => prev.map(rel =>
      rel.relation_uid === relation.relation_uid ? enriched : rel
    ));
    return enriched;
  }, [annotationsRef]);

  return {
    relations,
    loadRelations,
    createRelation,
    removeRelation,
    editRelation,
  };
};
