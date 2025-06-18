import { useEffect, useRef } from 'react';
import { EditMode } from '../types';
import type { LinkCreationState } from '../types';

interface UseKeyboardControlsProps {
  setCurrentMode: (mode: EditMode) => void;
  setLinkCreationState: (state: LinkCreationState) => void;
  currentMode: EditMode;
}

export const useKeyboardControls = ({
  setCurrentMode,
  setLinkCreationState,
  currentMode
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
          setCurrentMode(EditMode.CREATE_BLOCKS);
          setLinkCreationState({ step: 'waiting' });
          break;
        case 'KeyW':
          setCurrentMode(EditMode.CREATE_LINKS);
          setLinkCreationState({ step: 'waiting' });
          break;
        case 'KeyE':
          setCurrentMode(EditMode.DELETE);
          setLinkCreationState({ step: 'waiting' });
          break;
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      // Удаляем клавишу из набора нажатых
      pressedKeys.current.delete(e.code);
      
      console.log('KeyUp:', e.code, 'Current mode:', currentMode);

      // Для всех режимов возвращаемся в SELECT при отпускании клавиши
      switch (e.code) {
        case 'KeyQ':
          if (currentMode === EditMode.CREATE_BLOCKS) {
            setCurrentMode(EditMode.SELECT);
          }
          break;
        case 'KeyW':
          if (currentMode === EditMode.CREATE_LINKS) {
            setCurrentMode(EditMode.SELECT);
            // Сбрасываем состояние создания связи при выходе из режима
            setLinkCreationState({ step: 'waiting' });
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
  }, [currentMode, setCurrentMode, setLinkCreationState]);
}; 