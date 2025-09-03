import { useCallback } from 'react';
import { useArticlesData } from './useArticlesData';

export function useArticlesDataLoader() {
  const {
    blocks,
    links,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    setBlocks,
    setLinks,
    setIsLoading,
    setIsBootLoading,
    setLoadError,
    setPageOffset,
    processServerBlocks,
    processServerLinks,
    updateBlocks,
    updateLinks,
    loadedBlockIdsRef,
    loadedLinkIdsRef
  } = useArticlesData();

  const loadNextPage = useCallback(async (centerX?: number, centerY?: number) => {
    if (isLoading) {
      console.log(`[ArticlesPage] Skipping loadNextPage - already loading`);
      return;
    }
    
    // Простая проверка только для первой постраничной загрузки
    if (centerX == null && centerY == null) {
      if (blocks.length > 0 && pageOffset === 0) {
        console.log(`[ArticlesPage] Skipping loadNextPage - blocks already exist (${blocks.length} blocks)`);
        return;
      }
    }
    
    setIsLoading(true);
    setLoadError(null);
    
    try {
      let url: string;
      if (centerX != null && centerY != null) {
        const center_level = Math.max(0, Math.round(centerY / 120));
        const center_layer = Math.max(0, Math.round(centerX / 20));
        url = `http://localhost:8000/layout/articles_page?offset=0&limit=${pageLimit}&center_layer=${center_layer}&center_level=${center_level}`;
        console.log(`[ArticlesPage] Loading around center=(${center_layer},${center_level}) limit ${pageLimit}`);
      } else {
        url = `http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}`;
        console.log(`[ArticlesPage] Loading page ${pageOffset + 1} with limit ${pageLimit}`);
      }
      
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`[ArticlesPage] received page:`, data);
      
      if (data && data.success) {
        const serverBlocks = Array.isArray(data.blocks) ? data.blocks : [];
        const serverLinks = Array.isArray(data.links) ? data.links : [];

        console.log(`[ArticlesPage] blocks: ${serverBlocks.length}, links: ${serverLinks.length}`);
        
        const processedBlocks = processServerBlocks(serverBlocks);
        const processedLinks = processServerLinks(serverLinks);
        
        console.log(`[ArticlesPage] Обработано блоков: ${processedBlocks.length}, связей: ${processedLinks.length}`);
        
        // Обновляем состояние
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
        
        console.log(`[ArticlesPage] Состояние обновлено, processedBlocks: ${processedBlocks.length}, processedLinks: ${processedLinks.length}`);
        
        // Убираем экран загрузки при первой загрузке
        if (isBootLoading && processedBlocks.length > 0) {
          console.log(`[ArticlesPage] Убираем экран загрузки, processedBlocks: ${processedBlocks.length}`);
          setIsBootLoading(false);
        }
        
        // Переходим к следующей странице только для постраничной загрузки
        if (centerX == null && centerY == null) {
          setPageOffset(prev => prev + pageLimit);
        }
        
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
  }, [isLoading, pageOffset, blocks.length, pageLimit, isBootLoading, loadedBlockIdsRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, setIsBootLoading, setPageOffset]);

  const loadAround = useCallback(async (centerX: number, centerY: number) => {
    if (isLoading) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      // Преобразуем world Y в уровень, шаг 120 соответствует серверу
      const center_level = Math.max(0, Math.round(centerY / 120));
      const center_layer = Math.max(0, Math.round(centerX / 20));
      console.log(`[ArticlesPage] loadAround center=(${center_layer},${center_level})`);
      const response = await fetch(`http://localhost:8000/layout/articles_page?offset=0&limit=${pageLimit}&center_layer=${center_layer}&center_level=${center_level}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data && data.success) {
        const processedBlocks = processServerBlocks(data.blocks || []);
        const processedLinks = processServerLinks(data.links || []);
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
      }
    } catch (e: any) {
      console.error('loadAround error', e);
      setLoadError(e?.message || 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, pageLimit, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError]);

  return {
    blocks,
    links,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    loadNextPage
  };
}
