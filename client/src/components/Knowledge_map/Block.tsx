import { Graphics } from 'pixi.js';
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
  const { x, y, text } = blockData;

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(isSelected ? 0xffff00 : 0xffffff);
    g.lineStyle(2, isSelected ? 0xff0000 : 0x000000);
    g.drawRect(-BLOCK_WIDTH/2, -BLOCK_HEIGHT/2, BLOCK_WIDTH, BLOCK_HEIGHT);
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
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 10,
        }}
      />
    </pixiContainer>
  );
}