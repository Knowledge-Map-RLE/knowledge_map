import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useState, useEffect } from 'react';
import type { BlockData, EditMode } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import { AddBlockArrow } from './AddBlockArrow';
import { BlockPreview } from './BlockPreview';
import { EditMode as EditModeEnum } from './types';

extend({ Graphics });

interface BlockProps {
  blockData: BlockData;
  isSelected: boolean;
  onClick: () => void;
  onAddBlock: (sourceBlock: BlockData, targetLevel: number) => void;
  currentMode: EditMode;
}

export function Block({ blockData, isSelected, onClick, onAddBlock, currentMode }: BlockProps) {
  const { x, y, text, level } = blockData;
  const [isHovered, setIsHovered] = useState(false);
  const [hoveredArrow, setHoveredArrow] = useState<'left' | 'right' | null>(null);

  useEffect(() => {
    console.log('Block state:', { isHovered, hoveredArrow, currentMode });
  }, [isHovered, hoveredArrow, currentMode]);

  const draw = useCallback((g: Graphics) => {
    g.clear();

    // Цвета и параметры
    const fillColor = isSelected ? 0xeeeeee : 0xffffff;
    const borderColor = isSelected ? 0x0000ff : 0x000000;
    const borderWidth = isSelected ? 3 : 2;
    const cornerRadius = 10;

    // Рисуем блок с закругленными углами
    g.roundRect(-BLOCK_WIDTH/2, -BLOCK_HEIGHT/2, BLOCK_WIDTH, BLOCK_HEIGHT, cornerRadius);
    if (isSelected) {
      g.stroke({ width: borderWidth, color: borderColor});
    }
    g.fill(fillColor);
  }, [isSelected]);

  const handleMouseEnter = () => {
    console.log('Block mouse enter');
    setIsHovered(true);
  };

  const handleMouseLeave = (e: any) => {
    console.log('Block mouse leave');
    // Проверяем, не перешел ли курсор на одну из стрелок
    const relatedTarget = e.target.parent.children.find(
      (child: any) => child !== e.target && child.containsPoint?.(e.data.global)
    );
    
    if (!relatedTarget) {
      setIsHovered(false);
      setHoveredArrow(null);
    }
  };

  const handleLeftArrowClick = () => {
    onAddBlock(blockData, level - 1);
  };

  const handleRightArrowClick = () => {
    onAddBlock(blockData, level + 1);
  };

  // Вычисляем координаты для предварительного просмотра
  const getPreviewCoordinates = () => {
    if (!hoveredArrow) return null;

    const xOffset = BLOCK_WIDTH * 2;
    const coords = {
      sourceX: hoveredArrow === 'left' ? -BLOCK_WIDTH/2 : BLOCK_WIDTH/2, // Точка соединения на текущем блоке
      sourceY: 0,
      targetX: hoveredArrow === 'left' ? -xOffset : xOffset, // Смещение для нового блока
      targetY: 0
    };
    console.log('Preview coordinates:', coords);
    return coords;
  };

  const previewCoords = getPreviewCoordinates();

  const shouldShowArrows = (isHovered || hoveredArrow !== null) && currentMode === EditModeEnum.CREATE_BLOCKS;
  const shouldShowPreview = shouldShowArrows && hoveredArrow !== null && previewCoords !== null;
  
  console.log('Render conditions:', {
    isHovered,
    currentMode,
    expectedMode: EditModeEnum.CREATE_BLOCKS,
    shouldShowArrows,
    shouldShowPreview,
    hoveredArrow,
    previewCoords
  });

  return (
    <pixiContainer x={x} y={y} sortableChildren={true}>
      <pixiGraphics 
        draw={draw} 
        eventMode="static" 
        onClick={onClick}
        cursor="pointer"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        zIndex={1}
      />
      <pixiText
        text={text}
        anchor={0.5}
        eventMode="none"
        style={{
          fontSize: 14,
          fill: '#000000',
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 20,
          breakWords: true,
          align: 'center',
          lineHeight: 16,
        }}
        zIndex={2}
      />
      {shouldShowArrows && (
        <>
          <AddBlockArrow
            position="left"
            onHover={() => {
              console.log('Left arrow hover');
              setHoveredArrow('left');
            }}
            onHoverEnd={() => {
              console.log('Left arrow hover end');
              setHoveredArrow(null);
            }}
            onClick={handleLeftArrowClick}
            isHovered={hoveredArrow === 'left'}
            zIndex={3}
          />
          <AddBlockArrow
            position="right"
            onHover={() => {
              console.log('Right arrow hover');
              setHoveredArrow('right');
            }}
            onHoverEnd={() => {
              console.log('Right arrow hover end');
              setHoveredArrow(null);
            }}
            onClick={handleRightArrowClick}
            isHovered={hoveredArrow === 'right'}
            zIndex={3}
          />
        </>
      )}
      {shouldShowPreview && previewCoords && (
        <BlockPreview
          sourceX={previewCoords.sourceX}
          sourceY={previewCoords.sourceY}
          targetX={previewCoords.targetX}
          targetY={previewCoords.targetY}
          isLeftArrow={hoveredArrow === 'left'}
          zIndex={4}
        />
      )}
    </pixiContainer>
  );
}