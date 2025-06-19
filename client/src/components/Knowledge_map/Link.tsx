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
  const fromBlock = blocks.find(block => block.id === linkData.source_id);
  const toBlock = blocks.find(block => block.id === linkData.target_id);

  console.log('Rendering link:', linkData);
  console.log('From block:', fromBlock);
  console.log('To block:', toBlock);

  const draw = useCallback((g: Graphics) => {
    if (!fromBlock || !toBlock) {
      console.log('Missing blocks for link:', linkData);
      return;
    }

    // Находим точки соединения на краях блоков
    // x координата блока - это его центр
    const fromPoint = {
      x: fromBlock.x + BLOCK_WIDTH/2, // Правая сторона исходного блока
      y: fromBlock.y // Центр по вертикали
    };

    const toPoint = {
      x: toBlock.x - BLOCK_WIDTH/2, // Левая сторона целевого блока
      y: toBlock.y // Центр по вертикали
    };

    console.log('Link points:', {
      from: { ...fromPoint, blockY: fromBlock.y, blockHeight: BLOCK_HEIGHT },
      to: { ...toPoint, blockY: toBlock.y, blockHeight: BLOCK_HEIGHT }
    });

    // Цвета и параметры
    const lineColor = isSelected ? 0xff0000 : 0x8a2be2; // BlueViolet для неактивных линий
    const lineWidth = 5;

    g.clear();

    // Рисуем основную линию
    g.lineStyle(lineWidth, lineColor, 1.0);
    g.moveTo(fromPoint.x, fromPoint.y);
    g.lineTo(toPoint.x, toPoint.y);

    // Рисуем стрелку
    const arrowLength = 15;
    const arrowAngle = Math.PI / 6;

    const dx = toPoint.x - fromPoint.x;
    const dy = toPoint.y - fromPoint.y;
    const lineAngle = Math.atan2(dy, dx);

    const arrowPoint1 = {
      x: toPoint.x - arrowLength * Math.cos(lineAngle + arrowAngle),
      y: toPoint.y - arrowLength * Math.sin(lineAngle + arrowAngle)
    };

    const arrowPoint2 = {
      x: toPoint.x - arrowLength * Math.cos(lineAngle - arrowAngle),
      y: toPoint.y - arrowLength * Math.sin(lineAngle - arrowAngle)
    };

    // Рисуем стрелку
    g.beginFill(lineColor);
    g.lineStyle(lineWidth, lineColor, 1.0);
    g.moveTo(toPoint.x, toPoint.y);
    g.lineTo(arrowPoint1.x, arrowPoint1.y);
    g.lineTo(arrowPoint2.x, arrowPoint2.y);
    g.closePath();
    g.endFill();

    console.log('Link drawn with color:', lineColor.toString(16));

  }, [fromBlock, toBlock, isSelected]);

  if (!fromBlock || !toBlock) {
    console.log('Cannot render link:', linkData, 'Missing blocks');
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