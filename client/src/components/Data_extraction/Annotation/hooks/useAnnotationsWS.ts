/**
 * WebSocket-хук для работы с аннотациями.
 * Заменяет useAnnotations (HTTP) на постоянное WS-соединение.
 *
 * Одно соединение на сессию документа. Все операции (load/create/update/delete/batch)
 * идут через WebSocket — меньше накладных расходов, быстрее для больших наборов данных.
 *
 * Интерфейс совместим с useAnnotations — замена без изменения AnnotationWorkspace.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import type { Annotation } from '../../../../services/api';
import { getDefaultColor, ANNOTATION_TYPES } from '../annotationTypes';

interface UseAnnotationsWSOptions {
  docId: string;
  selectedCategories: string[];
  selectedSource: string | null;
}

interface BatchUpdateResult {
  success: boolean;
  updated_count: number;
  errors: string[];
}

interface PendingRequest {
  resolve: (value: any) => void;
  reject: (reason: any) => void;
}

// Строит WebSocket URL из текущего хоста или VITE_API_BASE_URL
function buildWsUrl(docId: string): string {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || '';
  if (base) {
    // Заменяем http(s):// на ws(s)://
    const wsBase = base.replace(/^http/, 'ws').replace(/\/$/, '');
    return `${wsBase}/api/data_extraction/ws/documents/${docId}/annotations`;
  }
  // Используем текущий хост (dev-proxy или prod)
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}/api/data_extraction/ws/documents/${docId}/annotations`;
}

function annotationFromDict(d: any): Annotation {
  const ann: Annotation = {
    uid: d.uid,
    text: d.text,
    annotation_type: d.annotation_type,
    start_offset: d.start_offset,
    end_offset: d.end_offset,
    color: d.color || '#ffeb3b',
    source: d.source || 'user',
  };
  if (d.metadata != null) ann.metadata = d.metadata;
  if (d.confidence != null) ann.confidence = d.confidence;
  if (d.created_date != null) ann.created_date = d.created_date;
  if (d.processor_version != null) ann.processor_version = d.processor_version;
  return ann;
}

export const useAnnotationsWS = ({
  docId,
  selectedCategories,
  selectedSource,
}: UseAnnotationsWSOptions) => {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [annotationsByUid, setAnnotationsByUid] = useState<Map<string, Annotation>>(new Map());
  const [totalAnnotations, setTotalAnnotations] = useState(0);
  const [loading, setLoading] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef<Map<string, PendingRequest>>(new Map());
  const chunksRef = useRef<Annotation[][]>([]);
  // Токен для отмены устаревших загрузок (смена документа / смена фильтров)
  const loadTokenRef = useRef(0);
  // Флаг: хук размонтирован — игнорировать все WS-события и не логировать ошибки
  const destroyedRef = useRef(false);
  // Зеркало annotationsByUid в ref — для O(1) мутаций без пересоздания Map
  const byUidRef = useRef<Map<string, Annotation>>(new Map());

  // Полная замена массива (после загрузки) — O(n) один раз
  const setAnnotationsAll = useCallback((anns: Annotation[]) => {
    const map = new Map<string, Annotation>(anns.map(a => [a.uid, a]));
    byUidRef.current = map;
    setAnnotationsByUid(map);
    setAnnotations(anns);
  }, []);

  // Добавление одной аннотации — O(1) мутация Map
  const addAnnotation = useCallback((ann: Annotation) => {
    byUidRef.current.set(ann.uid, ann);
    setAnnotationsByUid(new Map(byUidRef.current));
    setAnnotations(prev => [...prev, ann]);
  }, []);

  // Замена одной аннотации по uid — O(n) для массива, O(1) для Map
  const replaceAnnotation = useCallback((ann: Annotation) => {
    byUidRef.current.set(ann.uid, ann);
    setAnnotationsByUid(new Map(byUidRef.current));
    setAnnotations(prev => prev.map(a => a.uid === ann.uid ? ann : a));
  }, []);

  // Удаление одной аннотации — O(1) для Map, O(n) для массива (фильтр)
  const dropAnnotation = useCallback((uid: string) => {
    byUidRef.current.delete(uid);
    setAnnotationsByUid(new Map(byUidRef.current));
    setAnnotations(prev => prev.filter(a => a.uid !== uid));
  }, []);

  // Совместимость: полная замена через updater (используется в removeAnnotation)
  const setAnnotationsBoth = useCallback((updater: Annotation[] | ((prev: Annotation[]) => Annotation[])) => {
    setAnnotations(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      const map = new Map<string, Annotation>(next.map(a => [a.uid, a]));
      byUidRef.current = map;
      setAnnotationsByUid(map);
      return next;
    });
  }, []);

  // Закрываем WS при размонтировании или смене docId
  useEffect(() => {
    destroyedRef.current = false;
    return () => {
      destroyedRef.current = true;
      if (wsRef.current) {
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      // Reject все pending-запросы
      for (const { reject } of pendingRef.current.values()) {
        reject(new Error('WebSocket closed'));
      }
      pendingRef.current.clear();
      chunksRef.current = [];
    };
  }, [docId]);

  // Строим фильтр для action "load"
  const buildFilters = useCallback(() => {
    if (selectedCategories.length === 0 && !selectedSource) return {};
    const types: string[] = [];
    selectedCategories.forEach(category => {
      Object.entries(ANNOTATION_TYPES)
        .filter(([, info]) => (info as any).category === category)
        .forEach(([name]) => types.push(name));
    });
    return {
      types: types.length > 0 ? types : undefined,
      source: selectedSource || undefined,
    };
  }, [selectedCategories, selectedSource]);

  // Обработчик входящих WS-сообщений
  const handleMessage = useCallback((token: number, event: MessageEvent) => {
    if (destroyedRef.current) return;
    let msg: any;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    const { event: evtType, request_id } = msg;

    if (evtType === 'annotations_chunk') {
      if (token !== loadTokenRef.current) return; // устаревший ответ
      chunksRef.current.push((msg.annotations as any[]).map(annotationFromDict));
      return;
    }

    if (evtType === 'annotations_done') {
      if (token !== loadTokenRef.current) return;
      // flat() сливает чанки в один массив — O(n) один раз вместо O(n) × chunk_count
      const all = (chunksRef.current.length === 1)
        ? chunksRef.current[0]
        : chunksRef.current.flat();
      chunksRef.current = [];
      setAnnotationsAll(all);
      setTotalAnnotations(msg.total ?? all.length);
      setLoading(false);
      return;
    }

    if (evtType === 'created') {
      const ann = annotationFromDict(msg.annotation);
      addAnnotation(ann);
      pendingRef.current.get(request_id)?.resolve(ann);
      pendingRef.current.delete(request_id);
      return;
    }

    if (evtType === 'updated') {
      const ann = annotationFromDict(msg.annotation);
      replaceAnnotation(ann);
      pendingRef.current.get(request_id)?.resolve(ann);
      pendingRef.current.delete(request_id);
      return;
    }

    if (evtType === 'deleted') {
      const { annotation_id } = msg;
      dropAnnotation(annotation_id);
      pendingRef.current.get(request_id)?.resolve(undefined);
      pendingRef.current.delete(request_id);
      return;
    }

    if (evtType === 'batch_done') {
      const result: BatchUpdateResult = {
        success: (msg.errors ?? []).length === 0,
        updated_count: msg.updated_count ?? 0,
        errors: msg.errors ?? [],
      };
      pendingRef.current.get(request_id)?.resolve(result);
      pendingRef.current.delete(request_id);
      return;
    }

    if (evtType === 'error') {
      const err = new Error(msg.detail || 'WebSocket error');
      (err as any).code = msg.code;
      pendingRef.current.get(request_id)?.reject(err);
      pendingRef.current.delete(request_id);
      if (!request_id) {
        console.error('WS annotation error:', msg);
      }
      return;
    }
  }, [setAnnotationsAll, addAnnotation, replaceAnnotation, dropAnnotation]);

  // Открывает WS и отправляет load-запрос
  const loadAnnotations = useCallback(() => {
    if (destroyedRef.current) return;

    const token = ++loadTokenRef.current;
    setLoading(true);
    chunksRef.current = [];

    const filters = buildFilters();

    const send = (ws: WebSocket) => {
      ws.send(JSON.stringify({ action: 'load', doc_id: docId, filters }));
    };

    // Если соединение уже открыто — сразу шлём
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.onmessage = (ev) => handleMessage(token, ev);
      send(wsRef.current);
      return;
    }

    // Закрываем старое соединение если есть
    if (wsRef.current) {
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = new WebSocket(buildWsUrl(docId));
    wsRef.current = ws;

    ws.onopen = () => {
      if (destroyedRef.current) { ws.close(); return; }
      ws.onmessage = (ev) => handleMessage(token, ev);
      send(ws);
    };

    ws.onerror = () => {
      if (destroyedRef.current) return; // намеренное закрытие — не логируем
      if (token === loadTokenRef.current) {
        console.error('WS annotations connection error');
        setLoading(false);
        chunksRef.current = [];
      }
    };

    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
    };
  }, [docId, buildFilters, handleMessage]);

  // Вспомогательная: отправляет сообщение, возвращает Promise
  const sendRequest = useCallback(<T>(msg: object): Promise<T> => {
    return new Promise<T>((resolve, reject) => {
      const request_id = crypto.randomUUID();
      const fullMsg = { ...msg, request_id };
      pendingRef.current.set(request_id, { resolve, reject });

      const doSend = (ws: WebSocket) => {
        ws.send(JSON.stringify(fullMsg));
      };

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        doSend(wsRef.current);
      } else {
        // WS не открыт — создаём новое соединение
        if (wsRef.current) {
          wsRef.current.onmessage = null;
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.close();
        }
        const ws = new WebSocket(buildWsUrl(docId));
        wsRef.current = ws;
        const token = loadTokenRef.current;
        ws.onopen = () => {
          if (destroyedRef.current) { ws.close(); return; }
          ws.onmessage = (ev) => handleMessage(token, ev);
          doSend(ws);
        };
        ws.onerror = () => {
          if (destroyedRef.current) return;
          pendingRef.current.get(request_id)?.reject(new Error('WS connection error'));
          pendingRef.current.delete(request_id);
        };
        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
        };
      }
    });
  }, [docId, handleMessage]);

  const createNewAnnotation = useCallback(async (
    start: number,
    end: number,
    text: string,
    type: string,
  ): Promise<Annotation> => {
    return sendRequest<Annotation>({
      action: 'create',
      doc_id: docId,
      text,
      annotation_type: type,
      start_offset: start,
      end_offset: end,
      color: getDefaultColor(type),
    });
  }, [docId, sendRequest]);

  const removeAnnotation = useCallback(async (annotationId: string): Promise<void> => {
    // Оптимистичное удаление — O(1) для Map, O(n) для массива
    dropAnnotation(annotationId);
    try {
      await sendRequest<void>({ action: 'delete', annotation_id: annotationId });
    } catch (error) {
      // Откат: перезагружаем аннотации
      loadAnnotations();
      throw error;
    }
  }, [sendRequest, dropAnnotation, loadAnnotations]);

  const editAnnotation = useCallback(async (annotationId: string, annotationType: string): Promise<void> => {
    await sendRequest<Annotation>({ action: 'update', annotation_id: annotationId, annotation_type: annotationType });
  }, [sendRequest]);

  const batchUpdateOffsets = useCallback(async (
    updates: { annotation_id: string; start_offset: number; end_offset: number }[]
  ): Promise<BatchUpdateResult> => {
    return sendRequest<BatchUpdateResult>({ action: 'batch_update_offsets', updates });
  }, [sendRequest]);

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
    batchUpdateOffsets,
  };
};
