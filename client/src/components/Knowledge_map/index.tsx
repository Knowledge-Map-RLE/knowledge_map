import { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from './Viewport';
import type { ViewportRef } from './Viewport';
import { Link } from './Link';
import { Level } from './Level';
import { Sublevel } from './Sublevel';
import { Block } from './Block';
import ModeIndicator from './ModeIndicator';
import { useKeyboardControlsWithProps } from './hooks/useKeyboardControls';
import { useDataLoading } from './hooks/useDataLoading';
import { useSelectionState } from './hooks/useSelectionState';
import { useActions } from './hooks/useActions';
import { useInteractionHandlers } from './hooks/useInteractionHandlers';
import { useBlockOperations } from './hooks/useBlockOperations';
import { EditMode } from './types';
import type { LinkCreationState, BlockData, LinkData } from './types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from './constants';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export default function Knowledge_map() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);

  const {
    blocks, links, levels, sublevels, isLoading, loadError, loadLayoutData,
    setBlocks, setLinks, setLevels, setSublevels
  } = useDataLoading();

  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);

  const {
    handleBlockClick,
    handleBlockMouseEnter,
    handleBlockMouseLeave,
    handleArrowHover,
    handleLinkClick,
    handleCanvasClick
  } = useInteractionHandlers({
    currentMode,
    linkCreationState,
    setLinkCreationState,
    setBlocks,
    blocks,
    handleBlockSelection,
    handleLinkSelection,
    handleCreateLink,
    handleDeleteBlock,
    handleDeleteLink,
    clearSelection
  });

  const { handleAddBlock } = useBlockOperations({
    setBlocks,
    setLinks,
    setFocusTargetId,
    loadLayoutData
  });

  const viewportState = viewportRef.current ?
    { scale: viewportRef.current.scale, position: viewportRef.current.position } :
    { scale: 1, position: { x: 0, y: 0 } };

  useKeyboardControlsWithProps({
    setCurrentMode, setLinkCreationState, currentMode, linkCreationState
  });

  useEffect(() => { loadLayoutData(); }, [loadLayoutData]);
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => { containerRef.current?.focus(); }, []);

  // Автоматическое центрирование при первой загрузке данных
  useEffect(() => {
    if (blocks.length > 0 && !focusTargetId) {
      // Находим центр всех блоков
      const centerX = blocks.reduce((sum, block) => sum + (block.x || 0), 0) / blocks.length;
      const centerY = blocks.reduce((sum, block) => sum + (block.y || 0), 0) / blocks.length;

      // Центрируем viewport на центр данных
      setTimeout(() => {
        viewportRef.current?.focusOn(centerX, centerY);
      }, 100);
    }
  }, [blocks.length, focusTargetId]); // Зависимость только от количества блоков для единократного вызова

  useEffect(() => {
    if (focusTargetId && blocks.length > 0) {
      const targetBlock = blocks.find(b => b.id === focusTargetId);
      if (targetBlock && typeof targetBlock.x === 'number' && typeof targetBlock.y === 'number') {
        const targetX = targetBlock.x + BLOCK_WIDTH / 2;
        const targetY = targetBlock.y;
        viewportRef.current?.focusOn(targetX, targetY);
        setFocusTargetId(null);
      }
    }
  }, [blocks, focusTargetId]);

  // Простые обработчики, которые остаются в компоненте
  const handleBlockPointerDown = useCallback((blockId: string, event: any) => {
    event.stopPropagation();
    handleBlockClick(blockId);
  }, [handleBlockClick]);

  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  if (loadError) {
    return (
      <div className={styles.knowledge_map} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки: {loadError}
      </div>
    );
  }

  return (
    <div ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>
      {(!pixiReady || isLoading) && (
        <div className={styles.экран_загрузки}>
          {isLoading ? 'Обновление данных...' : 'Инициализация...'}
        </div>
      )}
      <Application width={window.innerWidth} height={window.innerHeight} backgroundColor={0xf5f5f5}>
        <Viewport ref={viewportRef} onCanvasClick={handleCanvasClick}>
          {/* Рендерим все уровни без вложенных sublevels и blocks */}
          {levels.map(level => (
            <Level
              key={level.id}
              levelData={level}
            />
          ))}
          
          {/* Рендерим все подуровни отдельно */}
          {sublevels.map(sublevel => (
            <Sublevel
              key={sublevel.id}
              sublevelData={sublevel}
              onSublevelClick={handleSublevelClick}
            />
          ))}

          {/* Рендерим все ссылки */}
          {links.map(link => (
            <Link
              key={link.id}
              linkData={link}
              blocks={blocks}
              isSelected={selectedLinks.includes(link.id)}
              onClick={() => handleLinkClick(link.id)}
            />
          ))}
          
          {/* Рендерим все блоки отдельно */}
          {blocks.map(block => (
            <Block
              key={block.id}
              blockData={block}
              onBlockClick={handleBlockClick}
              isSelected={selectedBlocks.includes(block.id)}
              currentMode={currentMode}
              onAddBlock={handleAddBlock}
              onBlockPointerDown={handleBlockPointerDown}
              onBlockMouseEnter={handleBlockMouseEnter}
              onBlockMouseLeave={handleBlockMouseLeave}
              onArrowHover={handleArrowHover}
            />
          ))}
        </Viewport>
      </Application>
      <ModeIndicator currentMode={currentMode} linkCreationStep={linkCreationState.step} />
    </div>
  );
}