import { Graphics, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect } from 'react';
import { Sublevel } from './Sublevel';
import type { BlockData, SublevelData, LevelData as LevelDataType } from './types';
import { LEVEL_PADDING } from './constants';
import { Block } from './Block';
import { EditMode } from './types';

extend({ Graphics, Container });

interface LevelProps {
  levelData: LevelDataType;
  sublevels: SublevelData[];
  blocks: BlockData[];
  onLevelHover?: (level: LevelDataType | null) => void;
  onSublevelHover?: (sublevel: SublevelData | null) => void;
  onSublevelClick: (sublevelId: number, x: number, y: number) => void;
  onBlockClick: (blockId: string) => void;
  onBlockHover?: (block: BlockData | null) => void;
  selectedBlocks: string[];
  currentMode: EditMode;
  onAddBlock: (sourceBlock: BlockData, targetLevel: number) => void;
}

export function Level({ 
  levelData, 
  sublevels, 
  blocks = [], 
  onLevelHover, 
  onSublevelHover, 
  onSublevelClick,
  onBlockClick,
  onBlockHover,
  selectedBlocks = [],
  currentMode,
  onAddBlock
}: LevelProps) {
  useEffect(() => {
    console.log('Level received currentMode:', currentMode);
  }, [currentMode]);

  const { min_x, max_x, min_y, max_y, color, sublevel_ids, id } = levelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.rect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.fill({color: color, alpha: isHovered ? 0.6 : 0.4});
    g.stroke({width: 2, color: color, alpha: isHovered ? 0.8 : 0.6});
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const levelSublevels = sublevels.filter(sublevel => sublevel_ids.includes(sublevel.id));
  const levelBlocks = blocks.filter(block => block.level === levelData.id);

  // Рассчитываем общую высоту всех подуровней
  const totalHeight = levelSublevels.reduce((total, sublevel) => 
    total + (sublevel.max_y - sublevel.min_y), 0);

  // Вычисляем начальную Y-координату для центрирования группы подуровней
  const levelHeight = max_y - min_y;
  let currentY = min_y + (levelHeight - totalHeight) / 2;

  const adjustedSublevels = levelSublevels.map(sublevel => {
    const sublevelHeight = sublevel.max_y - sublevel.min_y;
    const adjusted = {
      ...sublevel,
      min_x: sublevel.min_x,
      max_x: sublevel.max_x,
      min_y: currentY,
      max_y: currentY + sublevelHeight
    };
    currentY += sublevelHeight + LEVEL_PADDING;
    return adjusted;
  });

  return (
    <container sortableChildren={true}>
      <graphics
        draw={draw}
        eventMode="static"
        onMouseEnter={() => {
          setIsHovered(true);
          onLevelHover?.(levelData);
        }}
        onMouseLeave={() => {
          setIsHovered(false);
          onLevelHover?.(null);
        }}
        zIndex={1}
      />
      <pixiText
        text={`Уровень: ${id}`}
        x={min_x + 10}
        y={min_y + 10}
        style={{
          fontSize: 14,
          fill: color,
          fontWeight: 'bold'
        }}
      />
      <container zIndex={2}>
        {adjustedSublevels.map((sublevel) => (
          <Sublevel
            key={sublevel.id}
            sublevelData={sublevel}
            blocks={blocks}
            onSublevelHover={onSublevelHover}
            onSublevelClick={onSublevelClick}
            onBlockClick={onBlockClick}
            onBlockHover={onBlockHover}
            selectedBlocks={selectedBlocks}
            currentMode={currentMode}
            onAddBlock={onAddBlock}
          />
        ))}
      </container>
      <container zIndex={3}>
        {levelBlocks.map((block) => (
          <Block
            key={block.id}
            blockData={block}
            isSelected={selectedBlocks.includes(block.id)}
            onClick={() => onBlockClick(block.id)}
            currentMode={currentMode}
            onAddBlock={onAddBlock}
          />
        ))}
      </container>
    </container>
  );
} 