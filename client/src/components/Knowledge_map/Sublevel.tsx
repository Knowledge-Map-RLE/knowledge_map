import { Graphics, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState } from 'react';
import { SUBLEVEL_PADDING } from './constants';
import { Block } from './Block';
import type { BlockData, SublevelData } from './types';

extend({ Graphics, Text });

interface Props {
  sublevelData: SublevelData;
  blocks?: BlockData[];
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
  onBlockClick?: (blockId: string) => void;
  onBlockHover?: (block: BlockData | null) => void;
  selectedBlocks?: string[];
}

export function Sublevel({
  sublevelData,
  blocks = [],
  onSublevelHover,
  onSublevelClick,
  onBlockClick,
  onBlockHover,
  selectedBlocks = []
}: Props) {
  const { min_x, max_x, min_y, max_y, color, block_ids, id, level } = sublevelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.beginFill(color, isHovered ? 0.6 : 0.4);
    g.lineStyle(2, color, isHovered ? 0.8 : 0.6);
    g.drawRect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.endFill();
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const sublevelBlocks = blocks.filter(block => block_ids.includes(block.id));

  const adjustedBlocks = sublevelBlocks.map(block => ({
    ...block,
    x: block.x + SUBLEVEL_PADDING,
    y: min_y + (max_y - min_y) / 2
  }));

  return (
    <container sortableChildren={true}>
      <graphics
        draw={draw}
        eventMode="static"
        onMouseEnter={() => {
          setIsHovered(true);
          onSublevelHover?.(sublevelData);
        }}
        onMouseLeave={() => {
          setIsHovered(false);
          onSublevelHover?.(null);
        }}
        onMouseDown={() => onSublevelClick?.(sublevelData.id, (min_x + max_x) / 2, min_y)}
        zIndex={1}
      />
      <pixiText
        text={`ур: ${level}, пур: ${id}`}
        x={min_x + 10}
        y={min_y + 10}
        style={{
          fontSize: 12,
          fill: '#' + color.toString(16).padStart(6, '0'),
          fontWeight: 'bold'
        }}
        zIndex={2}
      />
      <container zIndex={3}>
        {adjustedBlocks.map((block) => (
          <Block
            key={block.id}
            blockData={block}
            isSelected={selectedBlocks.includes(block.id)}
            onClick={() => onBlockClick?.(block.id)}
          />
        ))}
      </container>
    </container>
  );
} 