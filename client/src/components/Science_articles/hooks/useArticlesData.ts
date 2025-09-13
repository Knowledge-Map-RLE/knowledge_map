import { useState, useCallback } from 'react';

const useArticlesData = () => {
    const [blocks, setBlocks] = useState<any[]>([]);
    const [links, setLinks] = useState<any[]>([]);
    const [levels, setLevels] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isBootLoading, setIsBootLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [pageOffset, setPageOffset] = useState(0);
    const [pageLimit] = useState(1000);
    const loadedBlockIdsRef = { current: new Set<string>() };
    const loadedLinkIdsRef = { current: new Set<string>() };

    const processServerBlocks = useCallback((serverBlocks: any[]) => {
        console.log(`[processServerBlocks] Обрабатываем ${serverBlocks.length} блоков с сервера`);
        
        const processedBlocks = serverBlocks.map((b, index) => {
                    const processed = {
            id: b.id,
            title: b.title || b.id,
            x: (typeof b.x === 'number') ? b.x : undefined,
            y: (typeof b.y === 'number') ? b.y : undefined,
            layer: (typeof b.layer === 'number') ? b.layer : 0,
            level: (typeof b.level === 'number') ? b.level : 0,
            is_pinned: b.is_pinned || false
        };
            
            if (index < 3) {
                console.log(`[processServerBlocks] Блок ${index + 1}:`, processed);
            }
            
            return processed;
        });
        
        console.log(`[processServerBlocks] Обработано ${processedBlocks.length} блоков`);
        return processedBlocks;
    }, []);

    const updateBlocks = useCallback((newBlocks: any[]) => {
        console.log(`[updateBlocks] Обновляем блоки. Текущих: ${blocks.length}, новых: ${newBlocks.length}`);
        
        setBlocks(prevBlocks => {
            const existingIds = new Set(prevBlocks.map(b => b.id));
            const blocksToAdd = newBlocks.filter(b => !existingIds.has(b.id));
            const updatedBlocks = [...prevBlocks, ...blocksToAdd];
            
            console.log(`[updateBlocks] Добавлено ${blocksToAdd.length} новых блоков, всего: ${updatedBlocks.length}`);
            return updatedBlocks;
        });
        
        console.log(`[updateBlocks] Состояние обновлено, текущий blocks.length: ${blocks.length}`);
    }, [blocks.length]);

    const updateLinks = useCallback((newLinks: any[]) => {
        console.log(`[updateLinks] Обновляем связи. Текущих: ${links.length}, новых: ${newLinks.length}`);
        
        setLinks(prevLinks => {
            const existingIds = new Set(prevLinks.map(l => l.id));
            const linksToAdd = newLinks.filter(l => !existingIds.has(l.id));
            const updatedLinks = [...prevLinks, ...linksToAdd];
            
            console.log(`[updateLinks] Добавлено ${linksToAdd.length} новых связей, всего: ${updatedLinks.length}`);
            return updatedLinks;
        });
    }, [links.length]);

    const updateLevels = useCallback((newLevels: any[]) => {
        console.log(`[updateLevels] Обновляем уровни. Новых: ${newLevels.length}`);
        setLevels(newLevels);
    }, []);

    const processServerLinks = useCallback((serverLinks: any[]) => {
        console.log(`[processServerLinks] Обрабатываем ${serverLinks.length} связей с сервера`);
        
        const processedLinks = serverLinks.map((l, index) => {
                    const processed = {
            id: l.id,
            source_id: l.source_id || l.source,
            target_id: l.target_id || l.target,
            metadata: l.metadata || {}
        };
            
            if (index < 3) {
                console.log(`[processServerLinks] Связь ${index + 1}:`, processed);
            }
            
            return processed;
        });
        
        console.log(`[processServerLinks] Обработано ${processedLinks.length} связей`);
        return processedLinks;
    }, []);

    return {
        blocks,
        links,
        levels,
        isLoading,
        isBootLoading,
        loadError,
        pageOffset,
        pageLimit,
        processServerBlocks,
        processServerLinks,
        updateBlocks,
        updateLinks,
        updateLevels,
        setBlocks,
        setLinks,
        setLevels,
        setIsLoading,
        setIsBootLoading,
        setLoadError,
        setPageOffset,
        loadedBlockIdsRef,
        loadedLinkIdsRef
    };
};

export default useArticlesData;
