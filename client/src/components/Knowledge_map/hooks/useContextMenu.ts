import { useState, useCallback, useRef } from 'react';
import { pinBlock, unpinBlock, pinBlockWithScale, moveBlockToLevel } from '../../../services/api';
import type { BlockData } from '../types';

export interface ContextMenuState {
  contextMenu: {
    blockId: string;
    x: number;
    y: number;
  } | null;
  isBlockContextMenuActive: boolean;
  blockRightClickRef: React.MutableRefObject<boolean>;
  instantBlockClickRef: React.MutableRefObject<boolean>;
}

export const useContextMenu = (
  blocks: BlockData[],
  setBlocks: (updater: (prev: BlockData[]) => BlockData[]) => void,
  loadLayoutData: () => void,
  clearSelection: () => void
) => {
  const [contextMenu, setContextMenu] = useState<{
    blockId: string;
    x: number;
    y: number;
  } | null>(null);
  const [isBlockContextMenuActive, setIsBlockContextMenuActive] = useState(false);
  const blockRightClickRef = useRef<boolean>(false);
  const instantBlockClickRef = useRef<boolean>(false);

  const handleBlockRightClick = useCallback((blockId: string, x: number, y: number) => {
    console.log('Block right click triggered');
    blockRightClickRef.current = true;
    setIsBlockContextMenuActive(true);
    setContextMenu({ blockId, x, y });
    
    // Сбрасываем флаги через короткий тайм-аут для быстрого восстановления перетаскивания
    setTimeout(() => {
      blockRightClickRef.current = false;
      instantBlockClickRef.current = false;
      console.log('Block right click flags reset');
    }, 50);
  }, []);

  const handleContextMenuClose = useCallback(() => {
    blockRightClickRef.current = false;
    setIsBlockContextMenuActive(false);
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

  const handlePinBlockWithScale = useCallback(async (blockId: string, physicalScale: number) => {
    try {
      const result = await pinBlockWithScale(blockId, physicalScale);
      if (result.success) {
        // Обновляем локальное состояние
        setBlocks(prev => prev.map(block => 
          block.id === blockId ? { ...block, is_pinned: true, physical_scale: physicalScale } : block
        ));
        // Перезагружаем данные для обновления укладки
        loadLayoutData();
      } else {
        console.error('Failed to pin block with scale:', result.error);
      }
    } catch (error) {
      console.error('Error pinning block with scale:', error);
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

  return {
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
  };
}; 