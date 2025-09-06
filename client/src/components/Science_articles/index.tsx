import { useState, useEffect, useRef, useCallback } from 'react';
import React from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from '../Knowledge_map/Viewport';
import type { ViewportRef } from '../Knowledge_map/Viewport';
import { Link } from '../Knowledge_map/Link';
import { Level } from '../Knowledge_map/Level';
import { Sublevel } from '../Knowledge_map/Sublevel';
import { Block } from '../Knowledge_map/Block';
import { BlockContextMenu } from '../Knowledge_map/BlockContextMenu';
import ModeIndicator from '../Knowledge_map/ModeIndicator';
import { useKeyboardControlsWithProps } from '../Knowledge_map/hooks/useKeyboardControls';
// Загружаем данные только с бэкенда, без клиентских вычислений координат
import { useSelectionState } from '../Knowledge_map/hooks/useSelectionState';
import { useActions } from '../Knowledge_map/hooks/useActions';
import { useInteractionHandlers } from '../Knowledge_map/hooks/useInteractionHandlers';
import { useBlockOperations } from '../Knowledge_map/hooks/useBlockOperations';
import { useEditingState } from '../Knowledge_map/hooks/useEditingState';
import { useContextMenu } from '../Knowledge_map/hooks/useContextMenu';
import { EditingPanel } from '../Knowledge_map/components/EditingPanel';
import { EditMode } from '../Knowledge_map/types';
import type { LinkCreationState, BlockData, LinkData } from '../Knowledge_map/types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from '../Knowledge_map/constants';

import { useArticlesDataLoader } from './hooks/useArticlesDataLoader';

extend({ Container, Graphics, Text });

