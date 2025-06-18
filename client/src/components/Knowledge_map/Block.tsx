import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';
import type { BlockData } from './types';

extend({ Graphics });

export interface BlockProps {
  blockData: BlockData;
  isSelected: boolean;
  onClick: () => void;
}

export function Block({ blockData, isSelected, onClick }: BlockProps) {
  const { x, y, text } = blockData;

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(isSelected ? 0xffff00 : 0xffffff);
    g.lineStyle(2, isSelected ? 0xff0000 : 0x000000);
    g.drawRect(-50, -25, 100, 50);
    g.endFill();
  }, [isSelected]);

  return (
    <pixiContainer x={x} y={y}>
      <pixiGraphics draw={draw} eventMode="static" onClick={onClick} />
      <pixiText
        text={text}
        anchor={0.5}
        style={{
          fontSize: 14,
          fill: '#000000',
        }}
      />
    </pixiContainer>
  );
}