import { useState } from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { extend } from '@pixi/react';
import type { ReactNode } from 'react';
import type { BlockData } from './index';

extend({ Container, Graphics, Text });

// Константы для стилизации
const BLOCK_WIDTH = 200;
const BLOCK_HEIGHT = 120;
const BLOCK_COLOR = 0xffffff;
const SELECTED_COLOR = 0x3b82f6;
const HOVER_COLOR = 0xf3f4f6;
const TEXT_COLOR = 0x000000;
const BORDER_COLOR = 0xe5e7eb;
const SELECTED_BORDER_COLOR = 0x2563eb;
const FIRST_FOR_LINK_COLOR = 0x8b5cf6; // Фиолетовый для первого блока при создании связи

interface BlockProps {
  blockData: BlockData;
  isSelected?: boolean;
  isFirstForLink?: boolean;
  onBlockClick?: (blockId: string) => void;
}

export function Block({ 
  blockData, 
  isSelected = false,
  isFirstForLink = false,
  onBlockClick
}: BlockProps): ReactNode {
  const [isHovered, setIsHovered] = useState(false);

  const handlePointerDown = (event: FederatedPointerEvent) => {
    // Останавливаем всплытие события, чтобы не сработал клик по canvas
    event.stopPropagation();
    
    if (onBlockClick) {
      onBlockClick(blockData.id);
    }
  };

  const handlePointerEnter = () => {
    setIsHovered(true);
  };

  const handlePointerLeave = () => {
    setIsHovered(false);
  };

  // Определяем цвета в зависимости от состояния
  const getBlockColor = () => {
    if (isFirstForLink) return FIRST_FOR_LINK_COLOR;
    if (isSelected) return SELECTED_COLOR;
    if (isHovered) return HOVER_COLOR;
    return BLOCK_COLOR;
  };

  const getBorderColor = () => {
    if (isFirstForLink) return FIRST_FOR_LINK_COLOR;
    return isSelected ? SELECTED_BORDER_COLOR : BORDER_COLOR;
  };

  return (
    <pixiContainer 
      x={blockData.x} 
      y={blockData.y}
      interactive={true}
      cursor="pointer"
      onPointerDown={handlePointerDown}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
    >
      {/* Фон блока */}
      <pixiGraphics
        draw={(g: Graphics) => {
          g.clear()
            .roundRect(
              -BLOCK_WIDTH / 2, 
              -BLOCK_HEIGHT / 2, 
              BLOCK_WIDTH, 
              BLOCK_HEIGHT, 
              8
            )
            .fill(getBlockColor())
            .stroke({ 
              color: getBorderColor(), 
              width: (isSelected || isFirstForLink) ? 3 : 2 
            });
        }}
      />
      
      {/* Текст блока */}
      <pixiText
        text={blockData.text}
        anchor={0.5}
        style={{
          fontFamily: 'Arial',
          fontSize: 14,
          fill: TEXT_COLOR,
          wordWrap: true,
          wordWrapWidth: BLOCK_WIDTH - 20,
          align: 'center'
        }}
      />
    </pixiContainer>
  );
}