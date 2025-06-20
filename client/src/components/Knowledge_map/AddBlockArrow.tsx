import { Graphics, Rectangle } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';
import { BLOCK_WIDTH } from './constants';

extend({ Graphics });

export interface AddBlockArrowProps {
  position: 'left' | 'right';
  onHover: () => void;
  onHoverEnd: () => void;
  onClick: () => void;
  isHovered: boolean;
  zIndex?: number;
}

export function AddBlockArrow({ position, onHover, onHoverEnd, onClick, isHovered, zIndex }: AddBlockArrowProps) {
  const draw = useCallback((g: Graphics) => {
    g.clear();

    // Параметры стрелки
    const arrowWidth = 30;
    const arrowHeight = 20;
    const arrowOffset = position === 'left' ? -BLOCK_WIDTH/2 - 10 : BLOCK_WIDTH/2 + 10;
    const fillColor = isHovered ? 0x4CAF50 : 0x2196F3;
    const alpha = isHovered ? 1 : 0.8;

    // Размеры фонового прямоугольника
    const bgWidth = arrowWidth + 20;
    const bgHeight = arrowHeight + 20;
    const bgX = position === 'left' ? arrowOffset - arrowWidth - 10 : arrowOffset;
    const bgY = -bgHeight/2;

    // Рисуем белый фон с использованием нового API
    g.rect(bgX, bgY, bgWidth, bgHeight).fill({ color: 0xFFFFFF, alpha: 1 });
    
    // Рисуем стрелку
    const path = [];
    if (position === 'left') {
      // Стрелка слева (указывает вправо)
      path.push(arrowOffset, 0, arrowOffset - arrowWidth, -arrowHeight/2, arrowOffset - arrowWidth, arrowHeight/2);
    } else {
      // Стрелка справа (указывает вправо)
      path.push(arrowOffset + arrowWidth, 0, arrowOffset, -arrowHeight/2, arrowOffset, arrowHeight/2);
    }
    g.poly(path).fill({ color: fillColor, alpha });

    // Устанавливаем hitArea больше, чем видимая область
    const hitAreaWidth = bgWidth + 20;
    const hitAreaHeight = bgHeight + 20;
    const hitAreaX = position === 'left' ? arrowOffset - arrowWidth - 20 : arrowOffset - 10;
    const hitAreaY = -hitAreaHeight/2;
    
    // Используем Rectangle для hitArea
    g.hitArea = new Rectangle(hitAreaX, hitAreaY, hitAreaWidth, hitAreaHeight);
  }, [position, isHovered]);

  return (
    <pixiGraphics
      draw={draw}
      eventMode="static"
      cursor="pointer"
      onMouseEnter={onHover}
      onMouseLeave={onHoverEnd}
      onClick={onClick}
      zIndex={zIndex}
    />
  );
} 