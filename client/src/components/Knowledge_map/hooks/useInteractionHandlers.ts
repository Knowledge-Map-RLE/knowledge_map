import { useCallback } from 'react';
import type { BlockData, LinkCreationState } from '../types';
import { EditMode } from '../types';

interface UseInteractionHandlersProps {
  currentMode: EditMode;
  linkCreationState: LinkCreationState;
  setLinkCreationState: (state: LinkCreationState) => void;
  setBlocks: (updateFn: (prev: BlockData[]) => BlockData[]) => void;
  blocks: BlockData[];
  handleBlockSelection: (blockId: string) => void;
  handleLinkSelection: (linkId: string) => void;
  handleCreateLink: (fromId: string, toId: string) => void;
  handleDeleteBlock: (blockId: string) => void;
  handleDeleteLink: (linkId: string) => void;
  clearSelection: () => void;
}

export const useInteractionHandlers = ({
  currentMode,
  linkCreationState,
  setLinkCreationState,
  setBlocks,
  blocks,
  handleBlockSelection,
  handleLinkSelection,
  handleCreateLink,
  handleDeleteBlock,
  handleDeleteLink,
  clearSelection
}: UseInteractionHandlersProps) => {

  const handleBlockClick = useCallback((blockId: string) => {
    const clickedBlock = blocks.find(block => block.id === blockId);
    if (!clickedBlock) return;
    
    switch (currentMode) {
      case EditMode.SELECT: 
        handleBlockSelection(blockId); 
        break;
      case EditMode.CREATE_LINKS:
        if (linkCreationState.step === 'selecting_source') {
          setLinkCreationState({ step: 'selecting_target', sourceBlock: clickedBlock });
        } else if (linkCreationState.step === 'selecting_target' && 'sourceBlock' in linkCreationState) {
          handleCreateLink(linkCreationState.sourceBlock.id, blockId);
          setLinkCreationState({ step: 'selecting_source' });
        }
        break;
      case EditMode.DELETE: 
        handleDeleteBlock(blockId); 
        break;
    }
  }, [currentMode, linkCreationState, setLinkCreationState, blocks, handleBlockSelection, handleCreateLink, handleDeleteBlock]);

  const handleBlockMouseEnter = useCallback((blockId: string) => {
    setBlocks(prev => prev.map(b =>
      b.id === blockId ? { ...b, isHovered: true } : { ...b, isHovered: false }
    ));
  }, [setBlocks]);

  const handleBlockMouseLeave = useCallback((blockId: string, event: any) => {
    const relatedTarget = event.currentTarget.parent?.children.find(
      (child: any) => child !== event.currentTarget && child.containsPoint?.(event.global)
    );
    if (!relatedTarget) {
      setBlocks(prev => prev.map(b =>
        b.id === blockId ? { ...b, isHovered: false } : b
      ));
    }
  }, [setBlocks]);

  const handleArrowHover = useCallback((blockId: string, arrowPosition: 'left' | 'right' | null) => {
    setBlocks(prev => prev.map(b =>
      b.id === blockId ? { ...b, hoveredArrow: arrowPosition } : b
    ));
  }, [setBlocks]);

  const handleLinkClick = useCallback((linkId: string) => {
    switch (currentMode) {
      case EditMode.SELECT: 
        handleLinkSelection(linkId); 
        break;
      case EditMode.DELETE: 
        handleDeleteLink(linkId); 
        break;
    }
  }, [currentMode, handleLinkSelection, handleDeleteLink]);

  const handleCanvasClick = useCallback(() => {
    if (currentMode === EditMode.SELECT) {
      clearSelection();
    }
  }, [currentMode, clearSelection]);

  return {
    handleBlockClick,
    handleBlockMouseEnter,
    handleBlockMouseLeave,
    handleArrowHover,
    handleLinkClick,
    handleCanvasClick
  };
}; 