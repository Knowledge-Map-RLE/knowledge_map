import { BlockData, LevelData, SublevelData } from '../types';
import { LAYER_SPACING, SUBLEVEL_COLORS, LEVEL_COLORS, LEVEL_PADDING } from '../constants';

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
      level: sublevel.level_id,
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
  // Группируем блоки по layer
  const blocksByLayer = new Map<number, BlockData[]>();
  blocksData.forEach(block => {
    const layer = block.layer || 0;
    if (!blocksByLayer.has(layer)) {
      blocksByLayer.set(layer, []);
    }
    blocksByLayer.get(layer)!.push(block);
  });

  const DEFAULT_BLOCK_HEIGHT = 100; // Высота блока по умолчанию
  const SUBLEVEL_GAP = 80; // Отступ между подуровнями
  const LEVEL_TO_SUBLEVEL_GAP = 40; // Отступ между уровнем и его подуровнями

  let currentY = 0;
  const levels: LevelData[] = [];
  const sublevels: SublevelData[] = [];
  let sublevelId = 0;

  // Обрабатываем каждый слой
  Array.from(blocksByLayer.keys()).sort((a, b) => a - b).forEach(layer => {
    const layerBlocks = blocksByLayer.get(layer)!;
    
    // Создаем подуровни для текущего слоя
    const layerSublevels: SublevelData[] = [];
    const blocksPerSublevel = Math.ceil(layerBlocks.length / 3); // Максимум 3 подуровня в уровне
    
    // Начальная Y-координата для подуровней в текущем уровне
    let sublevelStartY = currentY + LEVEL_TO_SUBLEVEL_GAP;
    
    for (let i = 0; i < layerBlocks.length; i += blocksPerSublevel) {
      const sublevelBlocks = layerBlocks.slice(i, i + blocksPerSublevel);
      const sublevelMinX = Math.min(...sublevelBlocks.map(b => b.x)) - LEVEL_PADDING;
      const sublevelMaxX = Math.max(...sublevelBlocks.map(b => b.x)) + LEVEL_PADDING;
      
      // Находим максимальную высоту блока в подуровне
      const maxBlockHeight = Math.max(
        ...sublevelBlocks.map(b => b.height || DEFAULT_BLOCK_HEIGHT)
      );
      
      const sublevel: SublevelData = {
        id: sublevelId++,
        block_ids: sublevelBlocks.map(b => b.id),
        min_x: sublevelMinX,
        max_x: sublevelMaxX,
        min_y: sublevelStartY,
        max_y: sublevelStartY + maxBlockHeight,
        color: SUBLEVEL_COLORS[layerSublevels.length % SUBLEVEL_COLORS.length],
        level_id: layer
      };
      
      layerSublevels.push(sublevel);
      sublevels.push(sublevel);
      
      // Обновляем Y-координату для следующего подуровня
      sublevelStartY += maxBlockHeight + SUBLEVEL_GAP;
    }

    // Создаем уровень, учитывая все его подуровни
    const levelMinX = Math.min(...layerSublevels.map(sl => sl.min_x));
    const levelMaxX = Math.max(...layerSublevels.map(sl => sl.max_x));
    
    // Высота уровня теперь зависит от реальных высот подуровней
    const totalLevelHeight = 
      (layerSublevels.length > 0 
        ? layerSublevels[layerSublevels.length - 1].max_y - layerSublevels[0].min_y 
        : DEFAULT_BLOCK_HEIGHT) +
      2 * LEVEL_TO_SUBLEVEL_GAP;

    const level: LevelData = {
      id: layer,
      sublevel_ids: layerSublevels.map(sl => sl.id),
      min_x: levelMinX,
      max_x: levelMaxX,
      min_y: currentY,
      max_y: currentY + totalLevelHeight,
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
        sublevel_id: sublevel.id,
        y: (sublevel.min_y + sublevel.max_y) / 2, // Центрируем блок по вертикали в подуровне
        height: block.height || DEFAULT_BLOCK_HEIGHT // Устанавливаем высоту по умолчанию, если не задана
      };
    }
    return {
      ...block,
      height: block.height || DEFAULT_BLOCK_HEIGHT
    };
  });

  return {
    levels,
    sublevels,
    blocks: updatedBlocks
  };
}; 