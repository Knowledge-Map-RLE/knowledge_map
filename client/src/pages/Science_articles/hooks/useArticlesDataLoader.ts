import { useCallback, useEffect, useRef } from 'react';
import useArticlesData from './useArticlesData';
import { edgesByViewport } from '../../../services/api';

// Научные области (OpenAlex field.display_name), относящиеся к биологии и медицине.
// Используется как фильтр по умолчанию для карты научных статей.
export const BIOMED_FIELDS = [
  'Medicine',
  'Agricultural and Biological Sciences',
  'Biochemistry, Genetics and Molecular Biology',
  'Immunology and Microbiology',
  'Neuroscience',
  'Nursing',
  'Pharmacology, Toxicology and Pharmaceutics',
  'Dentistry',
  'Health Professions',
  'Environmental Science',
  'Veterinary',
];

// Ключ для сравнения списков полей (null/пустой = все области)
export function fieldsKey(fields: string[] | null | undefined): string {
  return fields && fields.length > 0 ? fields.join('|') : '__all__';
}

/**
 * Загрузчик блоков/связей для карты научных статей.
 *
 * @param viewportRef      ссылка на Viewport для определения границ окна
 * @param activeFields     активный фильтр по научным областям (field.display_name);
 *                         null/[] = все области. Управляется родителем (селект фильтра),
 *                         поэтому не может рассинхронизироваться с UI.
 */
export function useArticlesDataLoader(viewportRef?: any, activeFields?: string[] | null) {
  // Флаг: сервер вернул пустой ответ при первом запросе — данных нет, останавливаем опрос
  const dataExhaustedRef = useRef(false);
  // Текущий фильтр как ключ для детекции его смены родителем
  const activeFieldsKey = fieldsKey(activeFields);
  const prevFieldsKeyRef = useRef<string | null>(null);

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

  const fieldsQuery = useCallback(() => {
    if (!activeFields || activeFields.length === 0) return '';
    return activeFields.map(f => `fields=${encodeURIComponent(f)}`).join('&');
  }, [activeFieldsKey]); // eslint-disable-line react-hooks/exhaustive-deps



  // Функция центрирования viewport на координатах (0,0)
  const centerViewportOnOrigin = useCallback((newBlocks: any[]) => {
    if (viewportRef?.current && newBlocks.length > 0) {
      // Находим диапазон координат для определения масштаба
      const minX = Math.min(...newBlocks.map(b => b.x || 0));
      const maxX = Math.max(...newBlocks.map(b => b.x || 0));
      const minY = Math.min(...newBlocks.map(b => b.y || 0));
      const maxY = Math.max(...newBlocks.map(b => b.y || 0));
      
      const rangeX = maxX - minX;
      const rangeY = maxY - minY;

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
        }
      }, 100);
    }
  }, [viewportRef]);

  const loadNextPage = useCallback(async (centerX?: number, centerY?: number) => {
    if (dataExhaustedRef.current) return;
    if (isLoading) {
      return;
    }
    
    // Простая проверка только для первой постраничной загрузки
    if (centerX == null && centerY == null) {
      if (blocks.length > 0 && pageOffset === 0) {
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
        url = `http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}&center_x=${centerX}&center_y=${centerY}&${fieldsQuery()}`;
      } else {
        url = `http://localhost:8000/layout/articles_page?offset=${pageOffset}&limit=${pageLimit}&${fieldsQuery()}`;
      }
      
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data && data.success) {
        const serverBlocks = Array.isArray(data.blocks) ? data.blocks : [];
        const serverLinks = Array.isArray(data.links) ? data.links : [];
        
        const processedBlocks = processServerBlocks(serverBlocks);
        const processedLinks = processServerLinks(serverLinks);
        
        // Обновляем состояние
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
        
        // Убираем экран загрузки при первой загрузке (даже если блоков нет)
        if (isBootLoading) {
          setIsBootLoading(false);
          if (processedBlocks.length > 0) {
            centerViewportOnOrigin(processedBlocks);
          } else {
            // Первый запрос вернул 0 — данных нет, останавливаем опрос viewport
            dataExhaustedRef.current = true;
          }
        }
        
        // Переходим к следующей странице для обоих сценариев (и центр, и обычная страница)
        setPageOffset(prev => prev + pageLimit);
        
      } else {
        throw new Error((data && data.error) || 'Failed to load articles page');
      }
    } catch (error: any) {
      setLoadError(error?.message || 'Unknown error');
      if (isBootLoading) setIsBootLoading(false);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, pageOffset, blocks.length, pageLimit, isBootLoading, loadedBlockIdsRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, setIsBootLoading, setPageOffset, centerViewportOnOrigin, fieldsQuery]);

  const loadAround = useCallback(async (centerX: number, centerY: number) => {
    if (isLoading) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const response = await fetch(`http://localhost:8000/layout/articles_page?offset=0&limit=${pageLimit}&center_x=${centerX}&center_y=${centerY}&${fieldsQuery()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data && data.success) {
        const processedBlocks = processServerBlocks(data.blocks || []);
        const processedLinks = processServerLinks(data.links || []);
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
      }
    } catch (e: any) {
      setLoadError(e?.message || 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, pageLimit, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, fieldsQuery]);

  const loadEdgesByViewport = useCallback(async () => {
    if (isLoading || !viewportRef?.current) return;
    
    setIsLoading(true);
    setLoadError(null);
    
    try {
      // Получаем границы viewport
      const bounds = viewportRef.current.getWorldBounds();
      if (!bounds) {
        return;
      }
      
      const data = await edgesByViewport({
        ...bounds,
        fields: activeFields && activeFields.length > 0 ? activeFields : undefined,
      });
      
      if (data && data.blocks && data.links) {
        const processedBlocks = processServerBlocks(data.blocks);
        const processedLinks = processServerLinks(data.links);
        
        // Обновляем состояние
        updateBlocks(processedBlocks);
        updateLinks(processedLinks);
      }
    } catch (e: any) {
      setLoadError(e?.message || 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, viewportRef, processServerBlocks, processServerLinks, updateBlocks, updateLinks, setIsLoading, setLoadError, activeFieldsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Смена фильтра родителем: сбрасываем всё и загружаем заново.
  // Первая загрузка (prevFieldsKeyRef === null) пропускается: на старте фильтр
  // уже учитывается в полях URL запросов, отдельный сброс не нужен.
  useEffect(() => {
    if (prevFieldsKeyRef.current === null) {
      prevFieldsKeyRef.current = activeFieldsKey;
      return;
    }
    if (prevFieldsKeyRef.current === activeFieldsKey) {
      return;
    }
    prevFieldsKeyRef.current = activeFieldsKey;
    dataExhaustedRef.current = false;
    loadedBlockIdsRef.current = new Set();
    loadedLinkIdsRef.current = new Set();
    setBlocks([]);
    setLinks([]);
    setPageOffset(0);
    setIsBootLoading(true);
    setLoadError(null);
    // Дожидаемся следующего тика, чтобы состояние успело примениться
    setTimeout(() => loadNextPage(), 0);
  }, [activeFieldsKey, loadedBlockIdsRef, loadedLinkIdsRef, setBlocks, setLinks, setPageOffset, setIsBootLoading, setLoadError, loadNextPage]);

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
    loadEdgesByViewport,
  };
}