import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';

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
  onLevelHover?: (level: LevelData | null) => void;
}

export function Level({ levelData, onLevelHover }: LevelProps) {
  const { min_x, max_x, min_y, max_y, color } = levelData;

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(color, 0.2);
    g.lineStyle(2, color, 0.5);
    g.drawRect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.endFill();
  }, [min_x, max_x, min_y, max_y, color]);

  return (
    <graphics
      draw={draw}
      eventMode="static"
      onMouseEnter={() => onLevelHover?.(levelData)}
      onMouseLeave={() => onLevelHover?.(null)}
    />
  );
} 