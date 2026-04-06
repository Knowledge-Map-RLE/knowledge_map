import { useState, useCallback, useMemo, useRef } from 'react';

export interface ActionNode {
  id: string;
  content: string;
  verb: string;
  verb_text: string;
  subject: string;
  object: string;
  action_class: 'action' | 'result' | 'mechanism';
  norm_key: string;
  doc_count: number;
  doc_ids: string[];
  x: number;
  y: number;
}

export interface ActionEdge {
  id: string;
  source_id: string;
  target_id: string;
  count: number;
  confidence: number;
  relation_subtype: string;
}

export function useKnowledgeMapLoader(viewportRef?: any) {
  const [nodes, setNodes] = useState<ActionNode[]>([]);
  const [edges, setEdges] = useState<ActionEdge[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isBootLoading, setIsBootLoading] = useState(true);
  const isLoadingRef = useRef(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageOffset, setPageOffset] = useState(0);
  const pageLimit = 15000;

  const nodeMap = useMemo(() => {
    const map = new Map<string, ActionNode>();
    nodes.forEach(n => map.set(n.id, n));
    return map;
  }, [nodes]);

  const centerViewport = useCallback((newNodes: ActionNode[]) => {
    if (viewportRef?.current && newNodes.length > 0) {
      const xs = newNodes.map(n => n.x);
      const ys = newNodes.map(n => n.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      setTimeout(() => {
        if (!viewportRef.current) return;
        const padding = 400;
        const fitX = window.innerWidth  / Math.max(maxX - minX + padding, 100);
        const fitY = window.innerHeight / Math.max(maxY - minY + padding, 100);
        const targetScale = Math.max(0.1, Math.min(1.0, Math.min(fitX, fitY)));
        if (typeof (viewportRef.current as any).setScale === 'function') {
          (viewportRef.current as any).setScale(targetScale);
        }
        viewportRef.current.focusOn(0, 0);
      }, 100);
    }
  }, [viewportRef]);

  const loadNextPage = useCallback(async (centerX?: number, centerY?: number) => {
    if (isLoadingRef.current) return;
    isLoadingRef.current = true;
    setIsLoading(true);
    setLoadError(null);

    try {
      const cx = centerX ?? 0;
      const cy = centerY ?? 0;
      const url = `http://localhost:8000/layout/knowledge_map_page?offset=${pageOffset}&limit=${pageLimit}&center_x=${cx}&center_y=${cy}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      if (data?.success) {
        const serverNodes: ActionNode[] = (data.blocks || []).map((b: any) => ({
          id: b.id,
          content: b.content || b.verb || b.id,
          verb: b.verb || '',
          verb_text: b.verb_text || '',
          subject: b.subject || '',
          object: b.object || '',
          action_class: b.action_class || 'action',
          norm_key: b.norm_key || '',
          doc_count: b.doc_count || 1,
          doc_ids: b.doc_ids || [],
          x: typeof b.x === 'number' ? b.x : 0,
          y: typeof b.y === 'number' ? b.y : 0,
        }));

        const serverEdges: ActionEdge[] = (data.links || []).map((l: any) => ({
          id: l.id,
          source_id: l.source_id,
          target_id: l.target_id,
          count: l.count || 1,
          confidence: l.confidence || 0,
          relation_subtype: l.relation_subtype || '',
        }));

        setNodes(prev => {
          const existingIds = new Set(prev.map(n => n.id));
          const toAdd = serverNodes.filter(n => !existingIds.has(n.id));
          return toAdd.length === 0 ? prev : [...prev, ...toAdd];
        });
        setEdges(prev => {
          const existingIds = new Set(prev.map(e => e.id));
          const toAdd = serverEdges.filter(e => !existingIds.has(e.id));
          return toAdd.length === 0 ? prev : [...prev, ...toAdd];
        });

        if (isBootLoading) {
          setIsBootLoading(false);
          if (serverNodes.length > 0) centerViewport(serverNodes);
        }
        setPageOffset(prev => prev + pageLimit);
      } else {
        throw new Error(data?.error || 'Failed to load knowledge map');
      }
    } catch (error: any) {
      console.error('[KnowledgeMap] load error:', error);
      setLoadError(error?.message || 'Unknown error');
      if (isBootLoading) setIsBootLoading(false);
    } finally {
      isLoadingRef.current = false;
      setIsLoading(false);
    }
  }, [pageOffset, pageLimit, isBootLoading, centerViewport]);

  const reset = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setPageOffset(0);
    setIsBootLoading(true);
    setLoadError(null);
  }, []);

  return {
    nodes,
    nodeMap,
    edges,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    loadNextPage,
    reset,
  };
}
