import { useCallback } from 'react';
import type { BlockData, LinkData } from '../types';
import { createBlockAndLink } from '../../../services/api';

interface UseBlockOperationsProps {
  setBlocks: (updateFn: (prev: BlockData[]) => BlockData[]) => void;
  setLinks: (updateFn: (prev: LinkData[]) => LinkData[]) => void;
  setFocusTargetId: (id: string) => void;
  loadLayoutData: () => void;
}

export const useBlockOperations = ({
  setBlocks,
  setLinks,
  setFocusTargetId,
  loadLayoutData
}: UseBlockOperationsProps) => {

  const handleAddBlock = useCallback(async (sourceBlock: BlockData, targetLevel: number) => {
    try {
      const linkDirection = targetLevel < sourceBlock.level ? 'to_source' : 'from_source';
      const response = await createBlockAndLink(sourceBlock.id, linkDirection);

      if (!response.success || !response.new_block || !response.new_link) {
        console.error('Failed to create block and link:', response.error || 'Invalid response from server');
        return;
      }
      
      // Оптимистичное добавление с корректными, но временными координатами
      const newBlock: BlockData = {
        id: response.new_block.id,
        text: response.new_block.content || 'Новый блок',
        x: (sourceBlock.x || 0) + (linkDirection === 'from_source' ? 150 : -150), // Временная позиция
        y: sourceBlock.y || 0, // Временная позиция
        level: response.new_block.level,
        layer: response.new_block.layer ?? sourceBlock.layer ?? 0,
        sublevel: response.new_block.sublevel_id,
      };

      const newLink: LinkData = {
        id: response.new_link.id,
        source_id: response.new_link.source_id,
        target_id: response.new_link.target_id,
      };

      setBlocks(prev => [...prev, newBlock]);
      setLinks(prev => [...prev, newLink]);
      setFocusTargetId(newBlock.id);

      // Фоновое обновление для получения финальных координат от сервиса укладки
      setTimeout(() => {
        loadLayoutData();
      }, 100);

    } catch (error) {
      console.error('Error adding block and link:', error);
    }
  }, [setBlocks, setLinks, setFocusTargetId, loadLayoutData]);

  return {
    handleAddBlock
  };
}; 