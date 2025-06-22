import { Graphics, Container, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useState, useCallback, useRef, useEffect, memo } from 'react';
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
  isSelected: boolean;
  currentMode: EditMode;
  onAddBlock: (sourceBlock: BlockData, targetLevel: number) => void;
  onBlockPointerDown: (blockId: string, event: any) => void;
  onBlockMouseEnter: (blockId: string) => void;
  onBlockMouseLeave: (blockId: string, event: any) => void;
  onArrowHover: (blockId: string, arrowPosition: 'left' | 'right' | null) => void;
}

export const Block = memo(function Block({ 
  blockData, 
  onBlockClick, 
  isSelected,
  currentMode,
  onAddBlock,
  onBlockPointerDown,
  onBlockMouseEnter,
  onBlockMouseLeave,
  onArrowHover,
}: BlockProps) {
  const { id, text, x, y, level, isHovered, hoveredArrow } = blockData;
  const containerRef = useRef<Container>(null);
  const isInitialRender = useRef(true);

  useEffect(() => {
    if (containerRef.current) {
      const safeX = x || 0;
      const safeY = y || 0;
      
      if (isInitialRender.current) {
        containerRef.current.x = safeX;
        containerRef.current.y = safeY;
        containerRef.current.alpha = 0;
        gsap.to(containerRef.current, { alpha: 1, duration: 0.5, ease: 'power2.inOut' });
        isInitialRender.current = false;
      } else {
        gsap.to(containerRef.current, { x: safeX, y: safeY, duration: 0.8, ease: 'power3.inOut' });
      }
    }
  }, [x, y]);

  const draw = useCallback((g: Graphics) => {
    const bgColor = isSelected ? 0x93c5fd : 0xffffff;
    const borderColor = isHovered || hoveredArrow ? 0x3b82f6 : 0xd1d5db;
    const borderWidth = isSelected || isHovered || hoveredArrow ? 2 : 1;
    g.clear();
    g.rect(0, 0, BLOCK_WIDTH, BLOCK_HEIGHT);
    g.fill(bgColor);
    g.stroke({ width: borderWidth, color: borderColor });
  }, [isSelected, isHovered, hoveredArrow]);

  return (
    <container 
      ref={containerRef}
      eventMode="static" 
      cursor="pointer"
      onMouseEnter={() => onBlockMouseEnter(id)}
      onMouseLeave={(e: any) => onBlockMouseLeave(id, e)}
      onPointerDown={(e: any) => onBlockPointerDown(id, e)}
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
            onHover={() => onArrowHover(id, 'left')}
            onHoverEnd={() => onArrowHover(id, null)}
            isHovered={hoveredArrow === 'left'}
          />
          <AddBlockArrow
            position="right"
            onClick={() => onAddBlock(blockData, level + 1)}
            onHover={() => onArrowHover(id, 'right')}
            onHoverEnd={() => onArrowHover(id, null)}
            isHovered={hoveredArrow === 'right'}
          />
        </>
      )}
    </container>
  );
});