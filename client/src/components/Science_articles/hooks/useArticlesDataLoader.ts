import { useCallback } from 'react';
import useArticlesData from './useArticlesData';
import { edgesByViewport } from '../../../services/api';

export function useArticlesDataLoader(viewportRef?: any) {
  const {
    blocks,
    blockMap,  // ОПТИМИЗАЦИЯ: Добавлен Map для передачи в компоненты
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



  // Функция центрирования viewport на координатах (0,0)
  const centerViewportOnOrigin = useCallback((newBlocks: any[]) => {
    if (viewportRef?.current && newBlocks.length > 0) {
      console.log(`[ArticlesPage] Centering viewport on origin (0,0)`);
      
      // Находим диапазон координат для определения масштаба
      const minX = Math.min(...newBlocks.map(b => b.x || 0));
      const maxX = Math.max(...newBlocks.map(b => b.x || 0));
      const minY = Math.min(...newBlocks.map(b => b.y || 0));
      const maxY = Math.max(...newBlocks.map(b => b.y || 0));
      
      const rangeX = maxX - minX;
      const rangeY = maxY - minY;
      
      console.log(`[ArticlesPage] Coordinate range: x=${minX}-${maxX} (${rangeX}), y=${minY}-${maxY} (${rangeY})`);

      // Центрируем viewport на координатах (0,0)
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

          // Центрируем на координатах (0,0)
          viewportRef.current.focusOn(0, 0);
          console.log(`[ArticlesPage] Viewport centered on origin (0,0) with scale ${targetScale}`);
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
        // ВАЖНО: используем текущий pageOffset даже при загрузке вокруг центра,
        // чтобы получать следующую страницу, а не одни и те же элементы
        url = `http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}&center_x=${centerX}&center_y=${centerY}`;
        console.log(`[ArticlesPage] Loading around center=(${centerX},${centerY}) offset=${pageOffset} limit ${pageLimit}`);
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
          
          // Центрируем viewport на координатах (0,0) при первой загрузке
          centerViewportOnOrigin(processedBlocks);
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
  }, [isLoading, pageOffset, blocks.length, pageLimit, isBootLoading, loadedBlockIdsRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, setIsBootLoading, setPageOffset, centerViewportOnOrigin]);

  const loadAround = useCallback(async (centerX: number, centerY: number) => {
    if (isLoading) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      console.log(`[ArticlesPage] loadAround center=(${centerX},${centerY})`);
      const response = await fetch(`http://localhost:8000/layout/articles_page?offset=0&limit=${pageLimit}&center_x=${centerX}&center_y=${centerY}`);
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

  const loadEdgesByViewport = useCallback(async () => {
    if (isLoading || !viewportRef?.current) return;
    
    setIsLoading(true);
    setLoadError(null);
    
    try {
      // Получаем границы viewport
      const bounds = viewportRef.current.getWorldBounds();
      if (!bounds) {
        console.log('[ArticlesPage] No viewport bounds available');
        return;
      }
      
      console.log(`[ArticlesPage] Loading edges by viewport:`, bounds);
      
      const data = await edgesByViewport(bounds);
      
      if (data && data.blocks && data.links) {
        const processedBlocks = processServerBlocks(data.blocks);
        const processedLinks = processServerLinks(data.links);
        
        console.log(`[ArticlesPage] Loaded by viewport: ${processedBlocks.length} blocks, ${processedLinks.length} links`);
        
        // Обновляем состояние
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
      }
    } catch (e: any) {
      console.error('loadEdgesByViewport error', e);
      setLoadError(e?.message || 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, viewportRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError]);

  return {
    blocks,
    blockMap,  // ОПТИМИЗАЦИЯ: Передаём Map для O(1) поиска в компонентах
    links,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    loadNextPage,
    loadEdgesByViewport
  };
}
