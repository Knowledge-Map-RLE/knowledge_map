import { useCallback } from 'react';
import type { BlockData, LinkData, SublevelData } from '../types';

interface UseActionsProps {
  blocks: BlockData[];
  links: LinkData[];
  sublevels: SublevelData[];
  setBlocks: (blocks: BlockData[]) => void;
  setLinks: (links: LinkData[]) => void;
  setSublevels: (sublevels: SublevelData[]) => void;
  clearSelection: () => void;
}

export const useActions = ({
  blocks,
  links,
  sublevels,
  setBlocks,
  setLinks,
  setSublevels,
  clearSelection
}: UseActionsProps) => {
  // Создание нового блока на подуровне
  const handleCreateBlockOnSublevel = useCallback(async (x: number, y: number, sublevelId: number) => {
    try {
      console.log(`Creating block at (${x}, ${y}) on sublevel ${sublevelId}`);
      
      const sublevel = sublevels.find(sl => sl.id === sublevelId);
      if (!sublevel) {
        console.error('Sublevel not found:', sublevelId);
        return;
      }

      const mockServerResponse: BlockData = {
        id: Date.now().toString(),
        text: 'Новый блок',
        x: Math.round(x / 50) * 50,
        y: sublevel.min_y,
        level: sublevel.id,
        layer: Math.round(x / 250),
        sublevel: sublevelId
      };
      
      const newBlocks = [...blocks, mockServerResponse];
      setBlocks(newBlocks);
      
      // Обновляем подуровень
      const newSublevels = sublevels.map(sl => 
        sl.id === sublevelId 
          ? { ...sl, block_ids: [...sl.block_ids, mockServerResponse.id] }
          : sl
      );
      setSublevels(newSublevels);
      
      console.log('Block created on sublevel:', mockServerResponse);
      
    } catch (error) {
      console.error('Ошибка при создании блока на подуровне:', error);
    }
  }, [blocks, sublevels, setBlocks, setSublevels]);

  // Создание нового блока (оригинальный метод для клика по canvas)
  const handleCreateBlock = useCallback(async (x: number, y: number) => {
    // Находим ближайший подуровень
    const nearestSublevel = sublevels.reduce((nearest, sublevel) => {
      const distance = Math.abs(sublevel.min_y - y);
      const nearestDistance = Math.abs(nearest.min_y - y);
      return distance < nearestDistance ? sublevel : nearest;
    }, sublevels[0]);

    if (nearestSublevel) {
      handleCreateBlockOnSublevel(x, nearestSublevel.min_y, nearestSublevel.id);
    } else {
      // Если подуровней нет, создаем обычным способом
      try {
        console.log(`Creating block at (${x}, ${y})`);
        
        const mockServerResponse: BlockData = {
          id: Date.now().toString(),
          text: 'Новый блок',
          x: Math.round(x / 50) * 50,
          y: Math.round(y / 50) * 50,
          level: Math.round(y / 150),
          layer: 1,
          sublevel_id: undefined
        };
        
        setBlocks((prev: BlockData[]) => [...prev, mockServerResponse]);
        console.log('Block created:', mockServerResponse);
        
      } catch (error) {
        console.error('Ошибка при создании блока:', error);
      }
    }
  }, [sublevels, setBlocks, handleCreateBlockOnSublevel]);

  // Создание связи
  const handleCreateLink = useCallback(async (fromId: string, toId: string) => {
    try {
      console.log(`Creating link ${fromId} -> ${toId}`);
      
      const mockServerResponse: LinkData = {
        id: `link_${Date.now()}`,
        source_id: fromId,
        target_id: toId
      };
      
      console.log('Current links before update:', links);
      const newLinks = [...links, mockServerResponse];
      console.log('New links array:', newLinks);
      setLinks(newLinks);
      console.log('Link created:', mockServerResponse);
      
    } catch (error) {
      console.error('Ошибка при создании связи:', error);
    }
  }, [links, setLinks]);

  // Удаление блока
  const handleDeleteBlock = useCallback(async (blockId: string) => {
    try {
      console.log(`Deleting block ${blockId}`);
      
      const newBlocks = blocks.filter(block => block.id !== blockId);
      setBlocks(newBlocks);
      
      const newLinks = links.filter((link: LinkData) => 
        link.source_id !== blockId && link.target_id !== blockId
      );
      setLinks(newLinks);
      
      clearSelection();
      
      // Обновляем подуровни
      const newSublevels = sublevels.map(sl => ({
        ...sl,
        block_ids: sl.block_ids.filter(id => id !== blockId)
      }));
      setSublevels(newSublevels);
      
      console.log('Block deleted:', blockId);
      
    } catch (error) {
      console.error('Ошибка при удалении блока:', error);
    }
  }, [blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection]);

  // Удаление связи
  const handleDeleteLink = useCallback(async (linkId: string) => {
    try {
      console.log(`Deleting link ${linkId}`);
      
      const newLinks = links.filter((link: LinkData) => link.id !== linkId);
      setLinks(newLinks);
      clearSelection();
      
      console.log('Link deleted:', linkId);
      
    } catch (error) {
      console.error('Ошибка при удалении связи:', error);
    }
  }, [links, setLinks, clearSelection]);

  return {
    handleCreateBlock,
    handleCreateBlockOnSublevel,
    handleCreateLink,
    handleDeleteBlock,
    handleDeleteLink
  };
}; 