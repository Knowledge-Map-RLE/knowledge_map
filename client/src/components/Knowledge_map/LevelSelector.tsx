import { useState } from 'react';
import type { BlockData } from './index';
import styles from './LevelSelector.module.css';

interface LevelSelectorProps {
  selectedBlock: BlockData;
  onMoveToLevel: (blockId: string, newLevel: number) => void;
  onClose: () => void;
}

export function LevelSelector({ selectedBlock, onMoveToLevel, onClose }: LevelSelectorProps) {
  const [newLevel, setNewLevel] = useState(selectedBlock.level);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onMoveToLevel(selectedBlock.id, newLevel);
    onClose();
  };

  const handleLevelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNewLevel(parseInt(e.target.value));
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <h3>Переместить блок на уровень</h3>
        <p><strong>Блок:</strong> {selectedBlock.text}</p>
        <p><strong>Текущий уровень:</strong> {selectedBlock.level}</p>
        
        <form onSubmit={handleSubmit}>
          <div className={styles.inputGroup}>
            <label htmlFor="level">Новый уровень:</label>
            <input
              id="level"
              type="number"
              value={newLevel}
              onChange={handleLevelChange}
              min="-10"
              max="10"
              step="1"
            />
          </div>
          
          <div className={styles.buttons}>
            <button type="submit" className={styles.moveButton}>
              Переместить
            </button>
            <button type="button" onClick={onClose} className={styles.cancelButton}>
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
} 