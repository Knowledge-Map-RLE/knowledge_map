import { useCallback } from 'react';
import type { BlockData, LinkData, SublevelData } from '../types';
import { createBlock, createLink, deleteBlock, deleteLink } from '../../../services/api';

interface UseActionsProps {
  blocks: BlockData[];
  links: LinkData[];
  sublevels: SublevelData[];
  setBlocks: (blocks: BlockData[]) => void;
  setLinks: (links: LinkData[]) => void;
  setSublevels: (sublevels: SublevelData[]) => void;
  clearSelection: () => void;
  loadLayoutData: () => void; // Добавляем для обновления данных после операций
}

export const useActions = ({
  blocks,
  links,
  sublevels,
  setBlocks,
  setLinks,
  setSublevels,
  clearSelection,
  loadLayoutData
}: UseActionsProps) => {
  // Создание нового блока на подуровне
  const handleCreateBlockOnSublevel = useCallback(async (x: number, y: number, sublevelId: number): Promise<BlockData | null> => {
    try {
      console.log(`Creating block at (${x}, ${y}) on sublevel ${sublevelId}`);
      
      const sublevel = sublevels.find(sl => sl.id === sublevelId);
      if (!sublevel) {
        console.error('Sublevel not found:', sublevelId);
        return null;
      }

      // Вызываем реальный API для создания блока
      const response = await createBlock('Новый блок');
      
      if (!response.success || !response.block) {
        console.error('Failed to create block:', response);
        return null;
      }

      // Создаем локальный объект с координатами для UI
      const newBlockData: BlockData = {
        id: response.block.id,
        text: response.block.content,
        x: Math.round(x / 50) * 50,
        y: sublevel.min_y ?? 0,
        level: response.block.level,
        layer: response.block.layer ?? Math.round(x / 250),
        sublevel: response.block.sublevel_id
      };
      
      // Оптимистично обновляем UI
      const newBlocks = [...blocks, newBlockData];
      setBlocks(newBlocks);
      
      // Обновляем подуровень
      const newSublevels = sublevels.map(sl => 
        sl.id === sublevelId 
          ? { ...sl, block_ids: [...sl.block_ids, newBlockData.id] }
          : sl
      );
      setSublevels(newSublevels);
      
      console.log('Block created on sublevel:', newBlockData);
      
      // Обновляем данные из сервера для получения финальных координат
      setTimeout(() => {
        loadLayoutData();
      }, 100);
      
      return newBlockData;
      
    } catch (error) {
      console.error('Ошибка при создании блока на подуровне:', error);
      return null;
    }
  }, [blocks, sublevels, setBlocks, setSublevels, loadLayoutData]);

  // Создание нового блока (оригинальный метод для клика по canvas)
  const handleCreateBlock = useCallback(async (x: number, y: number) => {
    // Находим ближайший подуровень
    if (sublevels.length > 0) {
      const nearestSublevel = sublevels.reduce((nearest, sublevel) => {
        const distance = Math.abs((sublevel.min_y ?? 0) - y);
        const nearestDistance = Math.abs((nearest.min_y ?? 0) - y);
        return distance < nearestDistance ? sublevel : nearest;
      }, sublevels[0]);

      if (nearestSublevel && nearestSublevel.min_y !== undefined) {
        await handleCreateBlockOnSublevel(x, nearestSublevel.min_y, nearestSublevel.id);
        return;
      }
    }
    
    // Если подуровней нет или ближайший не найден, создаем обычным способом
    try {
      console.log(`Creating block at (${x}, ${y})`);
      
      // Вызываем реальный API для создания блока
      const response = await createBlock('Новый блок');
      
      if (!response.success || !response.block) {
        console.error('Failed to create block:', response);
        return;
      }

      // Создаем локальный объект с координатами для UI
      const newBlockData: BlockData = {
        id: response.block.id,
        text: response.block.content,
        x: Math.round(x / 50) * 50,
        y: Math.round(y / 50) * 50,
        level: response.block.level,
        layer: response.block.layer ?? 1,
        sublevel: response.block.sublevel_id
      };
      
      const newBlocks = [...blocks, newBlockData];
      setBlocks(newBlocks);
      console.log('Block created:', newBlockData);
      
      // Обновляем данные из сервера для получения финальных координат
      setTimeout(() => {
        loadLayoutData();
      }, 100);
      
    } catch (error) {
      console.error('Ошибка при создании блока:', error);
    }
  }, [sublevels, blocks, setBlocks, handleCreateBlockOnSublevel, loadLayoutData]);

  // Создание связи
  const handleCreateLink = useCallback(async (fromId: string, toId: string) => {
    try {
      console.log(`Creating link ${fromId} -> ${toId}`);
      
      // Вызываем реальный API для создания связи
      const response = await createLink(fromId, toId);
      
      if (!response.success || !response.link) {
        console.error('Failed to create link:', response);
        return;
      }
      
      const newLinkData: LinkData = {
        id: response.link.id,
        source_id: response.link.source_id,
        target_id: response.link.target_id
      };
      
      // Оптимистично обновляем UI
      const newLinks = [...links, newLinkData];
      setLinks(newLinks);
      console.log('Link created:', newLinkData);
      
      // Обновляем данные из сервера для получения обновленной укладки
      setTimeout(() => {
        loadLayoutData();
      }, 100);
      
    } catch (error) {
      console.error('Ошибка при создании связи:', error);
    }
  }, [links, setLinks, loadLayoutData]);

  // Удаление блока
  const handleDeleteBlock = useCallback(async (blockId: string) => {
    try {
      console.log(`Deleting block ${blockId}`);
      
      // Вызываем реальный API для удаления блока
      const response = await deleteBlock(blockId);
      
      if (!response.success) {
        console.error('Failed to delete block:', response.error);
        return;
      }
      
      // Оптимистично обновляем UI
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
      
      // Обновляем данные из сервера для получения обновленной укладки
      setTimeout(() => {
        loadLayoutData();
      }, 100);
      
    } catch (error) {
      console.error('Ошибка при удалении блока:', error);
    }
  }, [blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection, loadLayoutData]);

  // Удаление связи
  const handleDeleteLink = useCallback(async (linkId: string) => {
    try {
      console.log(`Deleting link ${linkId}`);
      
      // Вызываем реальный API для удаления связи
      const response = await deleteLink(linkId);
      
      if (!response.success) {
        console.error('Failed to delete link:', response.error);
        return;
      }
      
      // Оптимистично обновляем UI
      const newLinks = links.filter((link: LinkData) => link.id !== linkId);
      setLinks(newLinks);
      clearSelection();
      
      console.log('Link deleted:', linkId);
      
      // Обновляем данные из сервера для получения обновленной укладки
      setTimeout(() => {
        loadLayoutData();
      }, 100);
      
    } catch (error) {
      console.error('Ошибка при удалении связи:', error);
    }
  }, [links, setLinks, clearSelection, loadLayoutData]);

  return {
    handleCreateBlock,
    handleCreateBlockOnSublevel,
    handleCreateLink,
    handleDeleteBlock,
    handleDeleteLink
  };
}; 