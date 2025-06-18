import { useState, useCallback } from 'react';
import type { BlockData, LevelData, SublevelData, LinkData } from '../types';
import { calculateBlockCoordinates } from '../utils/layout';
import { SUBLEVEL_SPACING, LAYER_SPACING } from '../constants';
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
    level: apiBlock.level,
    layer: apiBlock.layer || 0,
    sublevel_id: apiBlock.sublevel_id
  };
};

// Функция для преобразования связи из формата API в формат LinkData
const convertApiLinkToLinkData = (apiLink: api.Link): LinkData => {
  if (!apiLink || !apiLink.id || !apiLink.source_id || !apiLink.target_id) {
    throw new Error('Invalid link data from API');
  }
  
  return {
    id: apiLink.id,
    fromId: apiLink.source_id,
    toId: apiLink.target_id
  };
};

// Функция для преобразования уровня из формата API в формат LevelData
const convertApiLevelToLevelData = (apiLevel: api.Level): LevelData => {
  if (!apiLevel || typeof apiLevel.id !== 'number') {
    throw new Error('Invalid level data from API');
  }
  
  return {
    id: apiLevel.id,
    sublevel_ids: apiLevel.sublevel_ids || [],
    min_x: apiLevel.min_x || 0,
    max_x: apiLevel.max_x || 0,
    min_y: apiLevel.min_y || 0,
    max_y: apiLevel.max_y || 0,
    color: apiLevel.color || 0
  };
};

// Функция для преобразования подуровня из формата API в формат SublevelData
const convertApiSublevelToSublevelData = (apiSublevel: api.Sublevel): SublevelData => {
  if (!apiSublevel || typeof apiSublevel.id !== 'number') {
    throw new Error('Invalid sublevel data from API');
  }
  
  return {
    id: apiSublevel.id,
    block_ids: apiSublevel.block_ids || [],
    min_x: apiSublevel.min_x || 0,
    max_x: apiSublevel.max_x || 0,
    min_y: apiSublevel.y || 0,
    max_y: apiSublevel.y + (apiSublevel.height || 0),
    color: apiSublevel.color || 0,
    level_id: apiSublevel.level_id || 0
  };
};

export const useDataLoading = (): UseDataLoadingResult => {
  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [links, setLinks] = useState<LinkData[]>([]);
  const [levels, setLevels] = useState<LevelData[]>([]);
  const [sublevels, setSublevels] = useState<SublevelData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadLayoutData = useCallback(async () => {
    try {
      setIsLoading(true);
      setLoadError(null);
      
      // Проверяем здоровье сервисов
      console.log('🏥 Проверка здоровья сервисов...');
      
      const [apiHealthy, layoutHealthy] = await Promise.all([
        api.checkHealth(),
        api.checkLayoutHealth()
      ]);
      
      if (!apiHealthy || !layoutHealthy) {
        throw new Error('Сервисы недоступны');
      }
      
      console.log('✅ Сервисы работают нормально');
      console.log('🔄 Загрузка данных карты знаний...');
      
      // Получаем укладку
      const layout = await api.getLayout([], [], {
        sublevel_spacing: SUBLEVEL_SPACING,
        layer_spacing: LAYER_SPACING,
        optimize_layout: true
      });
      
      if (!layout.success) {
        throw new Error(layout.error || 'Ошибка получения укладки');
      }
      
      console.log('📦 Полученные данные:', {
        blocks: layout.blocks,
        links: layout.links,
        levels: layout.levels,
        sublevels: layout.sublevels,
        statistics: layout.statistics
      });
      
      if (!layout.blocks || layout.blocks.length === 0) {
        console.log('⚠️ В базе данных нет блоков');
        setLoadError('В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.');
        return;
      }
      
      // Преобразуем и фильтруем данные из API
      const validBlocks = layout.blocks
        .filter((block: unknown): block is api.Block => block != null && typeof (block as any).id === 'string')
        .map(convertApiBlockToBlockData);
        
      const validLinks = (layout.links || [])
        .filter((link: unknown): link is api.Link => 
          link != null && 
          typeof (link as any).id === 'string' && 
          typeof (link as any).source_id === 'string' && 
          typeof (link as any).target_id === 'string'
        )
        .map(convertApiLinkToLinkData);
        
      const validLevels = (layout.levels || [])
        .filter((level: unknown): level is api.Level => 
          level != null && typeof (level as any).id === 'number'
        )
        .map(convertApiLevelToLevelData);
        
      const validSublevels = (layout.sublevels || [])
        .filter((sublevel: unknown): sublevel is api.Sublevel => 
          sublevel != null && typeof (sublevel as any).id === 'number'
        )
        .map(convertApiSublevelToSublevelData);
      
      // Рассчитываем координаты блоков
      const blocksWithCoordinates = calculateBlockCoordinates(
        validBlocks,
        validLevels,
        validSublevels
      );
      
      // Обновляем состояние
      setBlocks(blocksWithCoordinates);
      setLinks(validLinks);
      setLevels(validLevels);
      setSublevels(validSublevels);
      
      console.log('✅ Данные успешно загружены');
      
    } catch (error) {
      console.error('❌ Ошибка загрузки данных:', error);
      setLoadError(error instanceof Error ? error.message : 'Неизвестная ошибка');
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
}; 