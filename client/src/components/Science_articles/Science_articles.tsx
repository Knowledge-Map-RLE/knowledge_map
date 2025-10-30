import { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from '../Knowledge_map/Viewport';
import type { ViewportRef } from '../Knowledge_map/Viewport';
import { useSelectionState } from '../Knowledge_map/hooks/useSelectionState';
import { useActions } from '../Knowledge_map/hooks/useActions';
import { useInteractionHandlers } from '../Knowledge_map/hooks/useInteractionHandlers';
import { useBlockOperations } from '../Knowledge_map/hooks/useBlockOperations';
import { useEditingState } from '../Knowledge_map/hooks/useEditingState';
import { useContextMenu } from '../Knowledge_map/hooks/useContextMenu';
import { EditMode } from '../Knowledge_map/types';
import type { LinkCreationState } from '../Knowledge_map/types';
import styles from '../Knowledge_map/Knowledge_map.module.css';

// Импортируем новые компоненты и хуки
import { useArticlesDataLoader } from './hooks/useArticlesDataLoader';
import { useArticlesViewport } from './hooks/useArticlesViewport';
import { ArticlesRenderer } from './components/ArticlesRenderer';
import { ArticlesControls } from './components/ArticlesControls';
import { TestNode } from './components/TestNode';
import { useViewport } from '../../contexts/ViewportContext';

extend({ Container, Graphics, Text });

export default function Science_articles() {
  console.log('Science_articles.tsx component is rendering!');
  
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);
  const { setViewportRef } = useViewport();

  // Регистрируем viewportRef в глобальном контексте
  useEffect(() => {
    console.log('Science_articles.tsx useEffect triggered');
    
    const registerViewport = () => {
      console.log('Science_articles.tsx: Registering viewportRef in context:', !!viewportRef.current);
      if (viewportRef.current) {
        setViewportRef(viewportRef);
      }
    };

    // Пробуем зарегистрировать сразу
    registerViewport();
    
    // И также через задержку на случай, если viewport еще не готов
    const timer = setTimeout(registerViewport, 1000);
    
    return () => clearTimeout(timer);
  }, [setViewportRef]);

  // Используем новый хук для загрузки данных
  const {
    blocks,
    blockMap,  // ОПТИМИЗАЦИЯ: Map для O(1) поиска блоков
    links,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    loadNextPage
  } = useArticlesDataLoader(viewportRef);

  // Логируем состояние загрузки для отладки
  console.log(`[Science_articles] Состояние:`, {
    blocksCount: blocks.length,
    linksCount: links.length,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit
  });

  const [levels, setLevels] = useState<any[]>([]);
  const [sublevels, setSublevels] = useState<any[]>([]);
  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);

  // Хуки для управления состоянием
  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlock, handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks: () => {}, setLinks: () => {}, setSublevels, clearSelection, loadLayoutData: loadNextPage
  });



  const {
    editingBlock,
    editingText,
    creatingBlock,
    setEditingText,
    setCreatingBlock,
    handleBlockDoubleClick,
    handleSaveEdit,
    handleCancelEdit,
    handleArrowClick: handleArrowClickEdit,
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
  } = useContextMenu(blocks, () => {}, loadNextPage, clearSelection);

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

  // Адаптеры для совместимости с ArticlesRenderer
  const handleBlockPointerDownAdapter = useCallback((blockId: string, event: any) => {
    event.stopPropagation();
    
    const currentTime = Date.now();
    const lastClick = (event.currentTarget as any)._lastClick || 0;
    const timeDiff = currentTime - lastClick;
    
    if (timeDiff < 300) {
      handleBlockDoubleClick(blockId, blocks);
    } else {
      handleBlockClick(blockId);
    }
    
    (event.currentTarget as any)._lastClick = currentTime;
  }, [handleBlockClick, handleBlockDoubleClick, blocks]);

  const handleArrowClickAdapter = useCallback((blockId: string, arrowPosition: 'left' | 'right') => {
    const block = blocks.find(b => b.id === blockId);
    if (block) {
      // Здесь можно добавить логику для обработки клика по стрелке
      console.log(`Arrow click on block ${blockId}, position: ${arrowPosition}`);
    }
  }, [blocks]);

  const handleBlockRightClickAdapter = useCallback((blockId: string, event: any) => {
    // Здесь можно добавить логику для обработки правого клика
    console.log(`Right click on block ${blockId}`);
  }, []);

  // Адаптеры для правильных сигнатур
  const handleBlockClickAdapter = useCallback((blockId: string) => {
    handleBlockClick(blockId);
  }, [handleBlockClick]);

  const handleLinkClickAdapter = useCallback((linkId: string) => {
    handleLinkClick(linkId);
  }, [handleLinkClick]);

  const handleBlockMouseEnterAdapter = useCallback((blockId: string) => {
    handleBlockMouseEnter(blockId);
  }, [handleBlockMouseEnter]);

  const handleBlockMouseLeaveAdapter = useCallback((blockId: string, event: any) => {
    handleBlockMouseLeave(blockId, event);
  }, [handleBlockMouseLeave]);

  // Обработчик стрелок
  const handleArrowHover = useCallback((blockId: string, arrowPosition: 'left' | 'right' | null) => {
    originalHandleArrowHover(blockId, arrowPosition);
  }, [originalHandleArrowHover]);

  const { handleAddBlock } = useBlockOperations({
    setBlocks: () => {},
    setLinks: () => {},
    setFocusTargetId,
    loadLayoutData: loadNextPage
  });

  // Используем новый хук для viewport
  useArticlesViewport(viewportRef, blocks, pageLimit, focusTargetId, setFocusTargetId, loadNextPage);

  // Инициализация PIXI
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => { 
    containerRef.current?.focus(); 
  }, []);



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

  // Обработка ошибок
  if (loadError) {
    return (
      <div className={styles.knowledge_map} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки статей: {loadError}
      </div>
    );
  }

  return (
    <main ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>
      {(!pixiReady || (isBootLoading && blocks.length === 0)) && (
        <div className={styles.экран_загрузки}>
          {isLoading ? 'Загрузка научных статей...' : 'Инициализация...'}
        </div>
      )}
      
      <ArticlesRenderer
        viewportRef={viewportRef}
        blocks={blocks}
        blockMap={blockMap}  // ОПТИМИЗАЦИЯ: Map для O(1) поиска в Link
        links={links}
        levels={levels}
        sublevels={sublevels}
        selectedBlocks={selectedBlocks}
        selectedLinks={selectedLinks}
        currentMode={currentMode}
        isBlockContextMenuActive={isBlockContextMenuActive}
        blockRightClickRef={blockRightClickRef}
        instantBlockClickRef={instantBlockClickRef}
        onCanvasClick={handleCanvasClickWithMode}
        onBlockClick={handleBlockClickAdapter}
        onLinkClick={handleLinkClickAdapter}
        onBlockPointerDown={handleBlockPointerDownAdapter}
        onBlockMouseEnter={handleBlockMouseEnterAdapter}
        onBlockMouseLeave={handleBlockMouseLeaveAdapter}
        onArrowClick={handleArrowClickAdapter}
        onArrowHover={handleArrowHover}
        onBlockRightClick={handleBlockRightClickAdapter}
        onSublevelClick={handleSublevelClick}
      />

      <ArticlesControls
        currentMode={currentMode}
        linkCreationStep={linkCreationState.step}
        editingBlock={editingBlock}
        creatingBlock={creatingBlock}
        editingText={editingText}
        contextMenu={contextMenu}
        blocks={blocks}
        setEditingText={setEditingText}
        onSaveEdit={handleSaveEditWrapper}
        onCancelEdit={handleCancelEdit}
        onCreateNewBlock={handleCreateNewBlockWrapper}
        onPin={() => handlePinBlock(contextMenu?.blockId || '')}
        onUnpin={() => handleUnpinBlock(contextMenu?.blockId || '')}
        onPinWithScale={(scale) => handlePinBlockWithScale(contextMenu?.blockId || '', scale)}
        onCloseContextMenu={handleContextMenuClose}
      />
    </main>
  );
}
