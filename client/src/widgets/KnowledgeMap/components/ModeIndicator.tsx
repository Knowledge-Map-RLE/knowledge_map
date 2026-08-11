import type { EditMode, LinkCreationStep } from '../types';
import { EditMode as EditModeValue } from '../types';
import styles from './ModeIndicator.module.css';

interface ModeIndicatorProps {
  currentMode: EditMode;
  linkCreationStep?: LinkCreationStep;
}

export default function ModeIndicator({ 
  currentMode, 
  linkCreationStep 
}: ModeIndicatorProps) {
  const getModeText = () => {
    switch (currentMode) {
      case EditModeValue.SELECT:
        return 'Выделение';
      case EditModeValue.CREATE_BLOCKS:
        return 'Создание блоков (Q)';
      case EditModeValue.CREATE_LINKS:
        if (linkCreationStep === 'select_source') {
          return 'Выберите первый блок (W)';
        } else if (linkCreationStep === 'select_target') {
          return 'Выберите второй блок (W)';
        }
        return 'Создание связей (W)';
      case EditModeValue.DELETE:
        return 'Удаление (E)';
      default:
        return 'Неизвестный режим';
    }
  };

  const getModeColor = () => {
    switch (currentMode) {
      case EditModeValue.SELECT:
        return '#6b7280';
      case EditModeValue.CREATE_BLOCKS:
        return '#10b981';
      case EditModeValue.CREATE_LINKS:
        return '#3b82f6';
      case EditModeValue.DELETE:
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  return (
    <div className={styles.modeIndicator}>
      <div 
        className={styles.modeText}
        style={{ color: getModeColor() }}
      >
        <div className={styles.modeIcon} style={{ backgroundColor: getModeColor() }}></div>
        {getModeText()}
      </div>
      
      {currentMode !== EditModeValue.SELECT && (
        <div className={styles.hint}>
          Отпустите клавишу для возврата к выделению
        </div>
      )}
    </div>
  );
} 