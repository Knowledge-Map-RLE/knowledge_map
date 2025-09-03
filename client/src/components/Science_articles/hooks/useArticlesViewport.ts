import { useEffect, useRef } from 'react';
import type { ViewportRef } from '../../Knowledge_map/Viewport';

export function useArticlesViewport(
  viewportRef: React.RefObject<ViewportRef>,
  blocks: any[],
  pageLimit: number,
  focusTargetId: string | null,
  setFocusTargetId: (id: string | null) => void,
  loadNextPage: () => void
) {
  const hasInitializedRef = useRef(false);

  // Первая загрузка страницы
  useEffect(() => { 
    if (!hasInitializedRef.current) {
      hasInitializedRef.current = true;
      loadNextPage();
    }
  }, [loadNextPage]);

  // Тригерим подгрузку при перемещении/зуме viewport
  useEffect(() => {
    const v = viewportRef.current as any;
    if (!v) return;
    
    let timer: any;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        // Загружаем вокруг видимого центра
        const center = viewportRef.current?.getWorldCenter?.();
        if (center) {
          // @ts-ignore — расширенная сигнатура loadNextPage не используется здесь
          (loadNextPage as any)?.(center.x, center.y);
        } else {
          loadNextPage();
        }
      }, 250);
    };
    
    // Слушаем события viewport
    const handleViewportMoved = () => schedule();
    const handleViewportZoomed = () => schedule();
    
    if (v.on) {
      v.on('moved', handleViewportMoved);
      v.on('zoomed', handleViewportZoomed);
    }
    
    return () => {
      clearTimeout(timer);
      if (v.off) {
        v.off('moved', handleViewportMoved);
        v.off('zoomed', handleViewportZoomed);
      }
    };
  }, [viewportRef, loadNextPage]);

  // Автоматическое центрирование только при первой загрузке
  useEffect(() => {
    if (blocks.length > 0 && !focusTargetId && blocks.length <= pageLimit) {
      const centerX = blocks.reduce((sum, block) => sum + (block.x || 0), 0) / blocks.length;
      const centerY = blocks.reduce((sum, block) => sum + (block.y || 0), 0) / blocks.length;

      setTimeout(() => {
        viewportRef.current?.focusOn(centerX, centerY);
      }, 100);
    }
  }, [blocks.length, focusTargetId, pageLimit, viewportRef]);

  // Фокус на конкретный блок
  useEffect(() => {
    if (focusTargetId && blocks.length > 0) {
      const targetBlock = blocks.find(b => b.id === focusTargetId);
      if (targetBlock && typeof targetBlock.x === 'number' && typeof targetBlock.y === 'number') {
        const targetX = targetBlock.x + 100; // BLOCK_WIDTH / 2
        const targetY = targetBlock.y;
        viewportRef.current?.focusOn(targetX, targetY);
        setFocusTargetId(null);
      }
    }
  }, [blocks, focusTargetId, setFocusTargetId, viewportRef]);

  return { hasInitializedRef };
}
