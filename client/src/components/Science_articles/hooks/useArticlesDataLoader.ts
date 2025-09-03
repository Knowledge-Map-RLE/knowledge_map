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

  const loadNextPage = useCallback(async () => {
    if (isLoading) {
      console.log(`[ArticlesPage] Skipping loadNextPage - already loading`);
      return;
    }
    
    // Простая проверка - если уже загружены блоки и это первая страница, пропускаем
    if (blocks.length > 0 && pageOffset === 0) {
      console.log(`[ArticlesPage] Skipping loadNextPage - blocks already exist (${blocks.length} blocks)`);
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
  }, [isLoading, pageOffset, blocks.length, pageLimit, isBootLoading, loadedBlockIdsRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, setIsBootLoading, setPageOffset]);

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
