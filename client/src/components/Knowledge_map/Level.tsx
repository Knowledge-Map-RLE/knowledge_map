import { Graphics, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect } from 'react';
import { Sublevel } from './Sublevel';
import type { BlockData, SublevelData, LevelData as LevelDataType } from './types';
import { LEVEL_PADDING, SUBLEVEL_PADDING, BLOCK_HEIGHT } from './constants';
import { Block } from './Block';
import { EditMode } from './types';

extend({ Graphics, Container });

interface LevelProps {
  levelData: LevelDataType;
  onLevelHover?: (level: LevelDataType | null) => void;
}

export function Level({ 
  levelData, 
  onLevelHover
}: LevelProps) {
  const { min_x, max_x, min_y, max_y, color, id } = levelData;
  const [isHovered, setIsHovered] = useState(false);

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
        text={`Уровень: ${id}`}
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