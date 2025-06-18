import { Graphics, Rectangle } from 'pixi.js';
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

  const draw = useCallback((g: Graphics) => {
    if (!fromBlock || !toBlock) return;

    // Находим центры блоков
    const fromCenter = { x: fromBlock.x, y: fromBlock.y };
    const toCenter = { x: toBlock.x, y: toBlock.y };

    // Определяем точки соединения на краях блоков
    const fromPoint = {
      x: fromCenter.x + BLOCK_WIDTH / 2, // Правый край исходного блока
      y: fromCenter.y // Центр по вертикали
    };

    const toPoint = {
      x: toCenter.x - BLOCK_WIDTH / 2, // Левый край целевого блока
      y: toCenter.y // Центр по вертикали
    };

    // Цвета для линий и стрелок
    const linkColor = isSelected ? 0xff0000 : 0x8a2be2; // BlueViolet цвет для неактивных линий
    const linkAlpha = 1.0; // Полная непрозрачность

    // Рисуем линию
    g.clear();
    g.lineStyle(6, linkColor, linkAlpha);
    g.moveTo(fromPoint.x, fromPoint.y);
    g.lineTo(toPoint.x, toPoint.y);
    g.endFill();

    // Рисуем стрелку
    const arrowLength = 20;
    const arrowAngle = Math.PI / 6; // 30 градусов

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

    // Рисуем стрелку с заливкой
    g.beginFill(linkColor, linkAlpha);
    g.lineStyle(0);
    g.moveTo(toPoint.x, toPoint.y);
    g.lineTo(arrowPoint1.x, arrowPoint1.y);
    g.lineTo(arrowPoint2.x, arrowPoint2.y);
    g.closePath();
    g.endFill();
  }, [fromBlock, toBlock, isSelected]);

  if (!fromBlock || !toBlock) return null;

  const hitArea = new Rectangle(
    Math.min(fromBlock.x, toBlock.x) - 10,
    Math.min(fromBlock.y, toBlock.y) - 10,
    Math.abs(toBlock.x - fromBlock.x) + 20,
    Math.abs(toBlock.y - fromBlock.y) + 20
  );

  return (
    <pixiGraphics
      draw={draw}
      eventMode="static"
      onClick={onClick}
      hitArea={hitArea}
    />
  );
} 