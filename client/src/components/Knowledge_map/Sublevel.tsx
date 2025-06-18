import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';

extend({ Graphics });

export interface SublevelData {
  id: number;
  block_ids: string[];
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  color: number;
  level_id: number;
}

interface SublevelProps {
  sublevelData: SublevelData;
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
}

export function Sublevel({ sublevelData, onSublevelHover, onSublevelClick }: SublevelProps) {
  const { min_x, max_x, min_y, max_y, color } = sublevelData;

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(color, 0.2);
    g.lineStyle(2, color, 0.5);
    g.drawRect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.endFill();
  }, [min_x, max_x, min_y, max_y, color]);

  return (
    <pixiGraphics
      draw={draw}
      eventMode="static"
      onMouseEnter={() => onSublevelHover?.(sublevelData)}
      onMouseLeave={() => onSublevelHover?.(null)}
      onMouseDown={() => onSublevelClick?.(sublevelData.id, (min_x + max_x) / 2, min_y)}
    />
  );
} 