import { Graphics, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect } from 'react';
import { Sublevel } from './Sublevel';
import type { BlockData, SublevelData, LevelData as LevelDataType } from './types';
import { LEVEL_PADDING, SUBLEVEL_PADDING, BLOCK_HEIGHT } from './constants';
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
  onBlockPointerDown: (blockId: string, event: any) => void;
  onBlockMouseEnter: (blockId: string) => void;
  onBlockMouseLeave: (blockId: string, event: any) => void;
  onArrowHover: (blockId: string, arrowPosition: 'left' | 'right' | null) => void;
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
  onAddBlock,
  onBlockPointerDown,
  onBlockMouseEnter,
  onBlockMouseLeave,
  onArrowHover
}: LevelProps) {
  const { min_x, max_x, min_y, max_y, color, id } = levelData;
  const [isHovered, setIsHovered] = useState(false);

  const draw = useCallback((g: Graphics) => {
    g.clear();
    g.rect(min_x, min_y, max_x - min_x, max_y - min_y);
    g.fill({color: color, alpha: isHovered ? 0.6 : 0.4});
    g.stroke({width: 2, color: color, alpha: isHovered ? 0.8 : 0.6});
  }, [min_x, max_x, min_y, max_y, color, isHovered]);

  const levelSublevels = sublevels.filter(sublevel => sublevel.level_id === id);

  // Рассчитываем общую высоту всех подуровней с учетом отступов
  const totalHeight = levelSublevels.length * BLOCK_HEIGHT + 
    (levelSublevels.length - 1) * SUBLEVEL_PADDING;

  // Вычисляем начальную Y-координату для центрирования группы подуровней
  const levelHeight = max_y - min_y;
  let currentY = min_y + (levelHeight - totalHeight) / 2;

  const adjustedSublevels = levelSublevels.map((sublevel, index) => {
    const adjusted = {
      ...sublevel,
      min_x: min_x + LEVEL_PADDING,
      max_x: max_x - LEVEL_PADDING,
      min_y: currentY,
      max_y: currentY + BLOCK_HEIGHT
    };
    // Добавляем SUBLEVEL_PADDING только между подуровнями
    currentY += BLOCK_HEIGHT + (index < levelSublevels.length - 1 ? SUBLEVEL_PADDING : 0);
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
            onBlockPointerDown={onBlockPointerDown}
            onBlockMouseEnter={onBlockMouseEnter}
            onBlockMouseLeave={onBlockMouseLeave}
            onArrowHover={onArrowHover}
          />
        ))}
      </container>
    </container>
  );
} 