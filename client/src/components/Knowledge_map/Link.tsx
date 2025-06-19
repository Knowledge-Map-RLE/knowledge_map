import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';
import type { LinkData, BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';

extend({ Graphics });

export interface LinkProps {
  linkData: LinkData;
  blocks: BlockData[];
  isSelected: boolean;
  onClick: () => void;
}

export function Link({ linkData, blocks, isSelected, onClick }: LinkProps) {
  const source_block = blocks.find(block => block.id === linkData.source_id);
  const target_block = blocks.find(block => block.id === linkData.target_id);

  const draw = useCallback((g: Graphics) => {
    if (!source_block || !target_block) {
      return;
    }

    // Находим точки соединения на краях блоков
    // x координата блока - это его центр
    const source_point = {
      x: source_block.x + BLOCK_WIDTH/2, // Правая сторона исходного блока
      y: source_block.y - BLOCK_HEIGHT // Центр по вертикали
    };

    const target_point = {
      x: target_block.x - BLOCK_WIDTH/2, // Левая сторона целевого блока
      y: target_block.y - BLOCK_HEIGHT // Центр по вертикали
    };

    // Цвета и параметры
    const lineColor = isSelected ? 0xff0000 : 0x8a2be2; // BlueViolet для неактивных линий
    const lineWidth = 5;

    
    // Рисуем основную линию
    g.clear();
    g.moveTo(source_point.x, source_point.y);
    g.lineTo(target_point.x, target_point.y);
    g.stroke({ width: lineWidth, color: lineColor});

    // Рисуем стрелку
    const arrowLength = 15;
    const arrowAngle = Math.PI / 6;

    const dx = target_point.x - source_point.x;
    const dy = target_point.y - source_point.y;
    const lineAngle = Math.atan2(dy, dx);

    const arrowPoint1 = {
      x: target_point.x - arrowLength * Math.cos(lineAngle + arrowAngle),
      y: target_point.y - arrowLength * Math.sin(lineAngle + arrowAngle)
    };

    const arrowPoint2 = {
      x: target_point.x - arrowLength * Math.cos(lineAngle - arrowAngle),
      y: target_point.y - arrowLength * Math.sin(lineAngle - arrowAngle)
    };

    // Рисуем стрелку
    g.moveTo(target_point.x, target_point.y);
    g.lineTo(arrowPoint1.x, arrowPoint1.y);
    g.lineTo(arrowPoint2.x, arrowPoint2.y);
    g.closePath();
    g.fill(lineColor);
  }, [source_block, target_block, isSelected]);

  if (!source_block || !target_block) {
    return null;
  }

  return (
    <pixiGraphics
      draw={draw}
      eventMode="static"
      cursor="pointer"
      onClick={onClick}
    />
  );
} 