import { Graphics, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState } from 'react';
import { Block } from './Block';
import type { BlockData, SublevelData, EditMode } from './types';
import { EditMode as EditModeEnum } from './types';
import { BLOCK_HEIGHT } from './constants';

extend({ Graphics, Text });

interface Props {
  sublevelData: SublevelData;
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
}

export function Sublevel({
  sublevelData,
  onSublevelHover,
  onSublevelClick
}: Props) {
  const { min_x, max_x, min_y, max_y, color, id } = sublevelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    const safeMinX = min_x ?? 0;
    const safeMaxX = max_x ?? 0;
    const safeMinY = min_y ?? 0;
    
    // Подуровень располагается точно на Y-координате блоков
    // min_y и max_y должны быть одинаковыми для горизонтального подуровня
    const sublevelY = safeMinY;
    const sublevelHeight = BLOCK_HEIGHT;
    
    g.clear();
    g.rect(safeMinX, sublevelY, safeMaxX - safeMinX, sublevelHeight);
    g.stroke({width: 2, color: color, alpha: isHovered ? 0.8 : 0.6});
    g.fill({color, alpha: isHovered ? 0.6 : 0.4});
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  return (
    <container sortableChildren={true}>
      <graphics
        draw={draw}
        eventMode="static"
        onMouseEnter={() => {
          setIsHovered(true);
          onSublevelHover?.(sublevelData);
        }}
        onMouseLeave={() => {
          setIsHovered(false);
          onSublevelHover?.(null);
        }}
        onMouseDown={() => onSublevelClick?.(sublevelData.id, ((min_x ?? 0) + (max_x ?? 0)) / 2, min_y ?? 0)}
      />
      <pixiText
        text={`Подуровень: ${id}`}
        x={(min_x ?? 0) + 10}
        y={(min_y ?? 0) + 10}
        style={{
          fontSize: 12,
          fill: '#000000',
          fontWeight: 'bold'
        }}
      />
    </container>
  );
} 