export default function Science_articles() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);

  // Хук для загрузки данных статей
  const {
    blocks,
    links,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    loadNextPage
  } = useArticlesDataLoader(viewportRef);

  // Центрируем viewport при загрузке блоков
  useEffect(() => {
    if (blocks.length > 0 && viewportRef.current) {
      console.log(`[Science_articles] Centering viewport on ${blocks.length} blocks`);
      
      // Находим центр всех блоков
      const centerX = blocks.reduce((sum, block) => sum + (block.x || 0), 0) / blocks.length;
      const centerY = blocks.reduce((sum, block) => sum + (block.y || 0), 0) / blocks.length;
      
      // Находим диапазон координат для определения масштаба
      const minX = Math.min(...blocks.map(b => b.x || 0));
      const maxX = Math.max(...blocks.map(b => b.x || 0));
      const minY = Math.min(...blocks.map(b => b.y || 0));
      const maxY = Math.max(...blocks.map(b => b.y || 0));
      
      const rangeX = maxX - minX;
      const rangeY = maxY - minY;
      
      console.log(`[Science_articles] Coordinate range: x=${minX}-${maxX} (${rangeX}), y=${minY}-${maxY} (${rangeY})`);
      
      // Устанавливаем подходящий масштаб для видимости всех блоков
      const targetScale = Math.min(1.0, 800 / Math.max(rangeX, rangeY, 100));
      viewportRef.current.scale = targetScale;
      
      // Центрируем viewport
      viewportRef.current.focusOn(centerX, centerY);
      console.log(`[Science_articles] Viewport centered on blocks with scale ${targetScale}`);
    }
  }, [blocks.length]);

  const [levels, setLevels] = useState<any[]>([]);
  const [sublevels, setSublevels] = useState<any[]>([]);
  const loadedBlockIdsRef = useRef<Set<string>>(new Set());
  const loadedLinkIdsRef = useRef<Set<string>>(new Set());

  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlock, handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks: () => {}, setLinks: () => {}, setSublevels: () => {}, clearSelection, loadLayoutData: () => loadNextPage()
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);

  // Хуки для управления состоянием
  const {
    editingBlock,
    editingText,
    creatingBlock,
    setEditingText,
    setCreatingBlock,
    handleBlockDoubleClick,
    handleSaveEdit,
    handleCancelEdit,
    handleArrowClick,
    handleCreateNewBlock
  } = useEditingState();

  const {
    contextMenu,
    isBlockContextMenuActive,
    blockRightClickRef,
    instantBlockClickRef,
    handleBlockRightClick,
    handleContextMenuClose,
    handlePinBlock,
    handleUnpinBlock,
    handlePinBlockWithScale,
    handleMovePinnedBlock
  } = useContextMenu(blocks, () => {}, () => loadNextPage(), clearSelection);

  const {
    handleBlockClick,
    handleBlockMouseEnter,
    handleBlockMouseLeave,
    handleArrowHover: originalHandleArrowHover,
    handleLinkClick,
    handleCanvasClick
  } = useInteractionHandlers({
    currentMode,
    linkCreationState,
    setLinkCreationState,
    setBlocks: () => {},
    blocks,
    handleBlockSelection,
    handleLinkSelection,
    handleCreateLink,
    handleDeleteBlock,
    handleDeleteLink,
    clearSelection
  });

  // Обработчик стрелок - просто передаем вызов дальше
  const handleArrowHover = useCallback((blockId: string, arrowPosition: 'left' | 'right' | null) => {
    originalHandleArrowHover(blockId, arrowPosition);
  }, [originalHandleArrowHover]);

  const { handleAddBlock } = useBlockOperations({
    setBlocks: () => {},
    setLinks: () => {},
    setFocusTargetId,
    loadLayoutData: () => loadNextPage()
  });

  // Первая загрузка страницы
  const hasInitializedRef = useRef(false);

  useEffect(() => { 
    console.log(`[ArticlesPage] useEffect for loadNextPage triggered, hasInitialized: ${hasInitializedRef.current}`);
    if (!hasInitializedRef.current) {
      hasInitializedRef.current = true;
      console.log(`[ArticlesPage] First time initialization, calling loadNextPage`);
      loadNextPage();
    } else {
      console.log(`[ArticlesPage] Skipping duplicate useEffect call`);
    }
  }, []);

  // Тригерим подгрузку при перемещении/зуме viewport
  useEffect(() => {
    const v = viewportRef.current as any;
    if (!v) return;
    
    let timer: any;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        console.log(`[Science_articles] Triggering loadNextPage from viewport event`);
        loadNextPage();
      }, 250);
    };
    
    // Слушаем события viewport
    const handleViewportMoved = () => schedule();
    const handleViewportZoomed = () => schedule();
    
    if (v.on) {
      v.on('moved', handleViewportMoved);
      v.on('zoomed', handleViewportZoomed);
    }
    
    return () => {
      clearTimeout(timer);
      if (v.off) {
        v.off('moved', handleViewportMoved);
        v.off('zoomed', handleViewportZoomed);
      }
    };
  }, [loadNextPage]);

  const viewportState = viewportRef.current ?
    { scale: viewportRef.current.scale, position: viewportRef.current.position } :
    { scale: 1, position: { x: 0, y: 0 } };

  useKeyboardControlsWithProps({
    setCurrentMode, 
    setLinkCreationState, 
    currentMode, 
    linkCreationState,
    selectedBlocks,
    blocks,
    levels,
    onMovePinnedBlock: handleMovePinnedBlock
  });

  // Первая подгрузка уже инициирована выше
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => { containerRef.current?.focus(); }, []);

  // Автоматическое центрирование при загрузке блоков
  useEffect(() => {
    if (blocks.length > 0 && !focusTargetId) {
      // Находим центр всех блоков
      const centerX = blocks.reduce((sum, block) => sum + (block.x || 0), 0) / blocks.length;
      const centerY = blocks.reduce((sum, block) => sum + (block.y || 0), 0) / blocks.length;

      console.log(`[ArticlesPage] Centering viewport on blocks center: x=${centerX}, y=${centerY}`);
      
      // Центрируем viewport на центр данных
      setTimeout(() => {
        if (viewportRef.current) {
          viewportRef.current.focusOn(centerX, centerY);
          console.log(`[ArticlesPage] Viewport centered on blocks`);
        }
      }, 100);
    }
  }, [blocks.length, focusTargetId]);

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

  // Дополнительная защита от контекстного меню
  useEffect(() => {
    const preventContextMenu = (e: MouseEvent) => {
      e.preventDefault();
    };

    const blockAllPointerEvents = (e: Event) => {
      if (isBlockContextMenuActive) {
        console.log('Blocking all pointer events due to active context menu');
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }
    };

    const handleGlobalClick = (e: MouseEvent) => {
      // Если клик вне контекстного меню, сбрасываем флаг
      if (isBlockContextMenuActive && !contextMenu) {
        // Флаг сбрасывается автоматически в хуке useContextMenu
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('contextmenu', preventContextMenu);
      
      // Агрессивная блокировка всех pointer событий если контекстное меню активно
      if (isBlockContextMenuActive) {
        const canvas = container.querySelector('canvas');
        if (canvas) {
          canvas.addEventListener('pointerdown', blockAllPointerEvents, { capture: true });
          canvas.addEventListener('pointermove', blockAllPointerEvents, { capture: true });
          canvas.addEventListener('pointerup', blockAllPointerEvents, { capture: true });
        }
      }
      
      document.addEventListener('click', handleGlobalClick);
      
      return () => {
        container.removeEventListener('contextmenu', preventContextMenu);
        const canvas = container.querySelector('canvas');
        if (canvas) {
          canvas.removeEventListener('pointerdown', blockAllPointerEvents, { capture: true } as any);
          canvas.removeEventListener('pointermove', blockAllPointerEvents, { capture: true } as any);
          canvas.removeEventListener('pointerup', blockAllPointerEvents, { capture: true } as any);
        }
        document.removeEventListener('click', handleGlobalClick);
      };
    }
  }, [isBlockContextMenuActive, contextMenu]);

  // Простые обработчики, которые остаются в компоненте
  const handleBlockPointerDown = useCallback((blockId: string, event: any) => {
    event.stopPropagation();
    
    // Простая реализация двойного клика
    const currentTime = Date.now();
    const lastClick = (event.currentTarget as any)._lastClick || 0;
    const timeDiff = currentTime - lastClick;
    
    if (timeDiff < 300) {
      // Двойной клик - начинаем редактирование
      handleBlockDoubleClick(blockId, blocks);
    } else {
      // Одиночный клик
      handleBlockClick(blockId);
    }
    
    (event.currentTarget as any)._lastClick = currentTime;
  }, [handleBlockClick, handleBlockDoubleClick, blocks]);

  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  const handleCanvasClickWithMode = useCallback((x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlock(x, y);
    } else {
      handleCanvasClick();
    }
  }, [currentMode, handleCreateBlock, handleCanvasClick]);

  // Обработчики для панели редактирования
  const handleSaveEditWrapper = useCallback(() => {
    if (editingBlock) {
      handleSaveEdit(editingBlock, editingText, () => {});
    }
  }, [editingBlock, editingText, handleSaveEdit]);

  const handleCreateNewBlockWrapper = useCallback(() => {
    if (creatingBlock) {
      handleCreateNewBlock(creatingBlock, editingText, blocks, () => {}, handleAddBlock);
    }
  }, [creatingBlock, editingText, blocks, handleAddBlock, handleCreateNewBlock]);

  if (loadError) {
    return (
              <div className="knowledge_map" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки статей: {loadError}
      </div>
    );
  }

  console.log(`[ArticlesPage] Rendering: pixiReady=${pixiReady}, isBootLoading=${isBootLoading}, blocks.length=${blocks.length}, isLoading=${isLoading}`);
  console.log(`[ArticlesPage] loadedBlockIds size:`, loadedBlockIdsRef.current.size);
  console.log(`[ArticlesPage] pageOffset:`, pageOffset);
  
  return (
            <main ref={containerRef} className="knowledge_map" tabIndex={-1}>
      {(!pixiReady || (isBootLoading && blocks.length === 0)) && (
                  <div className="экран_загрузки">
          {isLoading ? 'Загрузка научных статей...' : 'Инициализация...'}
        </div>
      )}
      <Application width={window.innerWidth} height={window.innerHeight} backgroundColor={0xf5f5f5}>
        <Viewport ref={viewportRef} onCanvasClick={handleCanvasClickWithMode} isBlockContextMenuActive={isBlockContextMenuActive} blockRightClickRef={blockRightClickRef} instantBlockClickRef={instantBlockClickRef}>
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
              onSublevelClick={handleSublevelClick}
            />
          ))}

          {/* Рендерим все связи */}
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
              onArrowClick={handleArrowClick}
              onBlockPointerDown={handleBlockPointerDown}
              onBlockMouseEnter={handleBlockMouseEnter}
              onBlockMouseLeave={handleBlockMouseLeave}
              onArrowHover={handleArrowHover}
              onBlockRightClick={handleBlockRightClick}
              instantBlockClickRef={instantBlockClickRef}
            />
          ))}
        </Viewport>
      </Application>
      <ModeIndicator currentMode={currentMode} linkCreationStep={linkCreationState.step} />
      
      {/* Кнопка для тестирования подгрузки */}
      <button 
        onClick={() => {
          console.log(`[Science_articles] Manual loadNextPage triggered`);
          loadNextPage();
        }}
        style={{
          position: 'fixed',
          top: '10px',
          right: '10px',
          zIndex: 1000,
          padding: '8px 16px',
          backgroundColor: '#3b82f6',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: 'pointer'
        }}
      >
        Загрузить еще ({blocks.length} блоков)
      </button>

      {/* Панель редактирования/создания блоков */}
      <EditingPanel
        editingBlock={editingBlock}
        creatingBlock={creatingBlock}
        editingText={editingText}
        setEditingText={setEditingText}
        onSaveEdit={handleSaveEditWrapper}
        onCancelEdit={handleCancelEdit}
        onCreateNewBlock={handleCreateNewBlockWrapper}
      />

      {/* Контекстное меню */}
      {contextMenu && (
        <BlockContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          isPinned={blocks.find(b => b.id === contextMenu.blockId)?.is_pinned || false}
          currentPhysicalScale={0}
          onPin={() => handlePinBlock(contextMenu.blockId)}
          onUnpin={() => handleUnpinBlock(contextMenu.blockId)}
          onPinWithScale={(physicalScale: number) => handlePinBlockWithScale(contextMenu.blockId, physicalScale)}
          onClose={handleContextMenuClose}
        />
      )}
    </main>
  );
}
