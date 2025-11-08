import { useState, useCallback } from 'react';
import {
  AnnotationRelation,
  getAnnotationRelations,
  createAnnotationRelation,
  deleteAnnotationRelation,
} from '../../../../services/api';

export const useRelations = (docId: string) => {
  const [relations, setRelations] = useState<AnnotationRelation[]>([]);

  const loadRelations = useCallback(async () => {
    try {
      const rels = await getAnnotationRelations(docId);
      setRelations(rels);
    } catch (error: any) {
      if (!error?.message?.includes('404')) {
        console.error('Ошибка загрузки связей:', error);
      }
      setRelations([]);
    }
  }, [docId]);

  const createRelation = useCallback(async (sourceId: string, targetId: string, relationType: string) => {
    const newRelation = await createAnnotationRelation(sourceId, {
      target_id: targetId,
      relation_type: relationType,
    });
    setRelations(prev => [...prev, newRelation]);
    return newRelation;
  }, []);

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
    setRelations(prev => prev.map(rel =>
      rel.relation_uid === relation.relation_uid ? newRelation : rel
    ));
    return newRelation;
  }, []);

  return {
    relations,
    loadRelations,
    createRelation,
    removeRelation,
    editRelation,
  };
};
