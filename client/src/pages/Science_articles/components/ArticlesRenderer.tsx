import { Application } from '@pixi/react';
import { useMemo, type ReactNode } from 'react';
import { Viewport, Link, Level, Sublevel, Block } from '../../../widgets/KnowledgeMap';
import { TestNode } from './TestNode';
import type { ViewportRef, BlockData, LinkData, EditMode } from '../../../widgets/KnowledgeMap';

interface ArticlesRendererProps {
  viewportRef: React.RefObject<ViewportRef>;
  blocks: BlockData[];
  blockMap?: Map<string, BlockData>;  // ОПТИМИЗАЦИЯ: Map для O(1) поиска
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
  /** Дополнительный контент внутри Viewport (например, KnowledgeMapRenderer) */
  children?: ReactNode;
  /** Цвет фона Pixi-холста */
  backgroundColor?: number;
}

export function ArticlesRenderer({
  viewportRef,
  blocks,
  blockMap,  // ОПТИМИЗАЦИЯ: Принимаем Map
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
  onSublevelClick,
  children,
  backgroundColor = 0xf5f5f5,
}: ArticlesRendererProps) {
  // ОПТИМИЗАЦИЯ: Создаём Set для O(1) проверки selection вместо O(n) Array.includes()
  const selectedBlocksSet = useMemo(() => new Set(selectedBlocks), [selectedBlocks]);
  const selectedLinksSet = useMemo(() => new Set(selectedLinks), [selectedLinks]);

  return (
    <Application width={window.innerWidth} height={window.innerHeight} backgroundColor={backgroundColor}>
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
            blockMap={blockMap}  // ОПТИМИЗАЦИЯ: Передаём Map для O(1) поиска
            isSelected={selectedLinksSet.has(link.id)}  // ОПТИМИЗАЦИЯ: Set.has() вместо Array.includes()
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
            isSelected={selectedBlocksSet.has(block.id)}  // ОПТИМИЗАЦИЯ: Set.has() вместо Array.includes()
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

        {/* Слот для дополнительного контента (например, карта знаний) */}
        {children}
      </Viewport>
    </Application>
  );
}
