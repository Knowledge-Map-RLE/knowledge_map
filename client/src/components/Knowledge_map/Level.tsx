import { useState } from 'react';
import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import type { ReactNode } from 'react';

extend({ Graphics });

export interface LevelData {
  id: number;
  sublevelIds: number[];
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  color: number;
}

interface LevelProps {
  levelData: LevelData;
  onLevelHover?: (levelId: number, isHovered: boolean) => void;
}

const LEVEL_ALPHA = 0.15;
const LEVEL_ALPHA_HOVER = 0.25;
const LEVEL_BORDER_WIDTH = 2;
const LEVEL_BORDER_COLOR = 0x1e40af; // navy
const LEVEL_MARGIN = 20; // отступ уровня в пикселях

export function Level({ levelData, onLevelHover }: LevelProps): ReactNode {
  const [isHovered, setIsHovered] = useState(false);

  const handlePointerEnter = () => {
    setIsHovered(true);
    onLevelHover?.(levelData.id, true);
  };

  const handlePointerLeave = () => {
    setIsHovered(false);
    onLevelHover?.(levelData.id, false);
  };

  const width = levelData.maxX - levelData.minX + 2 * LEVEL_MARGIN;
  const height = levelData.maxY - levelData.minY + 160 + 2 * LEVEL_MARGIN; // 160px высота дорожки + отступы
  const centerX = (levelData.minX + levelData.maxX) / 2;
  const centerY = (levelData.minY + levelData.maxY) / 2;

  return (
    <pixiGraphics
      x={centerX}
      y={centerY}
      interactive={true}
      cursor="pointer"
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      draw={(g: Graphics) => {
        g.clear()
          .rect(
            -width / 2, 
            -height / 2, 
            width, 
            height
          )
          .fill({
            color: levelData.color,
            alpha: isHovered ? LEVEL_ALPHA_HOVER : LEVEL_ALPHA
          })
          .stroke({ 
            color: LEVEL_BORDER_COLOR, 
            width: LEVEL_BORDER_WIDTH
          });
      }}
    />
  );
} 