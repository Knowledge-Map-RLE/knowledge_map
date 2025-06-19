import type { EditMode, LinkCreationStep } from './types';
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
      case 'SELECT':
        return 'Выделение';
      case 'CREATE_BLOCKS':
        return 'Создание блоков (Q)';
      case 'CREATE_LINKS':
        if (linkCreationStep === 'selecting_source') {
          return 'Выберите первый блок (W)';
        } else if (linkCreationStep === 'selecting_target') {
          return 'Выберите второй блок (W)';
        }
        return 'Создание связей (W)';
      case 'DELETE':
        return 'Удаление (E)';
      default:
        return 'Неизвестный режим';
    }
  };

  const getModeColor = () => {
    switch (currentMode) {
      case 'SELECT':
        return '#6b7280';
      case 'CREATE_BLOCKS':
        return '#10b981';
      case 'CREATE_LINKS':
        return '#3b82f6';
      case 'DELETE':
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
      
      {currentMode !== 'SELECT' && (
        <div className={styles.hint}>
          Отпустите клавишу для возврата к выделению
        </div>
      )}
    </div>
  );
} 