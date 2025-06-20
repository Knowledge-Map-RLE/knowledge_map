import { useState, useCallback } from 'react';
import type { BlockData, LevelData, SublevelData, LinkData } from '../types';
import * as api from '../../../services/api';

interface UseDataLoadingResult {
  blocks: BlockData[];
  links: LinkData[];
  levels: LevelData[];
  sublevels: SublevelData[];
  isLoading: boolean;
  loadError: string | null;
  loadLayoutData: () => Promise<void>;
  setBlocks: (blocks: BlockData[]) => void;
  setLinks: (links: LinkData[]) => void;
  setLevels: (levels: LevelData[]) => void;
  setSublevels: (sublevels: SublevelData[]) => void;
}

// Функция для преобразования блока из формата API в формат BlockData
const convertApiBlockToBlockData = (apiBlock: api.Block): BlockData => {
  if (!apiBlock || !apiBlock.id) {
    throw new Error('Invalid block data from API');
  }
  
  return {
    id: apiBlock.id,
    text: apiBlock.content || '',
    x: apiBlock.x || 0,
    y: apiBlock.y || 0,
    level: apiBlock.level || 0,
    layer: apiBlock.layer || 0,
    sublevel: apiBlock.sublevel_id || 0
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

  if (typeof apiLevel.min_x !== 'number' || 
      typeof apiLevel.max_x !== 'number' || 
      typeof apiLevel.min_y !== 'number' || 
      typeof apiLevel.max_y !== 'number') {
    console.error('Missing required level fields:', apiLevel);
    throw new Error('Invalid level data from API: missing required fields');
  }

  // Используем значения по умолчанию для опциональных полей
  const defaultColor = 0;
  const defaultName = `Уровень ${apiLevel.id}`;

  return {
    id: apiLevel.id,
    min_x: apiLevel.min_x,
    max_x: apiLevel.max_x,
    min_y: apiLevel.min_y,
    max_y: apiLevel.max_y,
    color: apiLevel.color !== undefined ? apiLevel.color : defaultColor,
    name: apiLevel.name || defaultName
  };
};

// Функция для преобразования подуровня из формата API в формат SublevelData
const convertApiSublevelToSublevelData = (apiSublevel: api.Sublevel): SublevelData => {
  if (!apiSublevel || typeof apiSublevel.id !== 'number') {
    console.error('Invalid sublevel data:', apiSublevel);
    throw new Error('Invalid sublevel data from API');
  }

  if (typeof apiSublevel.min_x !== 'number' || 
      typeof apiSublevel.max_x !== 'number' || 
      typeof apiSublevel.min_y !== 'number' || 
      typeof apiSublevel.max_y !== 'number' ||
      typeof apiSublevel.level !== 'number' ||
      !Array.isArray(apiSublevel.block_ids)) {
    console.error('Missing required sublevel fields. Values:', {
      min_x: apiSublevel.min_x,
      max_x: apiSublevel.max_x,
      min_y: apiSublevel.min_y,
      max_y: apiSublevel.max_y,
      level: apiSublevel.level,
      block_ids: apiSublevel.block_ids
    });
    throw new Error('Invalid sublevel data from API: missing required fields');
  }

  // Используем значения по умолчанию для опциональных полей
  const defaultColor = 0xD3D3D3;

  return {
    id: apiSublevel.id,
    min_x: apiSublevel.min_x,
    max_x: apiSublevel.max_x,
    min_y: apiSublevel.min_y,
    max_y: apiSublevel.max_y,
    color: apiSublevel.color !== undefined ? apiSublevel.color : defaultColor,
    block_ids: apiSublevel.block_ids,
    level: apiSublevel.level
  };
};

export function useDataLoading(): UseDataLoadingResult {
  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [links, setLinks] = useState<LinkData[]>([]);
  const [levels, setLevels] = useState<LevelData[]>([]);
  const [sublevels, setSublevels] = useState<SublevelData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadLayoutData = useCallback(async () => {
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

      setBlocks(convertedBlocks);
      setLinks(convertedLinks);
      setLevels(convertedLevels);
      setSublevels(convertedSublevels);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
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