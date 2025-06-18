import { useState, useCallback } from 'react';
import type { BlockData, LinkData } from '../types';

interface UseSelectionStateResult {
  selectedBlocks: string[];
  selectedLinks: string[];
  handleBlockSelection: (blockId: string) => void;
  handleLinkSelection: (linkId: string) => void;
  clearSelection: () => void;
}

export const useSelectionState = (): UseSelectionStateResult => {
  const [selectedBlocks, setSelectedBlocks] = useState<string[]>([]);
  const [selectedLinks, setSelectedLinks] = useState<string[]>([]);

  const handleBlockSelection = useCallback((blockId: string) => {
    setSelectedBlocks(prev => 
      prev.includes(blockId) 
        ? prev.filter(id => id !== blockId)
        : [...prev, blockId]
    );
  }, []);

  const handleLinkSelection = useCallback((linkId: string) => {
    setSelectedLinks(prev => 
      prev.includes(linkId) 
        ? prev.filter(id => id !== linkId)
        : [...prev, linkId]
    );
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedBlocks([]);
    setSelectedLinks([]);
  }, []);

  return {
    selectedBlocks,
    selectedLinks,
    handleBlockSelection,
    handleLinkSelection,
    clearSelection
  };
}; 