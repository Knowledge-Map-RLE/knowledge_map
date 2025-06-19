import type { BlockData, LevelData, SublevelData } from '../types';
import { LAYER_SPACING, SUBLEVEL_COLORS, LEVEL_COLORS, LEVEL_PADDING } from '../constants';

// Константы для расчета размеров
const DEFAULT_BLOCK_HEIGHT = 100;
const SUBLEVEL_GAP = 80;

// Функция для расчета координат блоков на основе уровней и подуровней
export const calculateBlockCoordinates = (
  blocks: BlockData[],
  levels: LevelData[],
  sublevels: SublevelData[]
): BlockData[] => {
  // Фильтруем блоки без id
  const validBlocks = blocks.filter(block => block && block.id);
  
  return validBlocks.map(block => {
    // Используем layer из блока для X координаты
    const x = (block.layer || 0) * LAYER_SPACING;
    
    // Находим подуровень блока
    const sublevel = sublevels.find(sl => sl.block_ids.includes(block.id));
    if (!sublevel) {
      return {
        ...block,
        x,
        y: Math.random() * 500 - 250,
        layer: block.layer || 0
      } as BlockData;
    }
    
    return {
      ...block,
      x,
      y: (sublevel.min_y + sublevel.max_y) / 2, // Центрируем блок в подуровне
      level: sublevel.level,
      sublevel: sublevel.id,
      layer: block.layer || 0
    } as BlockData;
  });
};

// Функция для расчета координат уровней
export const calculateLevelCoordinates = (
  blocks: BlockData[],
  levels: LevelData[]
): LevelData[] => {
  return levels.map((level, index) => {
    const layer = index;
    const color = LEVEL_COLORS[layer % LEVEL_COLORS.length];
    return {
      ...level,
      min_x: layer * LAYER_SPACING - LEVEL_PADDING,
      max_x: layer * LAYER_SPACING + LEVEL_PADDING,
      color: `#${color.toString(16).padStart(6, '0')}`
    };
  });
};

// Функция для генерации моковых данных layout'а
export const generateMockLayoutData = (blocksData: BlockData[]) => {
  // Группируем блоки по layer
  const blocksByLayer = new Map<number, BlockData[]>();
  blocksData.forEach(block => {
    const layer = block.layer || 0;
    if (!blocksByLayer.has(layer)) {
      blocksByLayer.set(layer, []);
    }
    blocksByLayer.get(layer)!.push(block);
  });

  const levels: LevelData[] = [];
  const sublevels: SublevelData[] = [];
  let sublevelId = 0;
  let currentY = 0;

  // Обрабатываем каждый слой
  Array.from(blocksByLayer.keys()).sort((a, b) => a - b).forEach(layer => {
    const layerBlocks = blocksByLayer.get(layer)!;
    
    // Создаем подуровни для текущего слоя
    const layerSublevels: SublevelData[] = [];
    const blocksPerSublevel = Math.ceil(layerBlocks.length / 3); // Максимум 3 подуровня в уровне
    
    // Сначала создаем все подуровни, чтобы знать их общую высоту
    let totalSublevelsHeight = 0;
    const tempSublevels: SublevelData[] = [];
    
    for (let i = 0; i < layerBlocks.length; i += blocksPerSublevel) {
      const sublevelBlocks = layerBlocks.slice(i, i + blocksPerSublevel);
      const sublevelMinX = Math.min(...sublevelBlocks.map(b => b.x)) - LEVEL_PADDING;
      const sublevelMaxX = Math.max(...sublevelBlocks.map(b => b.x)) + LEVEL_PADDING;
      
      const sublevel: SublevelData = {
        id: sublevelId++,
        block_ids: sublevelBlocks.map(b => b.id),
        min_x: sublevelMinX,
        max_x: sublevelMaxX,
        min_y: 0, // Временное значение
        max_y: DEFAULT_BLOCK_HEIGHT, // Временное значение
        color: SUBLEVEL_COLORS[tempSublevels.length % SUBLEVEL_COLORS.length],
        level: layer
      };
      
      tempSublevels.push(sublevel);
      totalSublevelsHeight += DEFAULT_BLOCK_HEIGHT;
    }
    
    // Теперь вычисляем начальную Y-координату для центрирования всей группы подуровней
    const totalGapsHeight = (tempSublevels.length - 1) * SUBLEVEL_GAP;
    const totalHeight = totalSublevelsHeight + totalGapsHeight;
    let sublevelStartY = currentY + (DEFAULT_BLOCK_HEIGHT - totalHeight) / 2;
    
    // Устанавливаем правильные координаты для каждого подуровня
    tempSublevels.forEach(sublevel => {
      sublevel.min_y = sublevelStartY;
      sublevel.max_y = sublevelStartY + DEFAULT_BLOCK_HEIGHT;
      sublevelStartY = sublevel.max_y + SUBLEVEL_GAP;
      
      layerSublevels.push(sublevel);
      sublevels.push(sublevel);
    });

    // Создаем уровень, учитывая все его подуровни
    const levelMinX = Math.min(...layerSublevels.map(sl => sl.min_x));
    const levelMaxX = Math.max(...layerSublevels.map(sl => sl.max_x));
    
    const level: LevelData = {
      id: layer,
      sublevel_ids: layerSublevels.map(sl => sl.id),
      min_x: levelMinX,
      max_x: levelMaxX,
      min_y: currentY,
      max_y: currentY + DEFAULT_BLOCK_HEIGHT,
      color: LEVEL_COLORS[layer % LEVEL_COLORS.length]
    };
    
    levels.push(level);
    currentY = level.max_y; // Следующий уровень начнется точно после текущего
  });

  // Обновляем позиции блоков
  const updatedBlocks = blocksData.map(block => {
    const sublevel = sublevels.find(sl => sl.block_ids.includes(block.id));
    if (sublevel) {
      return {
        ...block,
        sublevel: sublevel.id,
        y: (sublevel.min_y + sublevel.max_y) / 2 // Центрируем блок по вертикали в подуровне
      };
    }
    return block;
  });

  return {
    levels,
    sublevels,
    blocks: updatedBlocks
  };
}; 