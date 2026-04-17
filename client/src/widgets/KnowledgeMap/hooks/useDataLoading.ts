import { useState, useCallback, useRef, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { BlockData, LevelData, SublevelData, LinkData, PolylinePoint } from '../types';
import * as api from '../../../services/api';
import { edgesByViewport } from '../../../services/api';
import { calculateBlockCoordinates, calculateLevelCoordinates, calculateSublevelCoordinates } from '../utils/layout';

interface UseDataLoadingResult {
  blocks: BlockData[];
  links: LinkData[];
  levels: LevelData[];
  sublevels: SublevelData[];
  isLoading: boolean;
  loadError: string | null;
  loadLayoutData: () => Promise<void>;
  loadAround: (centerX: number, centerY: number, limit?: number) => Promise<void>;
  loadEdgesByViewport: (bounds: {left:number; right:number; top:number; bottom:number}) => Promise<void>;
  setBlocks: Dispatch<SetStateAction<BlockData[]>>;
  setLinks: Dispatch<SetStateAction<LinkData[]>>;
  setLevels: Dispatch<SetStateAction<LevelData[]>>;
  setSublevels: Dispatch<SetStateAction<SublevelData[]>>;
}

type Bounds = { left: number; right: number; top: number; bottom: number };

const DEFAULT_PADDING = 200;

const normalizeBounds = (bounds: Bounds, padding: number = DEFAULT_PADDING): Bounds => ({
  left: Math.floor(bounds.left - padding),
  right: Math.ceil(bounds.right + padding),
  top: Math.floor(bounds.top - padding),
  bottom: Math.ceil(bounds.bottom + padding),
});

const boundsKey = (bounds: Bounds): string =>
  `${bounds.left}:${bounds.top}:${bounds.right}:${bounds.bottom}`;

const rectContains = (outer: Bounds, inner: Bounds): boolean =>
  outer.left <= inner.left &&
  outer.right >= inner.right &&
  outer.top <= inner.top &&
  outer.bottom >= inner.bottom;

const rectsOverlap = (a: Bounds, b: Bounds): boolean =>
  !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);

const mergeRegion = (regions: Bounds[], candidate: Bounds): Bounds[] => {
  let merged = { ...candidate };
  const remaining: Bounds[] = [];

  for (const region of regions) {
    if (
      rectContains(region, merged) ||
      rectContains(merged, region) ||
      rectsOverlap(region, merged)
    ) {
      merged = {
        left: Math.min(region.left, merged.left),
        right: Math.max(region.right, merged.right),
        top: Math.min(region.top, merged.top),
        bottom: Math.max(region.bottom, merged.bottom),
      };
    } else {
      remaining.push(region);
    }
  }

  remaining.push(merged);

  // Limit number of tracked regions to avoid unbounded growth
  return remaining.slice(-50);
};

// Функция для преобразования блока из формата API в формат BlockData
const convertApiBlockToBlockData = (apiBlock: api.Block): BlockData => {
  if (!apiBlock || !apiBlock.id) {
    throw new Error('Invalid block data from API');
  }
  
  return {
    id: apiBlock.id,
    title: apiBlock.title || apiBlock.content || '',
    x: (typeof apiBlock.x === 'number') ? apiBlock.x : (undefined as any),
    y: (typeof apiBlock.y === 'number') ? apiBlock.y : (undefined as any),
    level: apiBlock.level || 0,
    physical_scale: apiBlock.physical_scale || 0,
    layer: apiBlock.layer || 0,
    is_pinned: apiBlock.is_pinned || false
  };
};

const normalizeMetadata = (metadata: unknown): Record<string, unknown> | undefined => {
  if (metadata == null) {
    return undefined;
  }
  if (typeof metadata === 'string') {
    try {
      const parsed = JSON.parse(metadata);
      return typeof parsed === 'object' && parsed !== null ? parsed as Record<string, unknown> : { raw: metadata };
    } catch {
      return { raw: metadata };
    }
  }
  if (typeof metadata === 'object') {
    return metadata as Record<string, unknown>;
  }
  return undefined;
};

