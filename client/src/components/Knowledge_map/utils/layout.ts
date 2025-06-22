import type { BlockData, LevelData, SublevelData } from '../types';
import { LAYER_SPACING, SUBLEVEL_COLORS, LEVEL_COLORS, LEVEL_PADDING } from '../constants';

// Константы для расчета размеров
const DEFAULT_BLOCK_HEIGHT = 100;
const DEFAULT_BLOCK_WIDTH = 200;
const LEVEL_HEIGHT = 150; // Высота уровня (горизонтального прямоугольника)
const LEVEL_GAP = 0; // Уровни касаются друг друга
const SUBLEVEL_HEIGHT = 80; // Высота подуровня внутри уровня

// Функция для расчета координат блоков по алгоритму из km_hand_layout.py
export const calculateBlockCoordinates = (
  blocks: BlockData[],
  _levels: LevelData[],
  _sublevels: SublevelData[]
): BlockData[] => {
  // Фильтруем блоки без id
  const validBlocks = blocks.filter(block => block && block.id);
  
  // 1. Группируем узлы по слоям (как в Python: узлы_по_слоям)
  const nodesByLayer = new Map<number, BlockData[]>();
  
  validBlocks.forEach(block => {
    const layer = block.layer || 0;
    if (!nodesByLayer.has(layer)) {
      nodesByLayer.set(layer, []);
    }
    nodesByLayer.get(layer)!.push(block);
  });
  
  // 2. Для каждого слоя назначаем места размещения по вертикали (как в Python)
  const placementPositions: { [blockId: string]: { x: number, y: number } } = {};
  
  nodesByLayer.forEach((nodes, layer) => {
    const nodeCount = nodes.length;
    
    // Вычисляем позиции с шагом 2 для избежания наложений (как в Python)
    let yPositions: number[];
    
    if (nodeCount === 1) {
      // Если один узел, размещаем в центре (0)
      yPositions = [0];
    } else {
      // Размещаем узлы с шагом 2, центрируя их относительно 0
      const step = 2;
      const totalHeight = (nodeCount - 1) * step;
      const startY = -Math.floor(totalHeight / 2);
      yPositions = [];
      for (let i = 0; i < nodeCount; i++) {
        yPositions.push(startY + i * step);
      }
      
      // Если нечетное количество узлов, корректируем для центрирования
      if (nodeCount % 2 === 1) {
        // yPositions остаются как есть
      } else {
        // Для четного количества сдвигаем на 1, чтобы избежать 0
        yPositions = yPositions.map(y => y + 1);
      }
    }
    
    // Присваиваем координаты узлам (как в Python)
    nodes.forEach((node, i) => {
      const x = layer * 2; // X координата тоже кратна 2 (как в Python)
      const y = yPositions[i];
      placementPositions[node.id] = { x, y };
    });
  });
  
  // 3. Преобразуем в результат с правильным масштабом
  const result: BlockData[] = validBlocks.map(block => {
    const pos = placementPositions[block.id];
    const finalX = pos.x * (LAYER_SPACING / 2); // Масштабируем X для видимости
    const finalY = pos.y * 60; // Масштабируем Y для видимости (2 * 30)
    
    return {
      ...block,
      x: finalX,
      y: finalY,
      layer: block.layer || 0
    };
  });
  
  return result;
};

// Функция для создания подуровней на основе Y-координат блоков (как в km_hand_layout.py)
export const calculateSublevelCoordinates = (
  _sublevels: SublevelData[],
  blocks: BlockData[]
): SublevelData[] => {
  const result: SublevelData[] = [];
  
  // Получаем блоки на каждом подуровне (как в Python: подуровни = {})
  const sublevelsByY = new Map<number, BlockData[]>();
  
  blocks.forEach(block => {
    const y = block.y || 0;
    if (!sublevelsByY.has(y)) {
      sublevelsByY.set(y, []);
    }
    sublevelsByY.get(y)!.push(block);
  });
  
  // Создаем подуровни на основе Y-координат
  let sublevelId = 0;
  sublevelsByY.forEach((blocksInSublevel, yCoordinate) => {
    // Находим минимальную и максимальную X-координату блоков в этом подуровне
    const xCoordinates = blocksInSublevel.map(b => b.x || 0);
    const minX = Math.min(...xCoordinates) - DEFAULT_BLOCK_WIDTH / 2;
    const maxX = Math.max(...xCoordinates) + DEFAULT_BLOCK_WIDTH / 2;
    
    const sublevel: SublevelData = {
      id: sublevelId++,
      level_id: 0, // Будет установлено позже при группировке в уровни
      block_ids: blocksInSublevel.map(b => b.id),
      min_x: minX,
      max_x: maxX,
      min_y: yCoordinate - SUBLEVEL_HEIGHT / 2,
      max_y: yCoordinate + SUBLEVEL_HEIGHT / 2,
      color: `#${SUBLEVEL_COLORS[sublevelId % SUBLEVEL_COLORS.length].toString(16).padStart(6, '0')}`
    };
    
    result.push(sublevel);
  });
  
  return result;
};

// Функция для группировки подуровней в уровни (как в km_hand_layout.py)
export const calculateLevelCoordinates = (
  _levels: LevelData[],
  sublevels: SublevelData[]
): LevelData[] => {
  const result: LevelData[] = [];
  
  // Сортируем подуровни по Y-координате (как в Python: sorted_подуровни)
  const sortedSublevels = [...sublevels].sort((a, b) => (a.min_y || 0) - (b.min_y || 0));
  
  // Логика группировки: каждые 2-3 подуровня объединяем в один уровень (как в Python)
  const groupSize = 2; // можно настроить
  
  for (let i = 0; i < sortedSublevels.length; i += groupSize) {
    const levelId = Math.floor(i / groupSize);
    const sublevelGroup = sortedSublevels.slice(i, i + groupSize);
    
    // Обновляем level_id у подуровней
    sublevelGroup.forEach(sublevel => {
      sublevel.level_id = levelId;
    });
    
    // Создаем уровень на основе границ его подуровней
    const sublevelIds = sublevelGroup.map(sl => sl.id);
    const minX = Math.min(...sublevelGroup.map(sl => sl.min_x!)) - LEVEL_PADDING;
    const maxX = Math.max(...sublevelGroup.map(sl => sl.max_x!)) + LEVEL_PADDING;
    const minY = Math.min(...sublevelGroup.map(sl => sl.min_y!)) - LEVEL_PADDING;
    const maxY = Math.max(...sublevelGroup.map(sl => sl.max_y!)) + LEVEL_PADDING;
    
    const level: LevelData = {
      id: levelId,
      sublevel_ids: sublevelIds,
      name: `Уровень ${levelId}`,
      min_x: minX,
      max_x: maxX,
      min_y: minY,
      max_y: maxY,
      color: `#${LEVEL_COLORS[levelId % LEVEL_COLORS.length].toString(16).padStart(6, '0')}`
    };
    
    result.push(level);
  }
  
  return result;
}; 