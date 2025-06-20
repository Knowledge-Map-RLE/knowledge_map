import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect, useRef } from 'react';
import type { LinkData, BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import { gsap } from 'gsap';

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

  // Состояние для анимируемых точек
  const [animatedPoints, setAnimatedPoints] = useState({
    source_x: 0,
    source_y: 0,
    target_x: 0,
    target_y: 0,
  });

  const isInitialRender = useRef(true);

  // Эффект для анимации
  useEffect(() => {
    if (!source_block || !target_block) return;

    const source_point = {
      x: source_block.x + BLOCK_WIDTH / 2,
      y: source_block.y - BLOCK_HEIGHT,
    };
    const target_point = {
      x: target_block.x - BLOCK_WIDTH / 2,
      y: target_block.y - BLOCK_HEIGHT,
    };

    if (isInitialRender.current) {
      setAnimatedPoints({
        source_x: source_point.x,
        source_y: source_point.y,
        target_x: target_point.x,
        target_y: target_point.y,
      });
      isInitialRender.current = false;
    } else {
      gsap.to(animatedPoints, {
        source_x: source_point.x,
        source_y: source_point.y,
        target_x: target_point.x,
        target_y: target_point.y,
        duration: 0.8,
        ease: 'power3.inOut',
        onUpdate: () => {
          setAnimatedPoints({ ...animatedPoints });
        },
      });
    }
  }, [source_block?.x, source_block?.y, target_block?.x, target_block?.y]);


  const draw = useCallback((g: Graphics) => {
    if (!source_block || !target_block || isInitialRender.current) {
      g.clear();
      return;
    }

    const { source_x, source_y, target_x, target_y } = animatedPoints;
    
    // Цвета и параметры
    const lineColor = isSelected ? 0xff0000 : 0x8a2be2; // BlueViolet для неактивных линий
    const lineWidth = 5;

    // Рисуем основную линию
    g.clear();
    g.moveTo(source_x, source_y);
    g.lineTo(target_x, target_y);
    g.stroke({ width: lineWidth, color: lineColor });

    // Рисуем стрелку
    const arrowLength = 15;
    const arrowAngle = Math.PI / 6;

    const dx = target_x - source_x;
    const dy = target_y - source_y;
    const lineAngle = Math.atan2(dy, dx);

    const arrowPoint1 = {
      x: target_x - arrowLength * Math.cos(lineAngle + arrowAngle),
      y: target_y - arrowLength * Math.sin(lineAngle + arrowAngle)
    };

    const arrowPoint2 = {
      x: target_x - arrowLength * Math.cos(lineAngle - arrowAngle),
      y: target_y - arrowLength * Math.sin(lineAngle - arrowAngle)
    };

    // Рисуем стрелку
    g.moveTo(target_x, target_y);
    g.lineTo(arrowPoint1.x, arrowPoint1.y);
    g.lineTo(arrowPoint2.x, arrowPoint2.y);
    g.closePath();
    g.fill(lineColor);
  }, [animatedPoints, isSelected, source_block, target_block]);

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