const parsePolylineCandidate = (candidate: unknown): PolylinePoint[] | undefined => {
  if (!candidate) {
    return undefined;
  }
  let value = candidate;
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value);
    } catch {
      return undefined;
    }
  }
  if (!Array.isArray(value)) {
    return undefined;
  }

  const normalized: PolylinePoint[] = [];
  for (const entry of value) {
    if (Array.isArray(entry) && entry.length >= 2) {
      const x = Number(entry[0]);
      const y = Number(entry[1]);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        normalized.push({ x, y });
      }
      continue;
    }

    if (entry && typeof entry === 'object') {
      const obj = entry as Record<string, unknown>;
      const xCandidate = obj.x ?? obj.X ?? (Array.isArray(obj) ? obj[0] : undefined);
      const yCandidate = obj.y ?? obj.Y ?? (Array.isArray(obj) ? obj[1] : undefined);
      const x = Number(xCandidate);
      const y = Number(yCandidate);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        normalized.push({ x, y });
      }
    }
  }

  return normalized.length >= 2 ? normalized : undefined;
};

const extractPolylineFromMetadata = (
  metadata: Record<string, unknown> | undefined,
  sourceId: string,
  targetId: string,
): PolylinePoint[] | undefined => {
  if (!metadata) {
    return undefined;
  }

  const directKeys = ['polyline', 'poly_line', 'points', 'path', 'edge_path', 'edgePath'];
  for (const key of directKeys) {
    const directCandidate = metadata[key];
    const parsed = parsePolylineCandidate(directCandidate);
    if (parsed) {
      return parsed;
    }
  }

  const keyVariants = [
    `${sourceId}->${targetId}`,
    `${sourceId}:${targetId}`,
    `${sourceId}|${targetId}`,
    `${sourceId},${targetId}`,
  ];
  const mapKeys = ['edge_paths', 'edgePaths', 'paths', 'polyline_map'];

  for (const key of mapKeys) {
    if (!(key in metadata)) {
      continue;
    }
    let mapCandidate = metadata[key];
    if (typeof mapCandidate === 'string') {
      try {
        mapCandidate = JSON.parse(mapCandidate);
      } catch {
        continue;
      }
    }

    if (Array.isArray(mapCandidate)) {
      const parsed = parsePolylineCandidate(mapCandidate);
      if (parsed) {
        return parsed;
      }
    } else if (mapCandidate && typeof mapCandidate === 'object') {
      const mapObject = mapCandidate as Record<string, unknown>;
      for (const variantKey of keyVariants) {
        const candidate = mapObject[variantKey];
        const parsed = parsePolylineCandidate(candidate);
        if (parsed) {
          return parsed;
        }
      }

      const nested = mapObject[sourceId];
      if (nested && typeof nested === 'object') {
        const nestedMap = nested as Record<string, unknown>;
        const parsed = parsePolylineCandidate(nestedMap[targetId]);
        if (parsed) {
          return parsed;
        }
      }
    }
  }

  if ('parameters' in metadata && metadata.parameters && typeof metadata.parameters === 'object') {
    const nested = metadata.parameters as Record<string, unknown>;
    const parsed = extractPolylineFromMetadata(nested, sourceId, targetId);
    if (parsed) {
      return parsed;
    }
  }

  return undefined;
};

const extractPolylineFromLink = (
  apiLink: api.Link,
  metadata: Record<string, unknown> | undefined,
): PolylinePoint[] | undefined => {
  const fromMetadata = extractPolylineFromMetadata(metadata, apiLink.source_id, apiLink.target_id);
  if (fromMetadata) {
    return fromMetadata;
  }

  const direct = parsePolylineCandidate((apiLink as unknown as Record<string, unknown>).polyline);
  if (direct) {
    return direct;
  }

  return undefined;
};

