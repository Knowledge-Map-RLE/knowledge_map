import { Graphics, Container, Text, Point } from 'pixi.js';
import { extend } from '@pixi/react';
import { useState, useCallback, useRef, useEffect, memo } from 'react';
import { AddBlockArrow } from './AddBlockArrow';
import type { BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import { EditMode } from './types';
import { gsap } from 'gsap';

extend({ Graphics, Container, Text });

const BLOCK_PADDING = 4;

export interface BlockProps {
  blockData: BlockData;
  onBlockClick: (id: string) => void;
  isSelected: boolean;
  currentMode: EditMode;
  onArrowClick: (sourceBlock: BlockData, targetLevel: number) => void;
  onBlockPointerDown: (blockId: string, event: any) => void;
  onBlockMouseEnter: (blockId: string) => void;
  onBlockMouseLeave: (blockId: string, event: any) => void;
  onArrowHover: (blockId: string, arrowPosition: 'left' | 'right' | null) => void;
  onBlockRightClick: (blockId: string, x: number, y: number) => void;
  instantBlockClickRef?: React.RefObject<boolean>;
}

export const Block = memo(function Block({ 
  blockData, 
  onBlockClick, 
  isSelected,
  currentMode,
  onArrowClick,
  onBlockPointerDown,
  onBlockMouseEnter,
  onBlockMouseLeave,
  onArrowHover,
  onBlockRightClick,
  instantBlockClickRef,
}: BlockProps) {
  const { id, text, x, y, level, isHovered, hoveredArrow, is_pinned } = blockData;
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
    const bgColor = isSelected ? 0x93c5fd : (is_pinned ? 0xfef3c7 : 0xffffff);
    const borderColor = isHovered || hoveredArrow ? 0x3b82f6 : (is_pinned ? 0xf59e0b : 0xd1d5db);
    const borderWidth = isSelected || isHovered || hoveredArrow || is_pinned ? 2 : 1;
    g.clear();
    g.roundRect(-BLOCK_WIDTH / 2, -BLOCK_HEIGHT / 2, BLOCK_WIDTH, BLOCK_HEIGHT, 10);
    g.fill(bgColor);
    g.stroke({ width: borderWidth, color: borderColor });
  }, [isSelected, isHovered, hoveredArrow, is_pinned]);

  return (
    <container 
      ref={containerRef}
      eventMode="static" 
      cursor="pointer"
      onMouseEnter={() => onBlockMouseEnter(id)}
      onMouseLeave={(e: any) => onBlockMouseLeave(id, e)}
              onPointerDown={(e: any) => {
          if (e.button === 2) {
            // Правый клик - мгновенно устанавливаем флаг и блокируем всплытие
            console.log('Block pointer down - RIGHT CLICK, blocking');
            if (instantBlockClickRef) {
              instantBlockClickRef.current = true;
              console.log('INSTANT flag set to true');
            }
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            return;
          }
          onBlockPointerDown(id, e);
        }}
        onRightClick={(e: any) => {
          console.log('Block right click event');
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
          e.nativeEvent?.preventDefault?.();
          e.nativeEvent?.stopPropagation?.();
          e.nativeEvent?.stopImmediatePropagation?.();
          onBlockRightClick(id, e.global.x, e.global.y);
        }}

        zIndex={10}
    >
      <graphics draw={draw} />
      <pixiText
        text={text}
        x={0}
        y={-BLOCK_HEIGHT / 2 + BLOCK_PADDING}
        anchor={new Point(0.5, 0)}
        style={{
          fontFamily: 'PT Sans Narrow, sans-serif',
          fontSize: 14,
          fill: 0x000000,
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 2 * BLOCK_PADDING,
          breakWords: true,
          align: 'center',
        }}
      />
      {isHovered && currentMode === EditMode.CREATE_BLOCKS && (
        <>
          <AddBlockArrow
            position="left"
            onClick={() => onArrowClick(blockData, level - 1)}
            onHover={() => onArrowHover(id, 'left')}
            onHoverEnd={() => onArrowHover(id, null)}
            isHovered={hoveredArrow === 'left'}
          />
          <AddBlockArrow
            position="right"
            onClick={() => onArrowClick(blockData, level + 1)}
            onHover={() => onArrowHover(id, 'right')}
            onHoverEnd={() => onArrowHover(id, null)}
            isHovered={hoveredArrow === 'right'}
          />
        </>
      )}
    </container>
  );
});