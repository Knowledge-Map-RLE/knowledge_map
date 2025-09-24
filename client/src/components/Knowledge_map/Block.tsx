import { Graphics, Container, Point } from 'pixi.js';
import { extend } from '@pixi/react';
import { useState, useCallback, useRef, useEffect, memo } from 'react';
import { AddBlockArrow } from './AddBlockArrow';
import type { BlockData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import { EditMode } from './types';
import { gsap } from 'gsap';

// Для соответствия остальным компонентам регистрируем только Graphics
extend({ Graphics });

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
  const { id, title, x, y, level, is_pinned } = blockData;
  
  // Отладочные логи отключены для производительности
  const containerRef = useRef<Container>(null);
  const isInitialRender = useRef(true);

  useEffect(() => {
    if (containerRef.current) {
      const fallbackX = (typeof (blockData.layer) === 'number' ? blockData.layer : 0) * 240;
      const fallbackY = (typeof (blockData.level) === 'number' ? blockData.level : 0) * 130;
      const safeX = (typeof x === 'number') ? x : fallbackX;
      const safeY = (typeof y === 'number') ? y : fallbackY;
      
      if (isInitialRender.current) {
        containerRef.current.x = safeX;
        containerRef.current.y = safeY;
        containerRef.current.alpha = 0;
        gsap.to(containerRef.current, { alpha: 1, duration: 0.5, ease: 'power2.inOut' });
        isInitialRender.current = false;
      } else {
        // Быстрая установка без плавной анимации для производительности
        containerRef.current.x = safeX;
        containerRef.current.y = safeY;
      }
    }
  }, [x, y]);

  const draw = useCallback((g: Graphics) => {
    const bgColor = isSelected ? 0x93c5fd : (is_pinned ? 0xfef3c7 : 0xffffff);
    const borderColor = is_pinned ? 0xf59e0b : 0xd1d5db;
    const borderWidth = isSelected || is_pinned ? 2 : 1;
    g.clear();
    g.roundRect(-BLOCK_WIDTH / 2, -BLOCK_HEIGHT / 2, BLOCK_WIDTH, BLOCK_HEIGHT, 10);
    g.fill(bgColor);
    g.stroke({ width: borderWidth, color: borderColor });
  }, [isSelected, is_pinned]);

  const drawText = (g: Graphics) => {
    g.clear();
    g.beginFill(0xffffff);
    g.drawRoundedRect(-60, 40, 120, 30, 8);
    g.endFill();
  };

  return (
         <container 
       ref={containerRef}
       eventMode="static" 
       cursor="pointer"
       zIndex={1}
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
     >
               <pixiGraphics draw={draw} />
      {/* @ts-ignore PixiText props typing */}
      <pixiText text={title} />
        
     </container>
  );
});