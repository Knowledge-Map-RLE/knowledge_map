import { useState, useEffect, useRef, useCallback } from 'react';
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
import styles from '../Knowledge_map/Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export default function Science_articles() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);

  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [links, setLinks] = useState<LinkData[]>([]);
  const [levels, setLevels] = useState<any[]>([]);
  const [sublevels, setSublevels] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isBootLoading, setIsBootLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Пагинация и наборы уже загруженных сущностей
  const [pageOffset, setPageOffset] = useState<number>(0);
  const [pageLimit] = useState<number>(50);
  const [totalCount, setTotalCount] = useState<number>(0);
  const loadedBlockIdsRef = useRef<Set<string>>(new Set());
  const loadedLinkIdsRef = useRef<Set<string>>(new Set());

  // Загрузка данных по батчам (пагинация)
  async function loadNextPage() {
    if (isLoading) {
      console.log(`[ArticlesPage] Skipping loadNextPage - already loading`);
      return;
    }
    
    // Проверяем, не загружали ли мы уже эту страницу
    if (loadedBlockIdsRef.current.size > 0 && pageOffset === 0) {
      console.log(`[ArticlesPage] Skipping loadNextPage - already loaded initial data (${loadedBlockIdsRef.current.size} blocks)`);
      return;
    }
    
    // Дополнительная защита от дублирования
    if (blocks.length > 0 && pageOffset === 0) {
      console.log(`[ArticlesPage] Skipping loadNextPage - blocks already exist (${blocks.length} blocks)`);
      return;
    }
    
    // Защита от двойного вызова в React Strict Mode
    if (loadedBlockIdsRef.current.size > 0) {
      console.log(`[ArticlesPage] Skipping loadNextPage - React Strict Mode protection (loadedBlockIds: ${loadedBlockIdsRef.current.size})`);
      return;
    }
    
    setIsLoading(true);
    setLoadError(null);
    
    try {
      console.log(`[ArticlesPage] Loading page ${pageOffset + 1} with limit ${pageLimit}`);
      
      const response = await fetch(`http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`[ArticlesPage] received page:`, data);
      
      if (data && data.success) {
        const serverBlocks = Array.isArray(data.blocks) ? data.blocks : [];
        const serverLinks = Array.isArray(data.links) ? data.links : [];

        console.log(`[ArticlesPage] blocks: ${serverBlocks.length}, links: ${serverLinks.length}`);
        console.log(`[ArticlesPage] first block:`, serverBlocks[0]);
        console.log(`[ArticlesPage] first block fields:`, Object.keys(serverBlocks[0] || {}));
        
        const processedBlocks: BlockData[] = [];
        for (let i = 0; i < serverBlocks.length; i++) {
          const b = serverBlocks[i];
          const id = String(b.id);
          const bx = (typeof b.x === 'number') ? b.x : (b.x != null ? Number(b.x) : undefined);
          const by = (typeof b.y === 'number') ? b.y : (b.y != null ? Number(b.y) : undefined);
          const lvl = (typeof b.level === 'number') ? b.level : 0;
          const lay = (typeof b.layer === 'number') ? b.layer : 0;
          const sub = (typeof b.sublevel_id === 'number') ? b.sublevel_id : 0;
          
          console.log(`[ArticlesPage] Block ${i} coordinates: x=${b.x} (${typeof b.x}), y=${b.y} (${typeof b.y}), processed: bx=${bx}, by=${by}`);
          
          // Fallback координаты, если x/y не определены
          const cols = 40;
          const col = i % cols;
          const row = Math.floor(i / cols);
          const fallbackX = col * (BLOCK_WIDTH + 40);
          const fallbackY = row * (BLOCK_HEIGHT + 60);
          const title = (b.content ?? b.title ?? b.name ?? id);
          
          const processedBlock = {
            id,
            text: String(title),
            content: String(title),
            x: (bx !== undefined ? bx : fallbackX),
            y: (by !== undefined ? by : fallbackY),
            level: lvl,
            physical_scale: typeof b.physical_scale === 'number' ? b.physical_scale : 0,
            sublevel: sub,
            layer: lay,
            is_pinned: Boolean(b.is_pinned)
          };
          
          console.log(`[ArticlesPage] processed block ${i}:`, processedBlock);
          console.log(`[ArticlesPage] Final coordinates for block ${i}: x=${processedBlock.x}, y=${processedBlock.y}`);
          processedBlocks.push(processedBlock);
        }
        
        const processedLinks: LinkData[] = [];
        for (const l of serverLinks) {
          const id = l.id ? String(l.id) : `${String(l.source_id)}-${String(l.target_id)}`;
          processedLinks.push({ 
            id, 
            source_id: String(l.source_id), 
            target_id: String(l.target_id) 
          });
        }
        
        // Добавляем новые блоки к существующим
        setBlocks(prevBlocks => {
          console.log(`[ArticlesPage] setBlocks called with prevBlocks.length: ${prevBlocks.length}`);
          console.log(`[ArticlesPage] setBlocks stack trace:`, new Error().stack);
          
          // Защита от двойного вызова в React Strict Mode
          if (loadedBlockIdsRef.current.size > 0) {
            console.log(`[ArticlesPage] Skipping setBlocks - already processed (loadedBlockIds: ${loadedBlockIdsRef.current.size})`);
            // Возвращаем текущее состояние, а не prevBlocks
            return blocks;
          }
          
          const newBlocks = [...prevBlocks];
          let addedCount = 0;
          for (const block of processedBlocks) {
            if (!loadedBlockIdsRef.current.has(block.id)) {
              newBlocks.push(block);
              loadedBlockIdsRef.current.add(block.id);
              addedCount++;
            }
          }
          console.log(`[ArticlesPage] Added ${addedCount} new blocks, total: ${newBlocks.length}`);
          console.log(`[ArticlesPage] First few blocks:`, newBlocks.slice(0, 3));
          console.log(`[ArticlesPage] Returning newBlocks with length: ${newBlocks.length}`);
          return newBlocks;
        });
        
        // Добавляем новые связи к существующим
        setLinks(prevLinks => {
          console.log(`[ArticlesPage] setLinks called with prevLinks.length: ${prevLinks.length}`);
          console.log(`[ArticlesPage] setLinks stack trace:`, new Error().stack);
          
          // Защита от двойного вызова в React Strict Mode
          if (loadedLinkIdsRef.current.size > 0) {
            console.log(`[ArticlesPage] Skipping setLinks - already processed (loadedLinkIds: ${loadedLinkIdsRef.current.size})`);
            // Возвращаем текущее состояние, а не prevLinks
            return links;
          }
          
          const newLinks = [...prevLinks];
          let addedCount = 0;
          for (const link of processedLinks) {
            if (!loadedLinkIdsRef.current.has(link.id)) {
              newLinks.push(link);
              loadedLinkIdsRef.current.add(link.id);
              addedCount++;
            }
          }
          console.log(`[ArticlesPage] Added ${addedCount} new links, total: ${newLinks.length}`);
          console.log(`[ArticlesPage] Returning newLinks with length: ${newLinks.length}`);
          return newLinks;
        });
        
        // Убираем экран загрузки при первой загрузке
        if (isBootLoading && processedBlocks.length > 0) {
          setIsBootLoading(false);
        }
        
        // Переходим к следующей странице
        setPageOffset(prev => prev + pageLimit);
        
      } else {
        throw new Error((data && data.error) || 'Failed to load articles page');
      }
    } catch (error: any) {
      console.error('Error loading articles page:', error);
      setLoadError(error?.message || 'Unknown error');
      if (isBootLoading) setIsBootLoading(false);
    } finally {
      setIsLoading(false);
    }
  }

  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlock, handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection, loadLayoutData: () => loadNextPage()
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
  } = useContextMenu(blocks, setBlocks, () => loadNextPage(), clearSelection);

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
      timer = setTimeout(() => loadNextPage(), 250);
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
  }, []);

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

  // Автоматическое центрирование только при первой загрузке (не при подгрузке)
  useEffect(() => {
    if (blocks.length > 0 && !focusTargetId && blocks.length <= pageLimit) {
      // Только для первой загрузки (когда blocks.length <= pageLimit)
      // Находим центр всех блоков
      const centerX = blocks.reduce((sum, block) => sum + (block.x || 0), 0) / blocks.length;
      const centerY = blocks.reduce((sum, block) => sum + (block.y || 0), 0) / blocks.length;

      // Центрируем viewport на центр данных
      setTimeout(() => {
        viewportRef.current?.focusOn(centerX, centerY);
      }, 100);
    }
  }, [blocks.length, focusTargetId, pageLimit]);

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
      handleSaveEdit(editingBlock, editingText, setBlocks);
    }
  }, [editingBlock, editingText, handleSaveEdit, setBlocks]);

  const handleCreateNewBlockWrapper = useCallback(() => {
    if (creatingBlock) {
      handleCreateNewBlock(creatingBlock, editingText, blocks, setBlocks, handleAddBlock);
    }
  }, [creatingBlock, editingText, blocks, setBlocks, handleAddBlock, handleCreateNewBlock]);

  if (loadError) {
    return (
      <div className={styles.knowledge_map} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки статей: {loadError}
      </div>
    );
  }

  console.log(`[ArticlesPage] Rendering: pixiReady=${pixiReady}, isBootLoading=${isBootLoading}, blocks.length=${blocks.length}, isLoading=${isLoading}`);
  console.log(`[ArticlesPage] loadedBlockIds size:`, loadedBlockIdsRef.current.size);
  console.log(`[ArticlesPage] pageOffset:`, pageOffset);
  
  return (
    <main ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>
      {(!pixiReady || (isBootLoading && blocks.length === 0)) && (
        <div className={styles.экран_загрузки}>
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
          currentPhysicalScale={blocks.find(b => b.id === contextMenu.blockId)?.physical_scale || 0}
          onPin={() => handlePinBlock(contextMenu.blockId)}
          onUnpin={() => handleUnpinBlock(contextMenu.blockId)}
          onPinWithScale={(physicalScale: number) => handlePinBlockWithScale(contextMenu.blockId, physicalScale)}
          onClose={handleContextMenuClose}
        />
      )}
    </main>
  );
}
