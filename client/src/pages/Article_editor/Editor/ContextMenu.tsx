import React, { useEffect, useRef, useCallback } from 'react';
import styles from '../Article_editor.module.css';

interface ContextMenuProps {
  x: number;
  y: number;
  blockIndex: number;
  totalBlocks: number;
  onDelete: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onClose: () => void;
}

const ContextMenu: React.FC<ContextMenuProps> = ({
  x, y, blockIndex, totalBlocks, onDelete, onMoveUp, onMoveDown, onClose,
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onCloseRef.current();
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current();
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, []);

  const handleDelete = useCallback(() => { onDelete(blockIndex); onClose(); }, [blockIndex, onDelete, onClose]);
  const handleMoveUp = useCallback(() => { onMoveUp(blockIndex); onClose(); }, [blockIndex, onMoveUp, onClose]);
  const handleMoveDown = useCallback(() => { onMoveDown(blockIndex); onClose(); }, [blockIndex, onMoveDown, onClose]);

  const menuX = Math.min(x, window.innerWidth - 160);
  const menuY = Math.min(y, window.innerHeight - 140);

  return (
    <div
      ref={ref}
      className={styles.contextMenu}
      style={{ left: menuX, top: menuY }}
    >
      <button
        className={`${styles.contextMenuItem} ${styles.danger}`}
        onClick={handleDelete}
      >
        Удалить
      </button>
      <button
        className={styles.contextMenuItem}
        disabled={blockIndex === 0}
        onClick={handleMoveUp}
      >
        ↑ Вверх
      </button>
      <button
        className={styles.contextMenuItem}
        disabled={blockIndex === totalBlocks - 1}
        onClick={handleMoveDown}
      >
        ↓ Вниз
      </button>
    </div>
  );
};

export default ContextMenu;
