import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState } from 'react';
import { Sublevel } from './Sublevel';
import type { BlockData, SublevelData } from './types';
import { LEVEL_PADDING } from './constants';

extend({ Graphics });

export interface LevelData {
  id: number;
  sublevel_ids: number[];
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color: number;
}

interface LevelProps {
  levelData: LevelData;
  sublevels: SublevelData[];
  blocks: BlockData[];
  onLevelHover?: (level: LevelData | null) => void;
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
  onBlockClick?: (blockId: string) => void;
  onBlockHover?: (block: BlockData | null) => void;
  selectedBlocks?: string[];
}

export function Level({ 
  levelData, 
  sublevels, 
  blocks = [], 
  onLevelHover, 
  onSublevelHover, 
  onSublevelClick,
  onBlockClick,
  onBlockHover,
  selectedBlocks = []
}: LevelProps) {
  const { min_x, max_x, min_y, max_y, color, sublevel_ids, id } = levelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(color, isHovered ? 0.6 : 0.4);
    g.lineStyle(2, color, isHovered ? 0.8 : 0.6);
    g.drawRect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.endFill();
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const levelSublevels = sublevels.filter(sublevel => sublevel_ids.includes(sublevel.id));

  // Рассчитываем общую высоту всех подуровней
  const totalSublevelsHeight = levelSublevels.reduce((total, sublevel) => 
    total + (sublevel.max_y - sublevel.min_y), 0);
  const totalGapsHeight = (levelSublevels.length - 1) * LEVEL_PADDING;
  const totalHeight = totalSublevelsHeight + totalGapsHeight;

  // Вычисляем начальную Y-координату для центрирования группы подуровней
  const levelHeight = max_y - min_y;
  let currentY = min_y + (levelHeight - totalHeight) / 2;

  const adjustedSublevels = levelSublevels.map(sublevel => {
    const sublevelHeight = sublevel.max_y - sublevel.min_y;
    const adjusted = {
      ...sublevel,
      min_x: sublevel.min_x + LEVEL_PADDING,
      max_x: sublevel.max_x - LEVEL_PADDING,
      min_y: currentY,
      max_y: currentY + sublevelHeight
    };
    currentY += sublevelHeight + LEVEL_PADDING;
    return adjusted;
  });

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
        x={min_x + 10}
        y={min_y + 10}
        style={{
          fontSize: 14,
          fill: color,
          fontWeight: 'bold'
        }}
      />
      <container zIndex={2}>
        {adjustedSublevels.map((sublevel) => (
          <Sublevel
            key={sublevel.id}
            sublevelData={sublevel}
            blocks={blocks}
            onSublevelHover={onSublevelHover}
            onSublevelClick={onSublevelClick}
            onBlockClick={onBlockClick}
            onBlockHover={onBlockHover}
            selectedBlocks={selectedBlocks}
          />
        ))}
      </container>
    </container>
  );
} 