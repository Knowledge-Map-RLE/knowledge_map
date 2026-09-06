import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import {
    Viewport,
    Block,
    Link,
    Level,
    Sublevel,
    BlockContextMenu,
    ModeIndicator,
    ViewportCoordinates,
    EditingPanel,
    useKeyboardControlsWithProps,
    useDataLoading,
    useSelectionState,
    useActions,
    useInteractionHandlers,
    useBlockOperations,
    useEditingState,
    useContextMenu,
    EditMode,
    BLOCK_WIDTH,
    BLOCK_HEIGHT,
} from '../../widgets/KnowledgeMap';
import type { ViewportRef, LinkCreationState, BlockData, LinkData } from '../../widgets/KnowledgeMap';
import { useViewport } from '../../shared/contexts';
import type { Knowledge_mapProps } from './model';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export const Knowledge_mapUI = ({ externalBlocks, externalLinks, embedded }: Knowledge_mapProps = {}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);
  const { setViewportRef } = useViewport();

  // Регистрируем viewportRef в глобальном контексте
  const [pixiReady, setPixiReady] = useState(false);

  useEffect(() => {
    const registerViewport = () => {
      console.log('Knowledge_map: Registering viewportRef in context:', !!viewportRef.current);
      if (viewportRef.current) {
        setViewportRef(viewportRef);
      }
    };

    // Пробуем зарегистрировать сразу
    registerViewport();
    
    // И также через задержку на случай, если viewport еще не готов
    const timer = setTimeout(registerViewport, 1000);
    
    return () => clearTimeout(timer);
  }, [setViewportRef, pixiReady]);

  const {
    blocks, links, levels, sublevels, isLoading, loadError, loadLayoutData, loadAround, loadEdgesByViewport,
    setBlocks, setLinks, setLevels, setSublevels
  } = useDataLoading();

  const actualBlocks = externalBlocks ?? blocks;
  const actualLinks = externalLinks ?? links;

  // Автоматическая загрузка данных при изменении viewport (только в режиме глобальной карты)
  useEffect(() => {
    if (externalBlocks) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    
    let timer: any;
    const scheduleLoad = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const center = viewport.getWorldCenter?.();
        const vb = viewport.getWorldBounds?.();
        if (center) loadAround(center.x, center.y, 100);
        if (vb) {
          loadEdgesByViewport({ left: vb.left, right: vb.right, top: vb.top, bottom: vb.bottom });
        }
      }, 1000); // Debounce 1 секунда
    };
    
    const handleViewportMoved = () => { userInteractedRef.current = true; scheduleLoad(); };
    const handleViewportZoomed = () => { userInteractedRef.current = true; scheduleLoad(); };
    
    if (viewport.on) {
      viewport.on('moved', handleViewportMoved);
      viewport.on('zoomed', handleViewportZoomed);
    }
    
    return () => {
      clearTimeout(timer);
      if (viewport.off) {
        viewport.off('moved', handleViewportMoved);
        viewport.off('zoomed', handleViewportZoomed);
      }
    };
  }, [loadAround, loadEdgesByViewport]);

  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlock, handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection, loadLayoutData
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);

  // После первого взаимодействия пользователя с камерой (drag/zoom)
  // автоматическое центрирование при догрузке блоков отключается,
  // чтобы не сбивать пользователю вид.
  const userInteractedRef = useRef(false);

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
  } = useContextMenu(blocks, setBlocks, loadLayoutData, clearSelection);

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
    setBlocks,
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
    setBlocks,
    setLinks,
    setFocusTargetId,
    loadLayoutData
  });

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

  useEffect(() => { if (!externalBlocks) loadLayoutData(); }, [externalBlocks, loadLayoutData]);
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => { containerRef.current?.focus(); }, []);

  // Автоматическое центрирование при первой загрузке данных
  useEffect(() => {
    if (actualBlocks.length > 0 && !focusTargetId && !userInteractedRef.current) {
      // Находим центр всех блоков
      const centerX = actualBlocks.reduce((sum, block) => sum + (block.x || 0), 0) / actualBlocks.length;
      const centerY = actualBlocks.reduce((sum, block) => sum + (block.y || 0), 0) / actualBlocks.length;

      // Центрируем viewport на центр данных
      setTimeout(() => {
        viewportRef.current?.focusOn(centerX, centerY);
      }, 100);
    }
  }, [actualBlocks.length, focusTargetId]);

  useEffect(() => {
    if (focusTargetId && actualBlocks.length > 0) {
      const targetBlock = actualBlocks.find(b => b.id === focusTargetId);
      if (targetBlock && typeof targetBlock.x === 'number' && typeof targetBlock.y === 'number') {
        const targetX = targetBlock.x + BLOCK_WIDTH / 2;
        const targetY = targetBlock.y;
        viewportRef.current?.focusOn(targetX, targetY);
        setFocusTargetId(null);
      }
    }
  }, [actualBlocks, focusTargetId]);

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
      handleSaveEdit(editingBlock, editingText, setBlocks);
    }
  }, [editingBlock, editingText, handleSaveEdit, setBlocks]);

  const handleCreateNewBlockWrapper = useCallback(() => {
    if (creatingBlock) {
      handleCreateNewBlock(creatingBlock, editingText, blocks, setBlocks, handleAddBlock);
    }
  }, [creatingBlock, editingText, blocks, setBlocks, handleAddBlock, handleCreateNewBlock]);

  // Подготавливаем memo-структуры для быстрого доступа и culling
  const viewportBounds = viewportRef.current?.getWorldBounds?.() || null;
  const screenSize = viewportRef.current?.getScreenSize?.() || null;
  const currentScale = viewportRef.current?.scale || 1;

  const pad = useMemo(() => {
    const w = screenSize?.width || 800;
    const h = screenSize?.height || 600;
    // Меньше запас при большом зуме
    const base = 0.35; // 35% экрана
    return {
      x: (w * base) / (currentScale || 1),
      y: (h * base) / (currentScale || 1)
    };
  }, [screenSize?.width, screenSize?.height, currentScale]);

  const blockMap = useMemo(() => new Map(actualBlocks.map(b => [b.id, b])), [actualBlocks]);

  const viewBoundsWithPad = useMemo(() => {
    if (!viewportBounds) return null;
    return {
      left: viewportBounds.left - pad.x,
      right: viewportBounds.right + pad.x,
      top: viewportBounds.top - pad.y,
      bottom: viewportBounds.bottom + pad.y,
    };
  }, [viewportBounds?.left, viewportBounds?.right, viewportBounds?.top, viewportBounds?.bottom, pad.x, pad.y]);

  const visibleBlocks = useMemo(() => {
    if (!viewBoundsWithPad) return actualBlocks;
    const { left, right, top, bottom } = viewBoundsWithPad;
    return actualBlocks.filter(b => {
      const x = (b.x ?? 0);
      const y = (b.y ?? 0);
      return x >= left && x <= right && y >= top && y <= bottom;
    });
  }, [actualBlocks, viewBoundsWithPad?.left, viewBoundsWithPad?.right, viewBoundsWithPad?.top, viewBoundsWithPad?.bottom]);

  const visibleLinks = useMemo(() => {
    if (!viewBoundsWithPad) return actualLinks;
    const { left, right, top, bottom } = viewBoundsWithPad;
    const isInView = (b?: BlockData) => {
      if (!b) return false;
      const x = (b.x ?? 0);
      const y = (b.y ?? 0);
      return x >= left && x <= right && y >= top && y <= bottom;
    };
    return actualLinks.filter(l => isInView(blockMap.get(l.source_id)) || isInView(blockMap.get(l.target_id)));
  }, [actualLinks, blockMap, viewBoundsWithPad?.left, viewBoundsWithPad?.right, viewBoundsWithPad?.top, viewBoundsWithPad?.bottom]);
  if (!externalBlocks && loadError) {
    return (
      <div className={styles.knowledge_map} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки: {loadError}
      </div>
    );
  }


  return (
    <main ref={containerRef} className={styles.knowledge_map} tabIndex={-1} style={embedded ? { position: 'relative', width: '100%', height: '100%' } : undefined}>
      {(!pixiReady || (!externalBlocks && isLoading)) && (
        <div className={styles.экран_загрузки}>
          {isLoading ? 'Загрузка данных...' : 'Инициализация...'}
        </div>
      )}
      <Application width={embedded ? (containerRef.current?.clientWidth || window.innerWidth) : window.innerWidth} height={embedded ? (containerRef.current?.clientHeight || window.innerHeight) : window.innerHeight} backgroundColor={0xf5f5f5} antialias resolution={window.devicePixelRatio || 1} autoDensity>
        <Viewport ref={viewportRef} onCanvasClick={handleCanvasClickWithMode} onDragStart={handleContextMenuClose} isBlockContextMenuActive={isBlockContextMenuActive} blockRightClickRef={blockRightClickRef} instantBlockClickRef={instantBlockClickRef}>
          {/* Рендерим все уровни */}
          {levels.map(level => (
            <Level
              key={level.id}
              levelData={level}
              blocks={actualBlocks}
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

          {visibleLinks.map(link => (
            <Link
              key={link.id}
              linkData={link}
              blockMap={blockMap}
              isSelected={selectedLinks.includes(link.id)}
              onClick={() => handleLinkClick(link.id)}
              perfMode={true}
            />
          ))}
          
          {visibleBlocks.map(block => (
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
        <ViewportCoordinates />

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
          isPinned={actualBlocks.find(b => b.id === contextMenu.blockId)?.is_pinned || false}
          currentPhysicalScale={actualBlocks.find(b => b.id === contextMenu.blockId)?.physical_scale || 0}
          onPin={() => handlePinBlock(contextMenu.blockId)}
          onUnpin={() => handleUnpinBlock(contextMenu.blockId)}
          onPinWithScale={(physicalScale: number) => handlePinBlockWithScale(contextMenu.blockId, physicalScale)}
          onClose={handleContextMenuClose}
        />
      )}
      
    </main>
  );
}

export default Knowledge_mapUI;