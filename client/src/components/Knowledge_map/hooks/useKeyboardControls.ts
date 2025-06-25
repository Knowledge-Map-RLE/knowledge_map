import { useEffect, useRef, useCallback, useState } from 'react';
import { EditMode, type BlockData, type LinkCreationState, type LinkCreationStep } from '../types';

interface UseKeyboardControlsProps {
  setCurrentMode: (mode: EditMode) => void;
  setLinkCreationState: (state: LinkCreationState) => void;
  currentMode: EditMode;
  linkCreationState: LinkCreationState;
  selectedBlocks?: string[];
  blocks?: BlockData[];
  levels?: any[];
  onMovePinnedBlock?: (blockId: string, direction: 'up' | 'down') => void;
}

interface UseKeyboardControlsResult {
  currentMode: EditMode;
  isQPressed: boolean;
}

export function useKeyboardControls(): UseKeyboardControlsResult {
  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [isQPressed, setIsQPressed] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'q' || event.key === 'Q') {
        setIsQPressed(true);
        setCurrentMode(EditMode.CREATE_BLOCKS);
      }
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.key === 'q' || event.key === 'Q') {
        setIsQPressed(false);
        setCurrentMode(EditMode.SELECT);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  return {
    currentMode,
    isQPressed
  };
}

export const useKeyboardControlsWithProps = ({
  setCurrentMode,
  setLinkCreationState,
  currentMode,
  linkCreationState,
  selectedBlocks = [],
  blocks = [],
  levels = [],
  onMovePinnedBlock
}: UseKeyboardControlsProps) => {
  const pressedKeys = useRef<Set<string>>(new Set());

  // Оборачиваем setCurrentMode в useCallback для логирования
  const setModeWithLogging = useCallback((mode: EditMode) => {
    console.log('useKeyboardControls setting mode:', mode);
    setCurrentMode(mode);
  }, [setCurrentMode]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Игнорируем автоповтор клавиш
      if (e.repeat) return;
      
      // Проверяем, что клавиша еще не нажата
      if (pressedKeys.current.has(e.code)) return;
      pressedKeys.current.add(e.code);

      console.log('KeyDown:', e.code, 'Current mode:', currentMode);

      // Escape всегда возвращает в режим SELECT и сбрасывает создание связей
      if (e.code === 'Escape') {
        setModeWithLogging(EditMode.SELECT);
        setLinkCreationState({ step: 'waiting' });
        return;
      }

      // Логика переключения режимов
      switch (e.code) {
        case 'KeyQ':
          if (currentMode !== EditMode.CREATE_BLOCKS) {
            setModeWithLogging(EditMode.CREATE_BLOCKS);
          }
          break;
        case 'KeyW':
          if (currentMode !== EditMode.CREATE_LINKS) {
            setModeWithLogging(EditMode.CREATE_LINKS);
            setLinkCreationState({ step: 'selecting_source' });
          }
          break;
        case 'KeyE':
          if (currentMode !== EditMode.DELETE) {
            setModeWithLogging(EditMode.DELETE);
          }
          break;
          
        case 'ArrowUp':
          if (e.ctrlKey && selectedBlocks.length === 1 && onMovePinnedBlock) {
            e.preventDefault();
            const selectedBlockId = selectedBlocks[0];
            const selectedBlock = blocks.find(b => b.id === selectedBlockId);
            if (selectedBlock?.is_pinned) {
              onMovePinnedBlock(selectedBlockId, 'up');
            }
          }
          break;
          
        case 'ArrowDown':
          if (e.ctrlKey && selectedBlocks.length === 1 && onMovePinnedBlock) {
            e.preventDefault();
            const selectedBlockId = selectedBlocks[0];
            const selectedBlock = blocks.find(b => b.id === selectedBlockId);
            if (selectedBlock?.is_pinned) {
              onMovePinnedBlock(selectedBlockId, 'down');
            }
          }
          break;
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      // Удаляем клавишу из набора нажатых
      pressedKeys.current.delete(e.code);
      
      console.log('KeyUp:', e.code, 'Current mode:', currentMode);

      // Возвращаемся в SELECT только если отпущена соответствующая клавиша текущего режима
      switch (e.code) {
        case 'KeyQ':
          if (currentMode === EditMode.CREATE_BLOCKS) {
            setModeWithLogging(EditMode.SELECT);
          }
          break;
        case 'KeyW':
          if (currentMode === EditMode.CREATE_LINKS && linkCreationState.step === 'waiting') {
            setModeWithLogging(EditMode.SELECT);
          }
          break;
        case 'KeyE':
          if (currentMode === EditMode.DELETE) {
            setModeWithLogging(EditMode.SELECT);
          }
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [currentMode, setModeWithLogging, setLinkCreationState, linkCreationState, selectedBlocks, blocks, onMovePinnedBlock]);
}; 