const convertApiLinkToLinkData = (apiLink: api.Link): LinkData => {
  if (!apiLink || !apiLink.source_id || !apiLink.target_id) {
    throw new Error('Invalid link data from API');
  }

  const linkId = (apiLink.id && apiLink.id !== 'None')
    ? apiLink.id
    : `${apiLink.source_id}-${apiLink.target_id}`;

  const parsedMetadata = normalizeMetadata(apiLink.metadata);
  const polyline = extractPolylineFromLink(apiLink, parsedMetadata);
  const metadataCopy = parsedMetadata ? { ...parsedMetadata } : undefined;
  if (metadataCopy && 'edge_paths' in metadataCopy) {
    delete (metadataCopy as Record<string, unknown>).edge_paths;
  }
  if (metadataCopy && 'parameters' in metadataCopy) {
    const paramsValue = metadataCopy.parameters;
    if (typeof paramsValue === 'string') {
      try {
        const parsedParams = JSON.parse(paramsValue);
        if (parsedParams && typeof parsedParams === 'object') {
          const paramsCopy = { ...(parsedParams as Record<string, unknown>) };
          if ('edge_paths' in paramsCopy) {
            delete paramsCopy.edge_paths;
          }
          metadataCopy.parameters = Object.keys(paramsCopy).length > 0 ? paramsCopy : undefined;
        }
      } catch {
        // ignore parsing errors
      }
    } else if (paramsValue && typeof paramsValue === 'object') {
      const paramsCopy = { ...(paramsValue as Record<string, unknown>) };
      if ('edge_paths' in paramsCopy) {
        delete paramsCopy.edge_paths;
      }
      metadataCopy.parameters = Object.keys(paramsCopy).length > 0 ? paramsCopy : undefined;
    }
    if (metadataCopy.parameters === undefined) {
      delete metadataCopy.parameters;
    }
  }
  const cleanedMetadata = metadataCopy && Object.keys(metadataCopy).length > 0 ? metadataCopy : undefined;

  return {
    id: linkId,
    source_id: apiLink.source_id,
    target_id: apiLink.target_id,
    metadata: cleanedMetadata,
    polyline,
  };
};

const convertApiLevelToLevelData = (apiLevel: api.Level): LevelData => {
  if (!apiLevel || typeof apiLevel.id !== 'number') {
    throw new Error('Invalid level data from API');
  }

  if (!Array.isArray(apiLevel.sublevel_ids)) {
    console.error('Missing required level fields:', apiLevel);
    throw new Error('Invalid level data from API: missing sublevel_ids');
  }

  return {
    id: apiLevel.id,
    sublevel_ids: apiLevel.sublevel_ids,
    name: apiLevel.name || `Уровень ${apiLevel.id}`,
    color: apiLevel.color || '#b0c4de'
  };
};

// Функция для преобразования подуровня из формата API в формат SublevelData
const convertApiSublevelToSublevelData = (apiSublevel: api.Sublevel): SublevelData => {
  if (!apiSublevel || typeof apiSublevel.id !== 'number') {
    console.error('Invalid sublevel data:', apiSublevel);
    throw new Error('Invalid sublevel data from API');
  }

  if (typeof apiSublevel.level_id !== 'number' ||
      !Array.isArray(apiSublevel.block_ids)) {
    console.error('Missing required sublevel fields. Values:', {
      level_id: apiSublevel.level_id,
      block_ids: apiSublevel.block_ids
    });
    throw new Error('Invalid sublevel data from API: missing required fields');
  }

  return {
    id: apiSublevel.id,
    level_id: apiSublevel.level_id,
    block_ids: apiSublevel.block_ids,
    color: apiSublevel.color || '#add8e6'
  };
};

/**
 * Универсальная функция для "умного" обновления состояния массива.
 * Сохраняет ссылки на объекты, если они существуют в новом и старом массивах,
 * чтобы предотвратить ненужный перемонтирование компонентов React.
 * @param oldArray - Предыдущее состояние (массив).
 * @param newArray - Новый массив данных из API.
 * @returns - Новый массив для установки в состояние.
 */
function smartUpdateArray<T extends { id: any }>(oldArray: T[], newArray: T[]): T[] {
  const newMap = new Map(newArray.map(item => [item.id, item]));
  const updatedArray: T[] = [];
  const usedIds = new Set();

  // Обновляем или сохраняем старые элементы
  for (const oldItem of oldArray) {
    const newItem = newMap.get(oldItem.id);
    if (newItem) {
      // Элемент существует в обоих массивах, обновляем его
      Object.assign(oldItem, newItem);
      updatedArray.push(oldItem);
      usedIds.add(oldItem.id);
    }
    // Если oldItem нет в newMap, он будет удален (не попадает в updatedArray)
  }

  // Добавляем новые элементы, которых не было в старом массиве
  for (const newItem of newArray) {
    if (!usedIds.has(newItem.id)) {
      updatedArray.push(newItem);
    }
  }

  return updatedArray;
}

