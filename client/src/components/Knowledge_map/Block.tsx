import { Graphics, Container, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { AddBlockArrow } from './AddBlockArrow';
import type { BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import { EditMode } from './types';
import { gsap } from 'gsap';

extend({ Graphics, Container, Text });

const BLOCK_PADDING = 10;

export interface BlockProps {
  blockData: BlockData;
  onBlockClick: (id: string) => void;
  onBlockHover?: (block: BlockData | null) => void;
  isSelected: boolean;
  currentMode: EditMode;
  onAddBlock: (sourceBlock: BlockData, targetLevel: number) => void;
}

export function Block({ 
  blockData, 
  onBlockClick, 
  onBlockHover, 
  isSelected,
  currentMode,
  onAddBlock
}: BlockProps) {
  const { id, text, x, y, level } = blockData;
  const containerRef = useRef<Container>(null);
  const isInitialRender = useRef(true);

  useEffect(() => {
    if (containerRef.current) {
      if (isInitialRender.current) {
        containerRef.current.x = x;
        containerRef.current.y = y;
        containerRef.current.alpha = 0;
        gsap.to(containerRef.current, { alpha: 1, duration: 0.5, ease: 'power2.inOut' });
        isInitialRender.current = false;
      } else {
        gsap.to(containerRef.current, { x, y, duration: 0.8, ease: 'power3.inOut' });
      }
    }
  }, [x, y]);

  const [isHovered, setIsHovered] = useState(false);
  const [hoveredArrow, setHoveredArrow] = useState<'left' | 'right' | null>(null);
  
  const draw = useCallback((g: Graphics) => {
    const bgColor = isSelected ? 0x93c5fd : 0xffffff;
    const borderColor = isHovered || hoveredArrow ? 0x3b82f6 : 0xd1d5db;
    const borderWidth = isSelected || isHovered || hoveredArrow ? 2 : 1;
    g.clear();
    g.rect(0, 0, BLOCK_WIDTH, BLOCK_HEIGHT);
    g.fill(bgColor);
    g.stroke({ width: borderWidth, color: borderColor });
  }, [isSelected, isHovered, hoveredArrow]);

  const handlePointerDown = (event: any) => {
    event.stopPropagation(); 
    onBlockClick(id);
  };
  
  const handleMouseLeave = (e: any) => {
     const relatedTarget = e.currentTarget.parent?.children.find(
       (child: any) => child !== e.currentTarget && child.containsPoint?.(e.global)
     );
     if (!relatedTarget) {
       setIsHovered(false);
       onBlockHover?.(null);
     }
  };

  return (
    <container 
      ref={containerRef}
      eventMode="static" 
      cursor="pointer"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onPointerDown={handlePointerDown}
      zIndex={10}
    >
      <graphics draw={draw} />
      <pixiText
        text={text}
        x={BLOCK_PADDING}
        y={BLOCK_PADDING}
        style={{
          fontSize: 14,
          fill: 0x000000,
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 2 * BLOCK_PADDING,
        }}
      />
      {isHovered && currentMode === EditMode.CREATE_BLOCKS && (
        <>
          <AddBlockArrow
            position="left"
            onClick={() => onAddBlock(blockData, level - 1)}
            onHover={() => setHoveredArrow('left')}
            onHoverEnd={() => setHoveredArrow(null)}
            isHovered={hoveredArrow === 'left'}
          />
          <AddBlockArrow
            position="right"
            onClick={() => onAddBlock(blockData, level + 1)}
            onHover={() => setHoveredArrow('right')}
            onHoverEnd={() => setHoveredArrow(null)}
            isHovered={hoveredArrow === 'right'}
          />
        </>
      )}
    </container>
  );
}