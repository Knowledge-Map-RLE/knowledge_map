import { useMemo } from 'react';
import type { BlockData } from '../types';

interface UseVirtualizationProps {
  blocks: BlockData[];
  viewportWidth: number;
  viewportHeight: number;
  scale: number;
  position: { x: number; y: number };
  blockWidth: number;
  blockHeight: number;
  overscan?: number;
}

export function useVirtualization({
  blocks,
  viewportWidth,
  viewportHeight,
  scale,
  position,
  blockWidth,
  blockHeight,
  overscan = 5
}: UseVirtualizationProps) {
  return useMemo(() => {
    // Вычисляем видимую область
    const visibleStartX = -position.x / scale;
    const visibleEndX = (-position.x + viewportWidth) / scale;
    const visibleStartY = -position.y / scale;
    const visibleEndY = (-position.y + viewportHeight) / scale;

    // Фильтруем блоки, которые находятся в видимой области
    const visibleBlocks = blocks.filter(block => {
      const blockEndX = block.x + blockWidth;
      const blockEndY = block.y + blockHeight;
      
      return block.x < visibleEndX + overscan * blockWidth &&
             blockEndX > visibleStartX - overscan * blockWidth &&
             block.y < visibleEndY + overscan * blockHeight &&
             blockEndY > visibleStartY - overscan * blockHeight;
    });

    return visibleBlocks;
  }, [blocks, viewportWidth, viewportHeight, scale, position, blockWidth, blockHeight, overscan]);
} 