export function useDataLoading(): UseDataLoadingResult {
  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [links, setLinks] = useState<LinkData[]>([]);
  const [levels, setLevels] = useState<LevelData[]>([]);
  const [sublevels, setSublevels] = useState<SublevelData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const blocksRef = useRef<BlockData[]>([]);
  useEffect(() => {
    blocksRef.current = blocks;
  }, [blocks]);

  const loadedRegionsRef = useRef<Bounds[]>([]);
  const pendingRegionsRef = useRef<Set<string>>(new Set());
  const lastViewportRef = useRef<Bounds | null>(null);

  const loadEdgesByViewportInternal = useCallback(async (rawBounds: Bounds) => {
    lastViewportRef.current = rawBounds;
    const normalized = normalizeBounds(rawBounds);

    const alreadyCovered = loadedRegionsRef.current.some(region => rectContains(region, normalized));
    if (alreadyCovered) {
      return;
    }

    const key = boundsKey(normalized);
    if (pendingRegionsRef.current.has(key)) {
      return;
    }

    const shouldShowLoader = (
      loadedRegionsRef.current.length === 0 &&
      blocksRef.current.length === 0 &&
      pendingRegionsRef.current.size === 0
    );

    if (shouldShowLoader) {
      setIsLoading(true);
    }
    setLoadError(null);
    pendingRegionsRef.current.add(key);

    try {
      const data = await edgesByViewport(normalized);

      if (Array.isArray(data.blocks)) {
        const mergedBlocks: BlockData[] = data.blocks.map((b: any) =>
          convertApiBlockToBlockData({
            id: String(b.id),
            title: b.title ?? '',
            content: b.content ?? '',
            x: b.x,
            y: b.y,
            layer: b.layer ?? 0,
            level: b.level ?? 0,
            physical_scale: b.physical_scale ?? 0,
            is_pinned: b.is_pinned ?? false,
          } as api.Block)
        );
        setBlocks(prev => smartUpdateArray(prev, mergedBlocks));
      }

      if (Array.isArray(data.links)) {
        const mergedLinks: LinkData[] = data.links.map((l: any) =>
          convertApiLinkToLinkData({
            id: String(l.id ?? `${l.source_id}-${l.target_id}`),
            source_id: String(l.source_id),
            target_id: String(l.target_id),
            metadata: l.metadata,
            polyline: l.polyline,
          } as api.Link)
        );
        setLinks(prev => smartUpdateArray(prev, mergedLinks));
      }

      const anyData = data as any;
      if (Array.isArray(anyData?.levels)) {
        const convertedLevels = anyData.levels.map(convertApiLevelToLevelData);
        setLevels(prev => smartUpdateArray(prev, convertedLevels));
      }

      if (Array.isArray(anyData?.sublevels)) {
        const convertedSublevels = anyData.sublevels.map(convertApiSublevelToSublevelData);
        setSublevels(prev => smartUpdateArray(prev, convertedSublevels));
      }

      loadedRegionsRef.current = mergeRegion(loadedRegionsRef.current, normalized);
    } catch (error) {
      console.warn('loadEdgesByViewport failed', error)
      setLoadError(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      pendingRegionsRef.current.delete(key);
      if (shouldShowLoader) {
        setIsLoading(false);
      }
    }
  }, [setBlocks, setLinks, setLevels, setSublevels])

  const loadEdgesByViewport = useCallback(async (bounds: Bounds) => {
    await loadEdgesByViewportInternal(bounds);
  }, [loadEdgesByViewportInternal])

  const loadAround = useCallback(async (centerX: number, centerY: number, limit: number = 1000) => {
    const half = limit / 2;
    await loadEdgesByViewportInternal({
      left: centerX - half,
      right: centerX + half,
      top: centerY - half,
      bottom: centerY + half,
    });
  }, [loadEdgesByViewportInternal])

  const loadLayoutData = useCallback(async () => {
    loadedRegionsRef.current = [];
    pendingRegionsRef.current.clear();
    setIsLoading(true);
    setLoadError(null);
    try {
      const fallback = lastViewportRef.current ?? { left: -500, right: 500, top: -500, bottom: 500 };
      await loadEdgesByViewportInternal(fallback);
    } finally {
      setIsLoading(false);
    }
  }, [loadEdgesByViewportInternal])

  return {
    blocks,
    links,
    levels,
    sublevels,
    isLoading,
    loadError,
    loadLayoutData,
    loadAround,
    loadEdgesByViewport,
    setBlocks,
    setLinks,
    setLevels,
    setSublevels
  };
} 
