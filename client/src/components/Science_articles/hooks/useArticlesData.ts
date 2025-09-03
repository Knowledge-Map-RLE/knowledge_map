import { useState, useRef } from 'react';
import type { BlockData, LinkData } from '../../Knowledge_map/types';
import { BLOCK_WIDTH, BLOCK_HEIGHT } from '../../Knowledge_map/constants';

export function useArticlesData() {
  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [links, setLinks] = useState<LinkData[]>([]);
  const [levels, setLevels] = useState<any[]>([]);
  const [sublevels, setSublevels] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isBootLoading, setIsBootLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageOffset, setPageOffset] = useState<number>(0);
  const [pageLimit] = useState<number>(50);
  const [totalCount, setTotalCount] = useState<number>(0);
  
  const loadedBlockIdsRef = useRef<Set<string>>(new Set());
  const loadedLinkIdsRef = useRef<Set<string>>(new Set());

  const processServerBlocks = (serverBlocks: any[]): BlockData[] => {
    const processedBlocks: BlockData[] = [];
    
    console.log(`[processServerBlocks] Обрабатываем ${serverBlocks.length} блоков с сервера`);
    
    for (let i = 0; i < serverBlocks.length; i++) {
      const b = serverBlocks[i];
      const id = String(b.id);
      const bx = (typeof b.x === 'number') ? b.x : (b.x != null ? Number(b.x) : undefined);
      const by = (typeof b.y === 'number') ? b.y : (b.y != null ? Number(b.y) : undefined);
      const lvl = (typeof b.level === 'number') ? b.level : 0;
      const lay = (typeof b.layer === 'number') ? b.layer : 0;
      const sub = (typeof b.sublevel_id === 'number') ? b.sublevel_id : 0;
      
      // Fallback координаты, если x/y не определены
      const cols = 40;
      const col = i % cols;
      const row = Math.floor(i / cols);
      const fallbackX = col * (BLOCK_WIDTH + 40);
      const fallbackY = row * (BLOCK_HEIGHT + 60);
      const title = (b.content ?? b.title ?? b.name ?? id);
      
      // Нормализуем координаты: если нет или слишком большие, используем компактные из layer/level/sub
      const compactX = lay * 20.0 + sub * 15.0;
      const compactY = lvl * 120.0;
      const needCompact = (v: number | undefined) => (v == null) || !isFinite(v) || Math.abs(v) > 100000;
      const normalizedX = needCompact(bx) ? compactX : bx as number;
      const normalizedY = needCompact(by) ? compactY : by as number;

      // Логируем координаты для отладки
      if (i < 3) { // Логируем только первые 3 блока
        console.log(`[processServerBlocks] Блок ${i+1}:`, {
          id,
          title: title.substring(0, 30),
          serverX: b.x,
          serverY: b.y,
          processedX: bx,
          processedY: by,
          compactX,
          compactY,
          fallbackX,
          fallbackY,
          finalX: normalizedX,
          finalY: normalizedY
        });
      }
      
      const processedBlock = {
        id,
        text: String(title),
        content: String(title),
        x: normalizedX,
        y: normalizedY,
        level: lvl,
        physical_scale: typeof b.physical_scale === 'number' ? b.physical_scale : 0,
        sublevel: sub,
        layer: lay,
        is_pinned: Boolean(b.is_pinned)
      };
      
      processedBlocks.push(processedBlock);
    }
    
    console.log(`[processServerBlocks] Обработано ${processedBlocks.length} блоков`);
    return processedBlocks;
  };

  const processServerLinks = (serverLinks: any[]): LinkData[] => {
    return serverLinks.map(l => ({
      id: l.id ? String(l.id) : `${String(l.source_id)}-${String(l.target_id)}`,
      source_id: String(l.source_id),
      target_id: String(l.target_id)
    }));
  };

  const updateBlocks = (processedBlocks: BlockData[]) => {
    setBlocks(prevBlocks => {
      console.log(`[updateBlocks] Обновляем блоки. Текущих: ${prevBlocks.length}, новых: ${processedBlocks.length}`);
      
      // Проверяем, какие блоки уже есть
      const existingIds = new Set(prevBlocks.map(b => b.id));
      const newBlocks = [...prevBlocks];
      let addedCount = 0;
      
      for (const block of processedBlocks) {
        if (!existingIds.has(block.id)) {
          newBlocks.push(block);
          loadedBlockIdsRef.current.add(block.id);
          addedCount++;
        }
      }
      
      console.log(`[updateBlocks] Добавлено ${addedCount} новых блоков, всего: ${newBlocks.length}`);
      
      // Логируем изменение состояния
      setTimeout(() => {
        console.log(`[updateBlocks] Состояние обновлено, текущий blocks.length: ${blocks.length}`);
      }, 0);
      
      return newBlocks;
    });
  };

  const updateLinks = (processedLinks: LinkData[]) => {
    setLinks(prevLinks => {
      console.log(`[updateLinks] Обновляем связи. Текущих: ${prevLinks.length}, новых: ${processedLinks.length}`);
      
      // Проверяем, какие связи уже есть
      const existingIds = new Set(prevLinks.map(l => l.id));
      const newLinks = [...prevLinks];
      let addedCount = 0;
      
      for (const link of processedLinks) {
        if (!existingIds.has(link.id)) {
          newLinks.push(link);
          loadedLinkIdsRef.current.add(link.id);
          addedCount++;
        }
      }
      
      console.log(`[updateLinks] Добавлено ${addedCount} новых связей, всего: ${newLinks.length}`);
      return newLinks;
    });
  };

  const resetLayoutData = () => {
    loadedBlockIdsRef.current.clear();
    loadedLinkIdsRef.current.clear();
    setBlocks([]);
    setLinks([]);
    setPageOffset(0);
    setIsBootLoading(true);
  };

  return {
    // Состояние
    blocks,
    links,
    levels,
    sublevels,
    isLoading,
    isBootLoading,
    loadError,
    pageOffset,
    pageLimit,
    totalCount,
    
    // Сеттеры
    setBlocks,
    setLinks,
    setLevels,
    setSublevels,
    setIsLoading,
    setIsBootLoading,
    setLoadError,
    setPageOffset,
    setTotalCount,
    
    // Методы
    processServerBlocks,
    processServerLinks,
    updateBlocks,
    updateLinks,
    resetLayoutData,
    
    // Рефы
    loadedBlockIdsRef,
    loadedLinkIdsRef
  };
}
