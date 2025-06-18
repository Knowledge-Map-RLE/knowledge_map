import { Graphics, Rectangle } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback } from 'react';
import type { LinkData, BlockData } from './types';

extend({ Graphics });

export interface LinkProps {
  linkData: LinkData;
  blocks: BlockData[];
  isSelected: boolean;
  onClick: () => void;
}

export function Link({ linkData, blocks, isSelected, onClick }: LinkProps) {
  const fromBlock = blocks.find(block => block.id === linkData.fromId);
  const toBlock = blocks.find(block => block.id === linkData.toId);

  const draw = useCallback((g: Graphics) => {
    if (!fromBlock || !toBlock) return;

    g.clear();
    g.lineStyle(2, isSelected ? 0xff0000 : 0x000000, 1);
    g.moveTo(fromBlock.x, fromBlock.y);
    g.lineTo(toBlock.x, toBlock.y);
  }, [fromBlock, toBlock, isSelected]);

  if (!fromBlock || !toBlock) return null;

  const hitArea = new Rectangle(
    Math.min(fromBlock.x, toBlock.x) - 5,
    Math.min(fromBlock.y, toBlock.y) - 5,
    Math.abs(toBlock.x - fromBlock.x) + 10,
    Math.abs(toBlock.y - fromBlock.y) + 10
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