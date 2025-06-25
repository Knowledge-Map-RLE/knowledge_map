import type { BlockData, LevelData, SublevelData, LinkData } from '../types';
import { LAYER_SPACING, SUBLEVEL_COLORS, LEVEL_COLORS, LEVEL_PADDING, BLOCK_WIDTH, BLOCK_HEIGHT } from '../constants';

// Константы для расчета размеров
const LEVEL_HEIGHT = 300; // Высота уровня
const SUBLEVEL_HEIGHT = 120; // Высота подуровня внутри уровня
const SUBLEVEL_MARGIN = 20; // Отступ между подуровнями
const LEVEL_MARGIN = 50; // Отступ между уровнями
const GRAPH_WIDTH = 2000; // Полная ширина графа
const GRAPH_START_X = -1000; // Начало графа по X
const BLOCK_SPACING_X = 250; // Горизонтальный интервал между блоками
const BLOCK_SPACING_Y = 130; // Вертикальный интервал между блоками

// Функция для расчета координат уровней - они должны располагаться горизонтально друг под другом
export const calculateLevelCoordinates = (
  levels: LevelData[],
  _sublevels: SublevelData[]
): LevelData[] => {
  // Сортируем уровни по id для правильного порядка
  const sortedLevels = [...levels].sort((a, b) => a.id - b.id);
  
  let currentY = 0;
  
  return sortedLevels.map(level => {
    const levelHeight = LEVEL_HEIGHT;
    const minY = currentY;
    const maxY = currentY + levelHeight;
    
    // Переходим к следующему уровню
    currentY = maxY + LEVEL_MARGIN;
    
    return {
      ...level,
      min_x: GRAPH_START_X,
      max_x: GRAPH_START_X + GRAPH_WIDTH,
      min_y: minY,
      max_y: maxY
    };
  });
};

// Функция для расчёта координат подуровней внутри уровней
export const calculateSublevelCoordinates = (
  sublevels: SublevelData[],
  levels: LevelData[]
): SublevelData[] => {
  // Создаём карту уровней для быстрого поиска
  const levelMap = new Map<number, LevelData>();
  levels.forEach(level => {
    levelMap.set(level.id, level);
  });
  
  // Группируем подуровни по уровням
  const sublevelsByLevel = new Map<number, SublevelData[]>();
  sublevels.forEach(sublevel => {
    const levelId = sublevel.level_id;
    if (!sublevelsByLevel.has(levelId)) {
      sublevelsByLevel.set(levelId, []);
    }
    sublevelsByLevel.get(levelId)!.push(sublevel);
  });
  
  const result: SublevelData[] = [];
  
  // Для каждого уровня размещаем его подуровни
  sublevelsByLevel.forEach((levelSublevels, levelId) => {
    const level = levelMap.get(levelId);
    if (!level) return;
    
    // Сортируем подуровни по id
    const sortedSublevels = [...levelSublevels].sort((a, b) => a.id - b.id);
    
    const levelInnerHeight = (level.max_y || 0) - (level.min_y || 0) - 2 * SUBLEVEL_MARGIN;
    const sublevelCount = sortedSublevels.length;
    const sublevelHeight = sublevelCount > 0 ? 
      Math.min(SUBLEVEL_HEIGHT, (levelInnerHeight - (sublevelCount - 1) * SUBLEVEL_MARGIN) / sublevelCount) : 
      SUBLEVEL_HEIGHT;
    
    let currentY = (level.min_y || 0) + SUBLEVEL_MARGIN;
    
    sortedSublevels.forEach(sublevel => {
      result.push({
        ...sublevel,
        min_x: (level.min_x || 0) + SUBLEVEL_MARGIN,
        max_x: (level.max_x || 0) - SUBLEVEL_MARGIN,
        min_y: currentY,
        max_y: currentY + sublevelHeight
      });
      
      currentY += sublevelHeight + SUBLEVEL_MARGIN;
    });
  });
  
  return result;
};

