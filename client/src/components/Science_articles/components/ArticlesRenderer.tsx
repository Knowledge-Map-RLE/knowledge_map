import { Application } from '@pixi/react';
import { Viewport } from '../../Knowledge_map/Viewport';
import { Link } from '../../Knowledge_map/Link';
import { Level } from '../../Knowledge_map/Level';
import { Sublevel } from '../../Knowledge_map/Sublevel';
import { Block } from '../../Knowledge_map/Block';
import { TestNode } from './TestNode';
import type { ViewportRef } from '../../Knowledge_map/Viewport';
import type { BlockData, LinkData } from '../../Knowledge_map/types';
import type { EditMode } from '../../Knowledge_map/types';

interface ArticlesRendererProps {
  viewportRef: React.RefObject<ViewportRef>;
  blocks: BlockData[];
  links: LinkData[];
  levels: any[];
  sublevels: any[];
  selectedBlocks: string[];
  selectedLinks: string[];
  currentMode: EditMode;
  isBlockContextMenuActive: boolean;
  blockRightClickRef: React.MutableRefObject<boolean>;
  instantBlockClickRef: React.MutableRefObject<boolean>;
  onCanvasClick: (x: number, y: number) => void;
  onBlockClick: (blockId: string) => void;
  onLinkClick: (linkId: string) => void;
  onBlockPointerDown: (blockId: string, event: any) => void;
  onBlockMouseEnter: (blockId: string) => void;
  onBlockMouseLeave: (blockId: string) => void;
  onArrowClick: (blockId: string, arrowPosition: 'left' | 'right') => void;
  onArrowHover: (blockId: string, arrowPosition: 'left' | 'right' | null) => void;
  onBlockRightClick: (blockId: string, event: any) => void;
  onSublevelClick: (sublevelId: number, x: number, y: number) => void;
}

export function ArticlesRenderer({
  viewportRef,
  blocks,
  links,
  levels,
  sublevels,
  selectedBlocks,
  selectedLinks,
  currentMode,
  isBlockContextMenuActive,
  blockRightClickRef,
  instantBlockClickRef,
  onCanvasClick,
  onBlockClick,
  onLinkClick,
  onBlockPointerDown,
  onBlockMouseEnter,
  onBlockMouseLeave,
  onArrowClick,
  onArrowHover,
  onBlockRightClick,
  onSublevelClick
}: ArticlesRendererProps) {
  return (
    <Application width={window.innerWidth} height={window.innerHeight} backgroundColor={0xf5f5f5}>
      <Viewport 
        ref={viewportRef} 
        onCanvasClick={onCanvasClick} 
        isBlockContextMenuActive={isBlockContextMenuActive} 
        blockRightClickRef={blockRightClickRef} 
        instantBlockClickRef={instantBlockClickRef}
      >
        {/* Рендерим все уровни */}
        {levels.map(level => (
          <Level
            key={level.id}
            levelData={level}
            blocks={blocks}
          />
        ))}
        
        {/* Рендерим все подуровни отдельно */}
        {sublevels.map(sublevel => (
          <Sublevel
            key={sublevel.id}
            sublevelData={sublevel}
            onSublevelClick={onSublevelClick}
          />
        ))}

        {/* Рендерим все связи */}
        {links.map(link => (
          <Link
            key={link.id}
            linkData={link}
            blocks={blocks}
            isSelected={selectedLinks.includes(link.id)}
            onClick={() => onLinkClick(link.id)}
          />
        ))}
        
        {/* Тестовая вершина в начале координат */}
        <TestNode 
          x={0} 
          y={0} 
          text="Тестовая вершина (0,0)" 
        />
        
        {/* Рендерим все блоки отдельно */}
        {blocks.map(block => (
          <Block
            key={block.id}
            blockData={block}
            onBlockClick={onBlockClick}
            isSelected={selectedBlocks.includes(block.id)}
            currentMode={currentMode}
            onArrowClick={onArrowClick}
            onBlockPointerDown={onBlockPointerDown}
            onBlockMouseEnter={onBlockMouseEnter}
            onBlockMouseLeave={onBlockMouseLeave}
            onArrowHover={onArrowHover}
            onBlockRightClick={onBlockRightClick}
            instantBlockClickRef={instantBlockClickRef}
          />
        ))}
      </Viewport>
    </Application>
  );
}
