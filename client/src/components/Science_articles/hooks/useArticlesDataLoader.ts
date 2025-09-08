import { useCallback } from 'react';
import useArticlesData from './useArticlesData';

export function useArticlesDataLoader(viewportRef?: any) {
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



  // Функция центрирования viewport на блоках
  const centerViewportOnBlocks = useCallback((newBlocks: any[]) => {
    if (viewportRef?.current && newBlocks.length > 0) {
      // Находим центр всех блоков
      const centerX = newBlocks.reduce((sum, block) => sum + (block.x || 0), 0) / newBlocks.length;
      const centerY = newBlocks.reduce((sum, block) => sum + (block.y || 0), 0) / newBlocks.length;

      console.log(`[ArticlesPage] Centering viewport on blocks center: x=${centerX}, y=${centerY}`);
      
      // Находим диапазон координат для определения масштаба
      const minX = Math.min(...newBlocks.map(b => b.x || 0));
      const maxX = Math.max(...newBlocks.map(b => b.x || 0));
      const minY = Math.min(...newBlocks.map(b => b.y || 0));
      const maxY = Math.max(...newBlocks.map(b => b.y || 0));
      
      const rangeX = maxX - minX;
      const rangeY = maxY - minY;
      
      console.log(`[ArticlesPage] Coordinate range: x=${minX}-${maxX} (${rangeX}), y=${minY}-${maxY} (${rangeY})`);

      // Центрируем viewport на центр данных
      setTimeout(() => {
        if (viewportRef.current) {
          // Рассчитываем масштаб по обоим измерениям с небольшим отступом
          const padding = 400; // добавляем запас к диапазону, чтобы не упираться в края
          const fitX =  window.innerWidth  / Math.max(rangeX + padding, 100);
          const fitY =  window.innerHeight / Math.max(rangeY + padding, 100);
          const minScale = 0.2;
          const maxScale = 1.0;
          const targetScale = Math.max(minScale, Math.min(maxScale, Math.min(fitX, fitY)));

          // Устанавливаем масштаб (через setScale если доступен)
          if (typeof (viewportRef.current as any).setScale === 'function') {
            (viewportRef.current as any).setScale(targetScale);
          } else {
            (viewportRef.current as any).scale = targetScale;
          }

          viewportRef.current.focusOn(centerX, centerY);
          console.log(`[ArticlesPage] Viewport centered on blocks with scale ${targetScale}`);
        }
      }, 100);
    }
  }, [viewportRef]);

  const loadNextPage = useCallback(async (centerX?: number, centerY?: number) => {
    if (isLoading) {
      console.log(`[ArticlesPage] Skipping loadNextPage - already loading`);
      return;
    }
    
    // Простая проверка только для первой постраничной загрузки
    if (centerX == null && centerY == null) {
      if (blocks.length > 0 && pageOffset === 0) {
        console.log(`[ArticlesPage] Skipping loadNextPage - blocks already exist (${blocks.length} blocks)`);
        // НЕ возвращаемся - продолжаем загрузку для получения большего количества блоков
      }
    }
    
    setIsLoading(true);
    setLoadError(null);
    
    try {
      let url: string;
      if (centerX != null && centerY != null) {
        const center_level = Math.max(0, Math.round(centerY / 120));
        const center_layer = Math.max(0, Math.round(centerX / 20));
        // ВАЖНО: используем текущий pageOffset даже при загрузке вокруг центра,
        // чтобы получать следующую страницу, а не одни и те же 50 элементов
        url = `http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}&center_layer=${center_layer}&center_level=${center_level}`;
        console.log(`[ArticlesPage] Loading around center=(${center_layer},${center_level}) offset=${pageOffset} limit ${pageLimit}`);
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
          
          // Центрируем viewport на первой загрузке
          centerViewportOnBlocks(processedBlocks);
        }
        
        // Переходим к следующей странице для обоих сценариев (и центр, и обычная страница)
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
  }, [isLoading, pageOffset, blocks.length, pageLimit, isBootLoading, loadedBlockIdsRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, setIsBootLoading, setPageOffset, centerViewportOnBlocks]);

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