// Функция для расчета координат блоков с разрешением коллизий (БЕЗ фиктивных вершин)
export const calculateBlockCoordinates = (
  blocks: BlockData[],
  levels: LevelData[],
  sublevels: SublevelData[],
  links: LinkData[]
): BlockData[] => {
  // Фильтруем блоки без id
  const validBlocks = blocks.filter(block => block && block.id);
  
  if (validBlocks.length === 0) return [];
  
  // 1. ПРОСТОЕ ПОСТРОЕНИЕ ГРАФА (без фиктивных вершин)
  
  // Строим граф зависимостей
  const graph = new Map<string, Set<string>>();
  const reverseGraph = new Map<string, Set<string>>();
  
  // Инициализируем граф для всех блоков
  validBlocks.forEach(block => {
    graph.set(block.id, new Set());
    reverseGraph.set(block.id, new Set());
  });
  
  // Добавляем связи
  links.forEach(link => {
    if (graph.has(link.source_id) && graph.has(link.target_id)) {
      graph.get(link.source_id)!.add(link.target_id);
      reverseGraph.get(link.target_id)!.add(link.source_id);
    }
  });
  
  // 2. ТОПОЛОГИЧЕСКАЯ СОРТИРОВКА И НАЗНАЧЕНИЕ СЛОЁВ
  
  // Вычисляем слои для всех блоков (минимальная глубина от корней)
  const blockLayers = new Map<string, number>();
  const visited = new Set<string>();
  
  // Находим корневые блоки (без входящих связей)
  const rootBlocks = validBlocks.filter(block => 
    reverseGraph.get(block.id)!.size === 0
  );
  
  // Если нет корней, выбираем блоки с минимальными входящими связями
  if (rootBlocks.length === 0) {
    const minInDegree = Math.min(...validBlocks.map(block => 
      reverseGraph.get(block.id)!.size
    ));
    rootBlocks.push(...validBlocks.filter(block => 
      reverseGraph.get(block.id)!.size === minInDegree
    ));
  }
  
  // Назначаем слои, начиная с корневых блоков
  function assignLayers(blockId: string, layer: number) {
    if (visited.has(blockId)) {
      blockLayers.set(blockId, Math.max(blockLayers.get(blockId) || 0, layer));
      return;
    }
    
    visited.add(blockId);
    blockLayers.set(blockId, layer);
    
    // Рекурсивно назначаем слои потомкам
    graph.get(blockId)!.forEach(childId => {
      assignLayers(childId, layer + 1);
    });
  }
  
  // Запускаем назначение слоёв
  rootBlocks.forEach(block => assignLayers(block.id, 0));
  
  // Обрабатываем оставшиеся блоки (если есть циклы)
  validBlocks.forEach(block => {
    if (!visited.has(block.id)) {
      assignLayers(block.id, 0);
    }
  });
  
  // 3. АЛГОРИТМ СУГИЯМЫ: УПОРЯДОЧЕНИЕ И РАЗМЕЩЕНИЕ
  
  // Группируем блоки по слоям
  const blocksByLayer = new Map<number, BlockData[]>();
  validBlocks.forEach(block => {
    const layer = blockLayers.get(block.id) || 0;
    if (!blocksByLayer.has(layer)) {
      blocksByLayer.set(layer, []);
    }
    blocksByLayer.get(layer)!.push(block);
  });
  
  // ФАЗА 1: УПОРЯДОЧЕНИЕ БЛОКОВ ВНУТРИ СЛОЁВ
  // Применяем эвристику для минимизации пересечений связей
  
  function orderNodesInLayer(layerNodes: BlockData[], layerIndex: number): BlockData[] {
    // Если в слое один блок, порядок не важен
    if (layerNodes.length <= 1) return layerNodes;
    
    // Вычисляем "барицентр" каждого блока на основе соседей
    const nodeScores = new Map<string, number>();
    
    layerNodes.forEach(node => {
      let totalWeight = 0;
      let totalPosition = 0;
      let neighborCount = 0;
      
      // Учитываем входящие связи (от предыдущих слоёв)
      const incomingNeighbors = Array.from(reverseGraph.get(node.id) || []);
      incomingNeighbors.forEach(neighborId => {
        const neighborLayer = blockLayers.get(neighborId);
        if (neighborLayer !== undefined && neighborLayer < layerIndex) {
          // Находим позицию соседа в его слое
          const neighborLayerNodes = blocksByLayer.get(neighborLayer);
          if (neighborLayerNodes) {
            const neighborPos = neighborLayerNodes.findIndex(n => n.id === neighborId);
            if (neighborPos >= 0) {
              totalPosition += neighborPos;
              neighborCount++;
            }
          }
        }
      });
      
      // Учитываем исходящие связи (к следующим слоям)
      const outgoingNeighbors = Array.from(graph.get(node.id) || []);
      outgoingNeighbors.forEach(neighborId => {
        const neighborLayer = blockLayers.get(neighborId);
        if (neighborLayer !== undefined && neighborLayer > layerIndex) {
          // Для исходящих связей используем текущий порядок (если есть)
          const neighborLayerNodes = blocksByLayer.get(neighborLayer);
          if (neighborLayerNodes) {
            const neighborPos = neighborLayerNodes.findIndex(n => n.id === neighborId);
            if (neighborPos >= 0) {
              totalPosition += neighborPos;
              neighborCount++;
            }
          }
        }
      });
      
      // Вычисляем барицентр (средняя позиция соседей)
      const barycenter = neighborCount > 0 ? totalPosition / neighborCount : layerNodes.length / 2;
      nodeScores.set(node.id, barycenter);
    });
    
    // Сортируем блоки по барицентру
    return [...layerNodes].sort((a, b) => {
      const scoreA = nodeScores.get(a.id) || 0;
      const scoreB = nodeScores.get(b.id) || 0;
      return scoreA - scoreB;
    });
  }
  
  // Применяем упорядочение ко всем слоям (несколько итераций для улучшения)
  const orderedBlocksByLayer = new Map<number, BlockData[]>();
  const layerNumbers = Array.from(blocksByLayer.keys()).sort((a, b) => a - b);
  
  // Инициализируем начальный порядок
  layerNumbers.forEach(layerNum => {
    orderedBlocksByLayer.set(layerNum, blocksByLayer.get(layerNum)!);
  });
  
  // Итеративное улучшение порядка (алгоритм баricenter heuristic)
  const MAX_ORDERING_ITERATIONS = 3;
  for (let iteration = 0; iteration < MAX_ORDERING_ITERATIONS; iteration++) {
    // Проходим слева направо
    for (let i = 0; i < layerNumbers.length; i++) {
      const layerNum = layerNumbers[i];
      const layerNodes = orderedBlocksByLayer.get(layerNum)!;
      const orderedNodes = orderNodesInLayer(layerNodes, layerNum);
      orderedBlocksByLayer.set(layerNum, orderedNodes);
    }
    
    // Проходим справа налево
    for (let i = layerNumbers.length - 1; i >= 0; i--) {
      const layerNum = layerNumbers[i];
      const layerNodes = orderedBlocksByLayer.get(layerNum)!;
      const orderedNodes = orderNodesInLayer(layerNodes, layerNum);
      orderedBlocksByLayer.set(layerNum, orderedNodes);
    }
  }
  
  // ФАЗА 2: НАЗНАЧЕНИЕ КООРДИНАТ
  
  const nodePositions = new Map<string, { x: number, y: number }>();
  
  // Константы для размещения
  const LAYER_WIDTH = BLOCK_SPACING_X; // Расстояние между слоями = 250px
  const NODE_HEIGHT = BLOCK_SPACING_Y; // Расстояние между блоками в слое = 130px
  
  layerNumbers.forEach(layerNum => {
    const layerNodes = orderedBlocksByLayer.get(layerNum)!;
    const layerNodeCount = layerNodes.length;
    
    // X координата - фиксированная для слоя
    const layerX = GRAPH_START_X + layerNum * LAYER_WIDTH;
    
    // Y координаты - центрируем блоки в слое
    const totalLayerHeight = (layerNodeCount - 1) * NODE_HEIGHT;
    const startY = -totalLayerHeight / 2; // Центрируем относительно y=0
    
    layerNodes.forEach((node, index) => {
      const nodeY = startY + index * NODE_HEIGHT;
      nodePositions.set(node.id, {
        x: layerX,
        y: nodeY
      });
    });
  });
  
  // 4. РАСПРЕДЕЛЕНИЕ НЕЗАКРЕПЛЁННЫХ БЛОКОВ ПО ПОДУРОВНЯМ
  
  const sublevelMap = new Map<number, SublevelData>();
  sublevels.forEach(sublevel => {
    sublevelMap.set(sublevel.id, sublevel);
  });
  
  // Группируем блоки по подуровням
  const blocksBySublevel = new Map<number, BlockData[]>();
  validBlocks.forEach(block => {
    const sublevelId = block.sublevel || 0;
    if (!blocksBySublevel.has(sublevelId)) {
      blocksBySublevel.set(sublevelId, []);
    }
    blocksBySublevel.get(sublevelId)!.push(block);
  });
  
  // Создаём виртуальные подуровни для незакреплённых блоков
  const virtualSublevels = new Map<string, { 
    blocks: BlockData[], 
    virtualIndex: number, 
    originalSublevel: SublevelData | null,
    yOffset: number 
  }>();
  
  function distributeBlocksInSublevel(sublevelId: number, sublevelBlocks: BlockData[]) {
    const originalSublevel = sublevelMap.get(sublevelId);
    
    // Фильтруем только незакреплённые блоки
    const unpinnedBlocks = sublevelBlocks.filter(block => !block.is_pinned);
    const pinnedBlocks = sublevelBlocks.filter(block => block.is_pinned);
    
    if (unpinnedBlocks.length <= 1) {
      // Если незакреплённых блоков мало, размещаем их в исходном подуровне
      const virtualKey = `${sublevelId}_0`;
      virtualSublevels.set(virtualKey, {
        blocks: sublevelBlocks,
        virtualIndex: 0,
        originalSublevel: originalSublevel || null,
        yOffset: 0
      });
      return;
    }
    
    // Вычисляем доступное вертикальное пространство
    let availableHeight = SUBLEVEL_HEIGHT;
    if (originalSublevel && originalSublevel.min_y !== undefined && originalSublevel.max_y !== undefined) {
      availableHeight = originalSublevel.max_y - originalSublevel.min_y;
    }
    
    // Определяем сколько блоков помещается в один подуровень
    const minBlockSpacing = BLOCK_HEIGHT + 20; // Минимальное расстояние между блоками
    const maxBlocksPerSublevel = Math.max(1, Math.floor(availableHeight / minBlockSpacing));
    
    console.log(`🔧 Подуровень ${sublevelId}: ${unpinnedBlocks.length} незакреплённых блоков, может поместиться ${maxBlocksPerSublevel} блоков на подуровень`);
    
    // Если все блоки помещаются в один подуровень, не создаём виртуальные
    if (unpinnedBlocks.length <= maxBlocksPerSublevel) {
      const virtualKey = `${sublevelId}_0`;
      virtualSublevels.set(virtualKey, {
        blocks: sublevelBlocks,
        virtualIndex: 0,
        originalSublevel: originalSublevel || null,
        yOffset: 0
      });
      return;
    }
    
    // Создаём виртуальные подуровни для незакреплённых блоков
    let virtualIndex = 0;
    
    // Сначала размещаем закреплённые блоки в исходном подуровне
    if (pinnedBlocks.length > 0) {
      const virtualKey = `${sublevelId}_${virtualIndex}`;
      virtualSublevels.set(virtualKey, {
        blocks: pinnedBlocks,
        virtualIndex: virtualIndex,
        originalSublevel: originalSublevel || null,
        yOffset: 0
      });
      virtualIndex++;
    }
    
    // Затем распределяем незакреплённые блоки по виртуальным подуровням
    for (let i = 0; i < unpinnedBlocks.length; i += maxBlocksPerSublevel) {
      const blockChunk = unpinnedBlocks.slice(i, i + maxBlocksPerSublevel);
      const virtualKey = `${sublevelId}_${virtualIndex}`;
      
      const yOffset = virtualIndex * (availableHeight + 30); // Отступ между виртуальными подуровнями
      
      virtualSublevels.set(virtualKey, {
        blocks: blockChunk,
        virtualIndex: virtualIndex,
        originalSublevel: originalSublevel || null,
        yOffset: yOffset
      });
      
      virtualIndex++;
    }
    
    console.log(`✅ Создано ${virtualIndex} виртуальных подуровней для подуровня ${sublevelId}`);
  }
  
  // Применяем распределение ко всем подуровням
  blocksBySublevel.forEach((sublevelBlocks, sublevelId) => {
    distributeBlocksInSublevel(sublevelId, sublevelBlocks);
  });
  
  // 5. ФИНАЛЬНОЕ РАЗМЕЩЕНИЕ С УЧЁТОМ ВИРТУАЛЬНЫХ ПОДУРОВНЕЙ
  
  const result: BlockData[] = [];
  
  // Размещаем блоки с учётом виртуальных подуровней
  validBlocks.forEach(block => {
    const position = nodePositions.get(block.id);
    
    if (position) {
      let finalX = position.x;
      let finalY = position.y;
      
      // Находим виртуальный подуровень для этого блока
      const sublevelId = block.sublevel || 0;
      let blockVirtualSublevel: { blocks: BlockData[], virtualIndex: number, originalSublevel: SublevelData | null, yOffset: number } | null = null;
      
      for (const [virtualKey, virtualSub] of virtualSublevels) {
        if (virtualKey.startsWith(`${sublevelId}_`) && virtualSub.blocks.some(b => b.id === block.id)) {
          blockVirtualSublevel = virtualSub;
          break;
        }
      }
      
      if (blockVirtualSublevel) {
        const originalSublevel = blockVirtualSublevel.originalSublevel;
        
        if (originalSublevel && originalSublevel.min_y !== undefined && originalSublevel.max_y !== undefined) {
          // Базовая позиция в пределах исходного подуровня
          const sublevelCenterY = (originalSublevel.min_y + originalSublevel.max_y) / 2;
          
          // Применяем смещение для виртуального подуровня
          finalY = sublevelCenterY + blockVirtualSublevel.yOffset;
          
          // Дополнительное смещение внутри виртуального подуровня
          const blockIndexInVirtual = blockVirtualSublevel.blocks.findIndex(b => b.id === block.id);
          if (blockIndexInVirtual >= 0 && blockVirtualSublevel.blocks.length > 1) {
            const virtualSublevelHeight = Math.min(SUBLEVEL_HEIGHT - 40, blockVirtualSublevel.blocks.length * 30);
            const blockOffsetInVirtual = (blockIndexInVirtual - (blockVirtualSublevel.blocks.length - 1) / 2) * 
                                       (virtualSublevelHeight / Math.max(1, blockVirtualSublevel.blocks.length - 1));
            finalY += blockOffsetInVirtual;
          }
          
          // Ограничиваем в разумных пределах (расширяем границы при необходимости)
          const margin = 10;
          const expandedMinY = originalSublevel.min_y - (blockVirtualSublevel.virtualIndex * 100);
          const expandedMaxY = originalSublevel.max_y + (blockVirtualSublevel.virtualIndex * 100);
          
          finalY = Math.max(expandedMinY + margin, finalY);
        }
      }
      
      result.push({
        ...block,
        x: finalX,
        y: finalY
      });
    } else {
      // Fallback для блоков без позиции
      result.push({
        ...block,
        x: (block.layer || 0) * BLOCK_SPACING_X,
        y: 0
      });
    }
  });
  
  // Финальная статистика
  const totalVirtualSublevels = virtualSublevels.size;
  const originalSublevels = sublevels.length;
  
  console.log(`📊 Алгоритм Сугиямы: обработано ${layerNumbers.length} слоёв, ${validBlocks.length} блоков`);
  console.log(`📋 Подуровни: ${originalSublevels} оригинальных → ${totalVirtualSublevels} виртуальных (+${totalVirtualSublevels - originalSublevels})`);
  
  return result;
}; 