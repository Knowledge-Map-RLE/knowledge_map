import { useState, useCallback } from 'react';
import type { BlockData } from '../types';

export interface EditingState {
  editingBlock: BlockData | null;
  editingText: string;
  creatingBlock: {
    sourceBlock: BlockData | null;
    targetLevel: number;
  } | null;
}

export const useEditingState = () => {
  const [editingBlock, setEditingBlock] = useState<BlockData | null>(null);
  const [editingText, setEditingText] = useState('');
  const [creatingBlock, setCreatingBlock] = useState<{
    sourceBlock: BlockData | null;
    targetLevel: number;
  } | null>(null);

  const handleBlockDoubleClick = useCallback((blockId: string, blocks: BlockData[]) => {
    const block = blocks.find(b => b.id === blockId);
    if (block) {
      setEditingBlock(block);
      setEditingText(block.text);
    }
  }, []);

  const handleSaveEdit = useCallback(async (editingBlock: BlockData, editingText: string, setBlocks: (updater: (prev: BlockData[]) => BlockData[]) => void) => {
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
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingBlock(null);
    setEditingText('');
    setCreatingBlock(null);
  }, []);

  const handleArrowClick = useCallback((sourceBlock: BlockData, targetLevel: number) => {
    setCreatingBlock({ sourceBlock, targetLevel });
    setEditingText('');
    setEditingBlock(null);
  }, []);

  const handleCreateNewBlock = useCallback(async (
    creatingBlock: { sourceBlock: BlockData | null; targetLevel: number } | null,
    editingText: string,
    blocks: BlockData[],
    setBlocks: (updater: (prev: BlockData[]) => BlockData[]) => void,
    handleAddBlock: (sourceBlock: BlockData, targetLevel: number) => Promise<void>
  ) => {
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
  }, []);

  return {
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
  };
}; 