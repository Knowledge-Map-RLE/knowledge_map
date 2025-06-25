import { useState, useEffect, useRef, useCallback } from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from './Viewport';
import type { ViewportRef } from './Viewport';
import { Link } from './Link';
import { Level } from './Level';
import { Sublevel } from './Sublevel';
import { Block } from './Block';
import { BlockContextMenu } from './BlockContextMenu';
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
import { pinBlock, unpinBlock, moveBlockToLevel } from '../../services/api';
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
    handleCreateBlock, handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection, loadLayoutData
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);
  
  // Состояние редактирования блоков
  const [editingBlock, setEditingBlock] = useState<BlockData | null>(null);
  const [editingText, setEditingText] = useState('');
  
  // Состояние создания нового блока
  const [creatingBlock, setCreatingBlock] = useState<{
    sourceBlock: BlockData | null;
    targetLevel: number;
  } | null>(null);

  // Состояние контекстного меню
  const [contextMenu, setContextMenu] = useState<{
    blockId: string;
    x: number;
    y: number;
  } | null>(null);

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

  // Обработчики редактирования блоков
  const handleBlockDoubleClick = useCallback((blockId: string) => {
    const block = blocks.find(b => b.id === blockId);
    if (block) {
      setEditingBlock(block);
      setEditingText(block.text);
    }
  }, [blocks]);

  const handleSaveEdit = useCallback(async () => {
    if (!editingBlock) return;
    
    try {
      const response = await fetch(`http://localhost:8000/api/blocks/${editingBlock.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content: editingText.trim() }),
      });

      if (response.ok) {
        // Обновляем локальное состояние
        setBlocks(prev => prev.map(block => 
          block.id === editingBlock.id ? { ...block, text: editingText.trim() } : block
        ));
        setEditingBlock(null);
        setEditingText('');
      } else {
        console.error('Failed to update block:', await response.text());
      }
    } catch (error) {
      console.error('Error updating block:', error);
    }
  }, [editingBlock, editingText, setBlocks]);

  const handleCancelEdit = useCallback(() => {
    setEditingBlock(null);
    setEditingText('');
    setCreatingBlock(null);
  }, []);

  // Обработчик клика по стрелке для создания блока
  const handleArrowClick = useCallback((sourceBlock: BlockData, targetLevel: number) => {
    setCreatingBlock({ sourceBlock, targetLevel });
    setEditingText('');
    setEditingBlock(null); // Закрываем редактирование если оно было открыто
  }, []);

  // Обработчики контекстного меню
  const handleBlockRightClick = useCallback((blockId: string, x: number, y: number) => {
    setContextMenu({ blockId, x, y });
  }, []);

  const handleContextMenuClose = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handlePinBlock = useCallback(async (blockId: string) => {
    try {
      const result = await pinBlock(blockId);
      if (result.success) {
        // Обновляем локальное состояние
        setBlocks(prev => prev.map(block => 
          block.id === blockId ? { ...block, is_pinned: true } : block
        ));
        // Перезагружаем данные для обновления укладки
        loadLayoutData();
      } else {
        console.error('Failed to pin block:', result.error);
      }
    } catch (error) {
      console.error('Error pinning block:', error);
    }
  }, [setBlocks, loadLayoutData]);

  const handleUnpinBlock = useCallback(async (blockId: string) => {
    try {
      const result = await unpinBlock(blockId);
      if (result.success) {
        // Обновляем локальное состояние
        setBlocks(prev => prev.map(block => 
          block.id === blockId ? { ...block, is_pinned: false } : block
        ));
        // Перезагружаем данные для обновления укладки
        loadLayoutData();
      } else {
        console.error('Failed to unpin block:', result.error);
      }
    } catch (error) {
      console.error('Error unpinning block:', error);
    }
  }, [setBlocks, loadLayoutData]);

  // Функция для поиска подходящего уровня для перемещения
  const findTargetLevel = useCallback((currentLevel: number, direction: 'up' | 'down', excludeBlockId?: string) => {
    const pinnedBlocksMap = new Map<number, string[]>();
    
    // Группируем закрепленные блоки по уровням (исключая текущий блок для расчета границ)
    blocks.forEach(block => {
      if (block.is_pinned && block.id !== excludeBlockId) {
        const level = block.level;
        if (!pinnedBlocksMap.has(level)) {
          pinnedBlocksMap.set(level, []);
        }
        pinnedBlocksMap.get(level)!.push(block.id);
      }
    });
    
    // Получаем отсортированные уровни с закрепленными блоками (без текущего)
    const pinnedLevels = Array.from(pinnedBlocksMap.keys()).sort((a, b) => a - b);
    
    console.log(`🔍 findTargetLevel: current=${currentLevel}, direction=${direction}, pinnedLevels:`, pinnedLevels);
    
    if (direction === 'up') {
        // "Вверх" означает переход на уровень с МЕНЬШИМ номером (визуально выше)
        const levelsAbove = pinnedLevels.filter(level => level < currentLevel);
        
        if (levelsAbove.length > 0) {
          const target = Math.max(...levelsAbove); // Ближайший (максимальный) из меньших
          console.log(`✅ Moving to existing level above: ${target}`);
          return target;
        }
        
        // Если не найден, создаем новый уровень выше всех существующих закрепленных блоков (включая текущий)
        const allLevels = [currentLevel, ...pinnedLevels];
        const minLevel = Math.min(...allLevels);
        const target = minLevel - 1;
        console.log(`🆕 Creating new level above all (including current): ${target}`);
        return target;
    } else {
        // "Вниз" означает переход на уровень с БОЛЬШИМ номером (визуально ниже)
        const levelsBelow = pinnedLevels.filter(level => level > currentLevel);
        
        if (levelsBelow.length > 0) {
          const target = Math.min(...levelsBelow); // Ближайший (минимальный) из больших
          console.log(`✅ Moving to existing level below: ${target}`);
          return target;
        }
        
        // Если не найден, создаем новый уровень ниже всех существующих закрепленных блоков (включая текущий)
        const allLevels = [currentLevel, ...pinnedLevels];
        const maxLevel = Math.max(...allLevels);
        const target = maxLevel + 1;
        console.log(`🆕 Creating new level below all (including current): ${target}`);
        return target;
    }
  }, [blocks]);

  // Обработчик перемещения закрепленного блока
  const handleMovePinnedBlock = useCallback(async (blockId: string, direction: 'up' | 'down') => {
    const block = blocks.find(b => b.id === blockId);
    if (!block || !block.is_pinned) {
      console.warn('Block is not pinned or not found:', blockId);
      return;
    }

    const targetLevel = findTargetLevel(block.level, direction, blockId);
    console.log(`🚀 Moving block ${blockId} from level ${block.level} to level ${targetLevel} (${direction})`);

    try {
      const result = await moveBlockToLevel(blockId, targetLevel);
      if (result.success) {
        console.log('✅ Block moved successfully, reloading layout...');
        // Снимаем выделение после успешного перемещения
        clearSelection();
        // Перезагружаем данные для получения новой укладки
        loadLayoutData();
      } else {
        console.error('❌ Failed to move block:', result.error);
      }
    } catch (error) {
      console.error('💥 Error moving block:', error);
    }
  }, [blocks, findTargetLevel, loadLayoutData, clearSelection]);

  // Обработчик создания нового блока
  const handleCreateNewBlock = useCallback(async () => {
    if (!creatingBlock?.sourceBlock || !editingText.trim()) return;
    
    const currentBlocksCount = blocks.length;
    const textToSet = editingText.trim();
    
    try {
      // Создаем блок с дефолтным текстом
      await handleAddBlock(creatingBlock.sourceBlock, creatingBlock.targetLevel);
      
      // Ждем появления нового блока и обновляем его текст
      const checkForNewBlock = () => {
        setBlocks(currentBlocks => {
          if (currentBlocks.length > currentBlocksCount) {
            // Найден новый блок - обновляем его текст через API
            const newBlock = currentBlocks[currentBlocks.length - 1];
            if (newBlock && newBlock.text === 'Новый блок') {
              // Обновляем через API
              fetch(`http://localhost:8000/api/blocks/${newBlock.id}`, {
                method: 'PUT',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: textToSet }),
              })
              .then(response => {
                if (response.ok) {
                  // Обновляем локальное состояние
                  setBlocks(prev => prev.map(block => 
                    block.id === newBlock.id ? { ...block, text: textToSet } : block
                  ));
                } else {
                  console.error('Failed to update new block text');
                }
              })
              .catch(error => {
                console.error('Error updating new block text:', error);
              });
            }
          }
          return currentBlocks;
        });
      };
      
      // Проверяем появление нового блока через небольшие интервалы
      setTimeout(checkForNewBlock, 100);
      setTimeout(checkForNewBlock, 300);
      setTimeout(checkForNewBlock, 500);
      
      setCreatingBlock(null);
      setEditingText('');
    } catch (error) {
      console.error('Error creating block:', error);
    }
  }, [creatingBlock, editingText, handleAddBlock, setBlocks, blocks.length]);

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
    
    // Простая реализация двойного клика
    const currentTime = Date.now();
    const lastClick = (event.currentTarget as any)._lastClick || 0;
    const timeDiff = currentTime - lastClick;
    
    if (timeDiff < 300) {
      // Двойной клик - начинаем редактирование
      handleBlockDoubleClick(blockId);
    } else {
      // Одиночный клик
      handleBlockClick(blockId);
    }
    
    (event.currentTarget as any)._lastClick = currentTime;
  }, [handleBlockClick, handleBlockDoubleClick]);

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
        <Viewport ref={viewportRef} onCanvasClick={handleCanvasClickWithMode}>
          {/* Рендерим все уровни */}
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
            />
          ))}
          

        </Viewport>
      </Application>
      <ModeIndicator currentMode={currentMode} linkCreationStep={linkCreationState.step} />
      

      
      {/* Панель редактирования/создания блоков внизу */}
      {(editingBlock || creatingBlock) && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t-2 border-blue-500 shadow-lg z-50 p-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center space-x-4">
              <div className="flex-shrink-0">
                <h3 className="text-lg font-semibold text-gray-800">
                  {editingBlock ? 'Редактировать блок' : 'Создать новый блок'}
                </h3>
              </div>
              <div className="flex-1">
                <textarea
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.shiftKey) {
                      e.preventDefault();
                      if (editingBlock) {
                        handleSaveEdit();
                      } else if (creatingBlock) {
                        handleCreateNewBlock();
                      }
                    } else if (e.key === 'Escape') {
                      e.preventDefault();
                      handleCancelEdit();
                    }
                  }}
                  className="w-full h-20 p-3 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder={editingBlock ? "Введите текст блока..." : "Введите текст нового блока..."}
                  autoFocus
                />
              </div>
              <div className="flex-shrink-0 flex items-center space-x-3">
                <div className="text-sm text-gray-500">
                  Shift+Enter - сохранить, Esc - отменить
                </div>
                <button
                  onClick={handleCancelEdit}
                  className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Отменить
                </button>
                <button
                  onClick={editingBlock ? handleSaveEdit : handleCreateNewBlock}
                  className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
                >
                  {editingBlock ? 'Сохранить' : 'Создать'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Контекстное меню */}
      {contextMenu && (
        <BlockContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          isPinned={blocks.find(b => b.id === contextMenu.blockId)?.is_pinned || false}
          onPin={() => handlePinBlock(contextMenu.blockId)}
          onUnpin={() => handleUnpinBlock(contextMenu.blockId)}
          onClose={handleContextMenuClose}
        />
      )}
    </div>
  );
}