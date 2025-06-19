import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useEffect } from 'react';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';

extend({ Graphics });

export interface BlockPreviewProps {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  isLeftArrow: boolean;
  zIndex?: number;
}

export function BlockPreview({ sourceX, sourceY, targetX, targetY, isLeftArrow, zIndex }: BlockPreviewProps) {
  useEffect(() => {
    console.log('BlockPreview mounted with coords:', { sourceX, sourceY, targetX, targetY, isLeftArrow });
  }, [sourceX, sourceY, targetX, targetY, isLeftArrow]);

  const draw = useCallback((g: Graphics) => {
    console.log('BlockPreview draw called');
    g.clear();
    
    // Рисуем тень для блока
    g.beginFill(0x000000, 0.1);
    g.drawRoundedRect(
      targetX - BLOCK_WIDTH/2 + 4,
      targetY - BLOCK_HEIGHT/2 + 4,
      BLOCK_WIDTH,
      BLOCK_HEIGHT,
      10
    );
    g.endFill();
    
    // Рисуем предварительный просмотр блока
    g.lineStyle(2, 0x2196F3, 0.6);
    g.beginFill(0xFFFFFF, 0.5);
    g.drawRoundedRect(
      targetX - BLOCK_WIDTH/2,
      targetY - BLOCK_HEIGHT/2,
      BLOCK_WIDTH,
      BLOCK_HEIGHT,
      10
    );
    g.endFill();

    // Рисуем предварительный просмотр связи
    g.lineStyle(3, 0x2196F3, 0.6);
    if (isLeftArrow) {
      // Связь от нового блока к текущему
      g.moveTo(targetX + BLOCK_WIDTH/2, targetY);
      g.lineTo(sourceX - BLOCK_WIDTH/2, sourceY);
    } else {
      // Связь от текущего блока к новому
      g.moveTo(sourceX + BLOCK_WIDTH/2, sourceY);
      g.lineTo(targetX - BLOCK_WIDTH/2, targetY);
    }

    // Рисуем стрелку на конце связи
    const angle = Math.atan2(
      targetY - sourceY,
      targetX - sourceX
    );
    const arrowLength = 15;
    const endX = isLeftArrow ? sourceX - BLOCK_WIDTH/2 : targetX - BLOCK_WIDTH/2;
    const endY = isLeftArrow ? sourceY : targetY;

    g.lineStyle(3, 0x2196F3, 0.6);
    g.moveTo(
      endX,
      endY
    );
    g.lineTo(
      endX - arrowLength * Math.cos(angle - Math.PI/6),
      endY - arrowLength * Math.sin(angle - Math.PI/6)
    );
    g.moveTo(
      endX,
      endY
    );
    g.lineTo(
      endX - arrowLength * Math.cos(angle + Math.PI/6),
      endY - arrowLength * Math.sin(angle + Math.PI/6)
    );

    // Добавляем текст "Новый блок"
    g.lineStyle(0);
    g.beginFill(0x000000, 0.6);
    g.drawRoundedRect(
      targetX - 40,
      targetY - 8,
      80,
      16,
      5
    );
    g.endFill();
  }, [sourceX, sourceY, targetX, targetY, isLeftArrow]);

  return (
    <container zIndex={zIndex}>
      <pixiGraphics
        draw={draw}
        eventMode="none"
      />
      <pixiText
        text="Новый блок"
        x={targetX}
        y={targetY}
        anchor={0.5}
        style={{
          fontSize: 14,
          fill: '#000000',
          fontWeight: 'bold'
        }}
      />
    </container>
  );
} 