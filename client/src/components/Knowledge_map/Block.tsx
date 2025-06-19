import { Graphics, Rectangle } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';
import type { BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';

extend({ Graphics });

export interface BlockProps {
  blockData: BlockData;
  isSelected: boolean;
  onClick: () => void;
}

export function Block({ blockData, isSelected, onClick }: BlockProps) {
  const { x, y, text, level, sublevel } = blockData;

  const draw = useCallback((g: Graphics) => {
    g.clear();

    // Цвета и параметры
    const fillColor = isSelected ? 0xffffff : 0xffffff; // Всегда белая заливка
    const borderColor = isSelected ? 0x0000ff : 0x000000; // Синий для выделенного, черный для обычного
    const borderWidth = isSelected ? 3 : 2; // Чуть толще рамка для выделенного блока
    const cornerRadius = 10;

    // Рисуем блок с закругленными углами
    g.lineStyle(borderWidth, borderColor);
    g.beginFill(fillColor);
    g.drawRoundedRect(-BLOCK_WIDTH/2, -BLOCK_HEIGHT/2, BLOCK_WIDTH, BLOCK_HEIGHT, cornerRadius);
    g.endFill();
  }, [isSelected]);

  const hitArea = new Rectangle(-BLOCK_WIDTH/2, -BLOCK_HEIGHT/2, BLOCK_WIDTH, BLOCK_HEIGHT);

  return (
    <pixiContainer x={x} y={y}>
      <pixiGraphics 
        draw={draw} 
        eventMode="static" 
        onClick={onClick}
        hitArea={hitArea}
        cursor="pointer"
      />
      <pixiText
        text={text}
        anchor={0.5}
        eventMode="none"
        style={{
          fontSize: 14,
          fill: '#000000',
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 20, // Увеличиваем отступы по бокам
          breakWords: true,
          align: 'center',
          lineHeight: 16, // Устанавливаем высоту строки
        }}
      />
      <pixiText
        text={`ур: ${level}, пур: ${sublevel}`}
        x={-BLOCK_WIDTH/2 + 5}
        y={-BLOCK_HEIGHT/2 + 5}
        eventMode="none"
        style={{
          fontSize: 10,
          fill: '#666666',
        }}
      />
    </pixiContainer>
  );
}