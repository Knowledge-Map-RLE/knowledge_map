import { Graphics, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect } from 'react';
import { Sublevel } from './Sublevel';
import type { BlockData, SublevelData, LevelData as LevelDataType } from './types';
import { LEVEL_PADDING, SUBLEVEL_PADDING, BLOCK_HEIGHT } from './constants';
import { Block } from './Block';
import { EditMode } from './types';
import { getLevelName } from './utils/scaleUtils';

extend({ Graphics, Container });

interface LevelProps {
  levelData: LevelDataType;
  blocks?: BlockData[]; // добавляем блоки для определения масштаба уровня
  onLevelHover?: (level: LevelDataType | null) => void;
}

export function Level({ 
  levelData, 
  blocks = [],
  onLevelHover
}: LevelProps) {
  const { min_x, max_x, min_y, max_y, color, id } = levelData;
  const [isHovered, setIsHovered] = useState(false);

  // Определяем физический масштаб уровня из блоков
  const getLevelPhysicalScale = useCallback(() => {
    // Находим блоки этого уровня
    const levelBlocks = blocks.filter(block => block.level === id);
    
    // Ищем блок с физическим масштабом
    const blockWithScale = levelBlocks.find(block => 
      block.physical_scale !== undefined && block.physical_scale !== null
    );
    
    // Возвращаем масштаб из блока или 0 по умолчанию (1 метр)
    return blockWithScale?.physical_scale ?? 0;
  }, [blocks, id]);

  const draw = useCallback((g: Graphics) => {
    const safeMinX = min_x ?? 0;
    const safeMaxX = max_x ?? 0;
    const safeMinY = min_y ?? 0;
    const safeMaxY = max_y ?? 0;
    
    g.clear();
    g.rect(safeMinX, safeMinY, safeMaxX - safeMinX, safeMaxY - safeMinY);
    g.fill({color: color, alpha: isHovered ? 0.6 : 0.4});
    g.stroke({width: 2, color: color, alpha: isHovered ? 0.8 : 0.6});
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const physicalScale = getLevelPhysicalScale();
  const levelName = getLevelName(physicalScale);

  return (
    <container sortableChildren={true}>
      <graphics
        draw={draw}
        eventMode="static"
        onMouseEnter={() => {
          setIsHovered(true);
          onLevelHover?.(levelData);
        }}
        onMouseLeave={() => {
          setIsHovered(false);
          onLevelHover?.(null);
        }}
        zIndex={1}
      />
      <pixiText
        text={levelName}
        x={(min_x ?? 0) + 10}
        y={(min_y ?? 0) + 10}
        style={{
          fontSize: 14,
          fill: color,
          fontWeight: 'bold'
        }}
      />
    </container>
  );
} 