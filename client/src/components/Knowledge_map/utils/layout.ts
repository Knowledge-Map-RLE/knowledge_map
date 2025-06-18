import { BlockData, LevelData, SublevelData } from '../types';
import { LAYER_SPACING, SUBLEVEL_COLORS, LEVEL_COLORS } from '../constants';

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
      // Если блок не привязан к подуровню, используем случайное значение Y
      return {
        ...block,
        x,
        y: Math.random() * 500 - 250, // Случайное значение от -250 до 250
        layer: block.layer || 0
      } as BlockData;
    }
    
    // Находим уровень подуровня
    const level = levels.find(l => l.sublevel_ids.includes(sublevel.id));
    if (!level) {
      return {
        ...block,
        x,
        y: sublevel.min_y,
        layer: block.layer || 0
      } as BlockData;
    }
    
    return {
      ...block,
      x,
      y: sublevel.min_y,
      level: level.id,
      sublevel_id: sublevel.id,
      layer: block.layer || 0
    } as BlockData;
  });
};

// Функция для генерации связей на основе слоев блоков
export const generateLinksFromBlocks = (blocksData: BlockData[]): LinkData[] => {
  const linksList: LinkData[] = [];
  
  // Группируем блоки по слоям
  const blocksByLayer = blocksData.reduce((acc, block) => {
    if (!acc[block.layer]) {
      acc[block.layer] = [];
    }
    acc[block.layer].push(block);
    return acc;
  }, {} as Record<number, BlockData[]>);
  
  // Создаем связи между соседними слоями
  const layers = Object.keys(blocksByLayer).map(Number).sort((a, b) => a - b);
  
  for (let i = 0; i < layers.length - 1; i++) {
    const currentLayer = layers[i];
    const nextLayer = layers[i + 1];
    
    const currentBlocks = blocksByLayer[currentLayer];
    const nextBlocks = blocksByLayer[nextLayer];
    
    // Простая логика: соединяем каждый блок с одним или несколькими блоками следующего слоя
    currentBlocks.forEach((currentBlock, idx) => {
      // Выбираем один или несколько блоков из следующего слоя
      const targetCount = Math.min(2, nextBlocks.length); // Максимум 2 связи
      const startIdx = (idx * targetCount) % nextBlocks.length;
      
      for (let j = 0; j < targetCount; j++) {
        const targetIdx = (startIdx + j) % nextBlocks.length;
        const targetBlock = nextBlocks[targetIdx];
        
        linksList.push({
          id: `link_${currentBlock.id}_${targetBlock.id}`,
          fromId: currentBlock.id,
          toId: targetBlock.id
        });
      }
    });
  }
  
  return linksList;
};

// Функция для генерации моковых данных layout'а
export const generateMockLayoutData = (blocksData: BlockData[]) => {
  // Создаем подуровни на основе Y координат блоков
  const sublevelMap = new Map<number, { y: number, blockIds: string[], minX: number, maxX: number }>();
  
  blocksData.forEach(block => {
    const sublevelY = Math.round(block.y / 100) * 100; // Группируем по 100 пикселей
    if (!sublevelMap.has(sublevelY)) {
      sublevelMap.set(sublevelY, {
        y: sublevelY,
        blockIds: [],
        minX: block.x,
        maxX: block.x
      });
    }
    
    const sublevel = sublevelMap.get(sublevelY)!;
    sublevel.blockIds.push(block.id);
    sublevel.minX = Math.min(sublevel.minX, block.x - 100);
    sublevel.maxX = Math.max(sublevel.maxX, block.x + 100);
  });

  // Создаем подуровни
  const sublevelsList: SublevelData[] = Array.from(sublevelMap.entries()).map(([sublevelY, data], index) => ({
    id: index,
    block_ids: data.blockIds,
    min_x: data.minX,
    max_x: data.maxX,
    min_y: sublevelY,
    max_y: sublevelY,
    color: SUBLEVEL_COLORS[index % SUBLEVEL_COLORS.length],
    level_id: 0
  }));

  // Создаем уровни
  const levelMap = new Map<number, { sublevel_ids: number[], minX: number, maxX: number, minY: number, maxY: number }>();
  
  sublevelsList.forEach(sublevel => {
    if (!levelMap.has(sublevel.id)) {
      levelMap.set(sublevel.id, {
        sublevel_ids: [],
        minX: sublevel.min_x,
        maxX: sublevel.max_x,
        minY: sublevel.min_y,
        maxY: sublevel.max_y
      });
    }
    
    const level = levelMap.get(sublevel.id)!;
    level.sublevel_ids.push(sublevel.id);
    level.minX = Math.min(level.minX, sublevel.min_x);
    level.maxX = Math.max(level.maxX, sublevel.max_x);
    level.minY = Math.min(level.minY, sublevel.min_y);
    level.maxY = Math.max(level.maxY, sublevel.max_y);
  });

  const levelsList: LevelData[] = Array.from(levelMap.entries()).map(([levelId, data]) => ({
    id: levelId,
    sublevel_ids: data.sublevel_ids,
    min_x: data.minX,
    max_x: data.maxX,
    min_y: data.minY,
    max_y: data.maxY,
    color: LEVEL_COLORS[levelId % LEVEL_COLORS.length]
  }));

  // Обновляем блоки с привязкой к подуровням
  const updatedBlocks = blocksData.map(block => {
    const sublevel = sublevelsList.find(sl => sl.block_ids.includes(block.id));
    return {
      ...block,
      sublevel_id: sublevel?.id
    };
  });

  return {
    levels: levelsList,
    sublevels: sublevelsList,
    blocks: updatedBlocks
  };
}; 