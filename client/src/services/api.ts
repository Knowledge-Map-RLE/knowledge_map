/**
 * API клиент для взаимодействия с бэкендом
 * 
 * Этот файл поддерживает обратную совместимость.
 * Новые функции импортируются из src/services/api/
 */

import { httpClient } from './api/httpClient';
import { fetchJson } from './api/http';

export * from './api';
export { httpClient };
export const api = httpClient;
export { fetchJson };

export { edgesByViewport, loadLayout, loadAround, createBlock, deleteBlock, createLink, deleteLink, createBlockAndLink, pinBlock, unpinBlock, pinBlockWithScale, moveBlockToLevel, getNLPMarkdown, getKnowledgeMapPage } from './api/layout';
export { uploadPdfForExtraction, listDocuments, searchPubMed, getByPubMedId, ingestPubMedArticle, getDocumentProgress, getDocumentAssets, deleteDocument, importAnnotations, exportAnnotations, saveMarkdown } from './api/documents';
export { getGlobalLinguisticGraph, getDocumentLinguisticGraph, getDependencyNgrams, getPatternContext, getExtractedPatterns, getExtractStatus, getPatternGraph, getPatternText, savePatternsToDb, createPatternsInDb, getPatternCreateStatus } from './api/graphs';
export { createAnnotation, getAnnotations, updateAnnotation, deleteAnnotation, deleteAllAnnotations, batchUpdateAnnotationOffsets, createAnnotationRelation, deleteAnnotationRelation, getAnnotationRelations } from './api/annotations';
export { analyzeText, autoAnnotateDocument, autoAnnotateMultilevel, getNlpTaskStatus, exportAnnotationsYAML, importAnnotationsYAML } from './api/nlp';
export { checkDataAvailability, saveDocumentForTests, analyzeDocumentPatterns, getDocumentPatterns, getDocumentSpecificPatterns, analyzeDocumentGoals, getDocumentGoals, extractDocumentActions, getPendingEdges, reviewEdge, autoReview, getConfirmedActionGraph, backfillNormKeys } from './api/patterns';
export { buildAnnotationsCSV, parseAnnotationsCSV } from './api/csv';

export type { Link } from '../entities/link';
export type { User } from '../entities/user';