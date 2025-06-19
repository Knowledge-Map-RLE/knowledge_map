import { useEffect, useRef } from 'react';
import { EditMode } from '../types';
import type { LinkCreationState } from '../types';

interface UseKeyboardControlsProps {
  setCurrentMode: (mode: EditMode) => void;
  setLinkCreationState: (state: LinkCreationState) => void;
  currentMode: EditMode;
  linkCreationState: LinkCreationState;
}

export const useKeyboardControls = ({
  setCurrentMode,
  setLinkCreationState,
  currentMode,
  linkCreationState
}: UseKeyboardControlsProps) => {
  const pressedKeys = useRef<Set<string>>(new Set());

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
        setCurrentMode(EditMode.SELECT);
        setLinkCreationState({ step: 'waiting' });
        return;
      }

      // Логика переключения режимов
      switch (e.code) {
        case 'KeyQ':
          if (currentMode !== EditMode.CREATE_BLOCKS) {
            setCurrentMode(EditMode.CREATE_BLOCKS);
          }
          break;
        case 'KeyW':
          if (currentMode !== EditMode.CREATE_LINKS) {
            setCurrentMode(EditMode.CREATE_LINKS);
          }
          break;
        case 'KeyE':
          if (currentMode !== EditMode.DELETE) {
            setCurrentMode(EditMode.DELETE);
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
            setCurrentMode(EditMode.SELECT);
          }
          break;
        case 'KeyW':
          if (currentMode === EditMode.CREATE_LINKS && linkCreationState.step === 'waiting') {
            setCurrentMode(EditMode.SELECT);
          }
          break;
        case 'KeyE':
          if (currentMode === EditMode.DELETE) {
            setCurrentMode(EditMode.SELECT);
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
  }, [currentMode, setCurrentMode, setLinkCreationState, linkCreationState]);
}; 