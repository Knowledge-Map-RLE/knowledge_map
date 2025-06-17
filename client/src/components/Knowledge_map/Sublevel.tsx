import { useState } from 'react';
import { Graphics, FederatedPointerEvent } from 'pixi.js';
import { extend } from '@pixi/react';
import type { ReactNode } from 'react';

extend({ Graphics });

export interface SublevelData {
  id: number;
  y: number;
  blockIds: string[];
  minX: number;
  maxX: number;
  color: number;
  levelId: number;
}

interface SublevelProps {
  sublevelData: SublevelData;
  onSublevelHover?: (sublevelId: number, isHovered: boolean) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
}

const SUBLEVEL_ALPHA = 0.3;
const SUBLEVEL_ALPHA_HOVER = 0.5;
const SUBLEVEL_HEIGHT = 160; // Высота дорожки подуровня в пикселях
const SUBLEVEL_BORDER_WIDTH = 1;
const SUBLEVEL_BORDER_COLOR = 0x6b7280; // gray

export function Sublevel({ 
  sublevelData, 
  onSublevelHover, 
  onSublevelClick 
}: SublevelProps): ReactNode {
  const [isHovered, setIsHovered] = useState(false);

  const handlePointerEnter = () => {
    setIsHovered(true);
    onSublevelHover?.(sublevelData.id, true);
  };

  const handlePointerLeave = () => {
    setIsHovered(false);
    onSublevelHover?.(sublevelData.id, false);
  };

  const handlePointerDown = (event: FederatedPointerEvent) => {
    // Останавливаем всплытие события
    event.stopPropagation();
    
    if (!onSublevelClick) return;
    
    // Получаем локальные координаты клика относительно подуровня
    const localX = event.global.x - (sublevelData.minX + sublevelData.maxX) / 2;
    const worldX = (sublevelData.minX + sublevelData.maxX) / 2 + localX;
    
    onSublevelClick(sublevelData.id, worldX, sublevelData.y);
  };

  const width = sublevelData.maxX - sublevelData.minX;
  const centerX = (sublevelData.minX + sublevelData.maxX) / 2;

  return (
    <pixiGraphics
      x={centerX}
      y={sublevelData.y}
      interactive={true}
      cursor="pointer"
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      onPointerDown={handlePointerDown}
      draw={(g: Graphics) => {
        g.clear()
          .rect(
            -width / 2, 
            -SUBLEVEL_HEIGHT / 2, 
            width, 
            SUBLEVEL_HEIGHT
          )
          .fill({
            color: sublevelData.color,
            alpha: isHovered ? SUBLEVEL_ALPHA_HOVER : SUBLEVEL_ALPHA
          })
          .stroke({ 
            color: SUBLEVEL_BORDER_COLOR, 
            width: SUBLEVEL_BORDER_WIDTH
          });
      }}
    />
  );
} 