import { Graphics, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState } from 'react';
import { Block } from './Block';
import type { BlockData, SublevelData, EditMode } from './types';
import { EditMode as EditModeEnum } from './types';

extend({ Graphics, Text });

interface Props {
  sublevelData: SublevelData;
  blocks?: BlockData[];
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick?: (sublevelId: number, x: number, y: number) => void;
  onBlockClick?: (blockId: string) => void;
  onBlockHover?: (block: BlockData | null) => void;
  selectedBlocks?: string[];
  currentMode?: EditMode;
  onAddBlock?: (sourceBlock: BlockData, targetLevel: number) => void;
}

export function Sublevel({
  sublevelData,
  blocks = [],
  onSublevelHover,
  onSublevelClick,
  onBlockClick,
  onBlockHover,
  selectedBlocks = [],
  currentMode = EditModeEnum.SELECT,
  onAddBlock = () => {}
}: Props) {
  const { min_x, max_x, min_y, max_y, color, block_ids, id, level } = sublevelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.rect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.stroke({width: 2, color: color, alpha: isHovered ? 0.8 : 0.6});
    g.fill({color, alpha: isHovered ? 0.6 : 0.4});
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const sublevelBlocks = blocks.filter(block => block_ids.includes(block.id));

  const adjustedBlocks = sublevelBlocks.map(block => ({
    ...block,
    x: block.x,
    y: (min_y + max_y) / 2
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
      />
      <pixiText
        text={`Подуровень: ${id}`}
        x={min_x + 10}
        y={min_y + 10}
        style={{
          fontSize: 12,
          fill: color,
          fontWeight: 'bold'
        }}
      />
      <container>
        {adjustedBlocks.map((block) => (
          <Block
            key={block.id}
            blockData={block}
            isSelected={selectedBlocks.includes(block.id)}
            onClick={() => onBlockClick?.(block.id)}
            currentMode={currentMode}
            onAddBlock={onAddBlock}
          />
        ))}
      </container>
    </container>
  );
} 