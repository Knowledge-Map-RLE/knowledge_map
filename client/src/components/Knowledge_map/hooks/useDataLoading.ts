import { useState, useCallback, useRef, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { BlockData, LevelData, SublevelData, LinkData } from '../types';
import * as api from '../../../services/api';
import { calculateBlockCoordinates, calculateLevelCoordinates, calculateSublevelCoordinates } from '../utils/layout';

interface UseDataLoadingResult {
  blocks: BlockData[];
  links: LinkData[];
  levels: LevelData[];
  sublevels: SublevelData[];
  isLoading: boolean;
  loadError: string | null;
  loadLayoutData: () => Promise<void>;
  setBlocks: Dispatch<SetStateAction<BlockData[]>>;
  setLinks: Dispatch<SetStateAction<LinkData[]>>;
  setLevels: Dispatch<SetStateAction<LevelData[]>>;
  setSublevels: Dispatch<SetStateAction<SublevelData[]>>;
}

// Функция для преобразования блока из формата API в формат BlockData
const convertApiBlockToBlockData = (apiBlock: api.Block): BlockData => {
  if (!apiBlock || !apiBlock.id) {
    throw new Error('Invalid block data from API');
  }
  
  return {
    id: apiBlock.id,
    text: apiBlock.content || '',
    content: apiBlock.content || '',
    level: apiBlock.level || 0,
    layer: apiBlock.layer || 0,
    sublevel: apiBlock.sublevel_id || 0,
    is_pinned: apiBlock.is_pinned || false
  };
};

// Функция для преобразования связи из формата API в формат LinkData
const convertApiLinkToLinkData = (apiLink: api.Link): LinkData => {
  if (!apiLink || !apiLink.source_id || !apiLink.target_id) {
    throw new Error('Invalid link data from API');
  }

  const linkId = (apiLink.id && apiLink.id !== 'None') 
    ? apiLink.id 
    : `${apiLink.source_id}-${apiLink.target_id}`;

  return {
    id: linkId,
    source_id: apiLink.source_id,
    target_id: apiLink.target_id
  };
};

// Функция для преобразования уровня из формата API в формат LevelData
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
  const updateTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const loadLayoutData = useCallback(async () => {
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
    }

    updateTimeoutRef.current = setTimeout(async () => {
      setIsLoading(true);
      setLoadError(null);

      try {
        const data = await api.getLayout();

        if (!data.blocks || data.blocks.length === 0) {
          throw new Error('No blocks found in the response');
        }

        const convertedBlocks = data.blocks.map(convertApiBlockToBlockData);
        const convertedLinks = (data.links || []).map(convertApiLinkToLinkData);
        const convertedLevels = (data.levels || []).map(convertApiLevelToLevelData);
        const convertedSublevels = (data.sublevels || []).map(convertApiSublevelToSublevelData);

        // Рассчитываем координаты блоков по алгоритму Sugiyama
        const blocksWithCoords = calculateBlockCoordinates(convertedBlocks, convertedLevels, convertedSublevels);
        
        // После размещения блоков рассчитываем координаты подуровней и уровней
        const sublevelsWithCoords = calculateSublevelCoordinates(convertedSublevels, blocksWithCoords);
        const levelsWithCoords = calculateLevelCoordinates(convertedLevels, sublevelsWithCoords);

        setBlocks(prev => smartUpdateArray(prev, blocksWithCoords));
        setLinks(prev => smartUpdateArray(prev, convertedLinks));
        setLevels(prev => smartUpdateArray(prev, levelsWithCoords));
        setSublevels(prev => smartUpdateArray(prev, sublevelsWithCoords));

      } catch (error) {
        setLoadError(error instanceof Error ? error.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    }, 100);
  }, []);

  useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, []);

  return {
    blocks,
    links,
    levels,
    sublevels,
    isLoading,
    loadError,
    loadLayoutData,
    setBlocks,
    setLinks,
    setLevels,
    setSublevels
  };
} 