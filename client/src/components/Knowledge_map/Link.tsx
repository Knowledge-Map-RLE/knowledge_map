import type { ReactNode } from 'react';
import { extend } from '@pixi/react';
import { Container, Graphics, FederatedPointerEvent } from 'pixi.js';
import type { BlockData, LinkData } from './index';

extend({ Container, Graphics });

const BLOCK_WIDTH = 200;
const BLOCK_HEIGHT = 120;
const ARROW_SIZE = 12;
const LINK_COLOR = 0x8b5cf6; // Фиолетовый цвет
const SELECTED_LINK_COLOR = 0x3b82f6;

interface LinkProps {
  linkData: LinkData;
  fromBlock: BlockData;
  toBlock: BlockData;
  isSelected?: boolean;
  onLinkClick?: (linkId: string) => void;
}

export function Link({ 
  linkData, 
  fromBlock, 
  toBlock, 
  isSelected = false,
  onLinkClick 
}: LinkProps): ReactNode {
  
  const handleLinkClick = (event: FederatedPointerEvent) => {
    event.stopPropagation();
    
    if (onLinkClick) {
      onLinkClick(linkData.id);
    }
  };

  // Вычисляем точки подключения - связи автоматически следуют за блоками
  const getConnectionPoints = () => {
    const fromX = fromBlock.x;
    const fromY = fromBlock.y;
    const toX = toBlock.x;
    const toY = toBlock.y;

    let startX: number, startY: number, endX: number, endY: number;

    // Определяем направление связи
    if (Math.abs(fromX - toX) > Math.abs(fromY - toY)) {
      // Горизонтальная связь
      if (fromX < toX) {
        startX = fromX + BLOCK_WIDTH / 2;
        startY = fromY;
        endX = toX - BLOCK_WIDTH / 2;
        endY = toY;
      } else {
        startX = fromX - BLOCK_WIDTH / 2;
        startY = fromY;
        endX = toX + BLOCK_WIDTH / 2;
        endY = toY;
      }
    } else {
      // Вертикальная связь
      if (fromY < toY) {
        startX = fromX;
        startY = fromY + BLOCK_HEIGHT / 2;
        endX = toX;
        endY = toY - BLOCK_HEIGHT / 2;
      } else {
        startX = fromX;
        startY = fromY - BLOCK_HEIGHT / 2;
        endX = toX;
        endY = toY + BLOCK_HEIGHT / 2;
      }
    }

    return { startX, startY, endX, endY };
  };

  // Вычисляем координаты стрелки
  const getArrowPoints = (endX: number, endY: number, startX: number, startY: number) => {
    const angle = Math.atan2(endY - startY, endX - startX);
    
    const arrowX1 = endX - ARROW_SIZE * Math.cos(angle - Math.PI / 6);
    const arrowY1 = endY - ARROW_SIZE * Math.sin(angle - Math.PI / 6);
    
    const arrowX2 = endX - ARROW_SIZE * Math.cos(angle + Math.PI / 6);
    const arrowY2 = endY - ARROW_SIZE * Math.sin(angle + Math.PI / 6);

    return { arrowX1, arrowY1, arrowX2, arrowY2 };
  };

  return (
    <pixiContainer>
      <pixiGraphics
        interactive={!!onLinkClick}
        cursor="pointer"
        onPointerDown={onLinkClick ? handleLinkClick : undefined}
        draw={(g: Graphics) => {
          const { startX, startY, endX, endY } = getConnectionPoints();
          const { arrowX1, arrowY1, arrowX2, arrowY2 } = getArrowPoints(endX, endY, startX, startY);

          const color = isSelected ? SELECTED_LINK_COLOR : LINK_COLOR;
          const width = isSelected ? 4 : 2;

          g.clear()
            // Основная линия
            .moveTo(startX, startY)
            .lineTo(endX, endY)
            .stroke({ color: color, width: width })
            
            // Стрелка
            .moveTo(endX, endY)
            .lineTo(arrowX1, arrowY1)
            .lineTo(arrowX2, arrowY2)
            .closePath()
            .fill(color);
        }}
      />
    </pixiContainer>
  );
} 