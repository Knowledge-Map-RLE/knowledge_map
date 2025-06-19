import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState } from 'react';
import { Sublevel } from './Sublevel';
import type { SublevelData } from './Sublevel';
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
  onLevelHover?: (level: LevelData | null) => void;
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
}

export function Level({ levelData, sublevels, onLevelHover, onSublevelHover, onSublevelClick }: LevelProps) {
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

  const adjustedSublevels = levelSublevels.map(sublevel => ({
    ...sublevel,
    min_x: sublevel.min_x + LEVEL_PADDING,
    max_x: sublevel.max_x - LEVEL_PADDING,
    min_y: sublevel.min_y + LEVEL_PADDING,
    max_y: sublevel.max_y - LEVEL_PADDING
  }));

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
            onSublevelHover={onSublevelHover}
            onSublevelClick={onSublevelClick}
          />
        ))}
      </container>
    </container>
  );
} 