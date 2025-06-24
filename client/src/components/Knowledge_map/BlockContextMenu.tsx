import React, { useEffect, useRef } from 'react';
import styles from './BlockContextMenu.module.css';

interface BlockContextMenuProps {
  x: number;
  y: number;
  isPinned: boolean;
  onPin: () => void;
  onUnpin: () => void;
  onClose: () => void;
}

export const BlockContextMenu: React.FC<BlockContextMenuProps> = ({
  x,
  y,
  isPinned,
  onPin,
  onUnpin,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose]);

  const handleMenuItemClick = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <div
      ref={menuRef}
      className={styles.contextMenu}
      style={{
        left: x,
        top: y,
      }}
    >
      <button
        className={styles.menuItem}
        onClick={() => handleMenuItemClick(isPinned ? onUnpin : onPin)}
      >
        {isPinned ? '📌 Открепить от уровня' : '📌 Закрепить за уровнем'}
      </button>
    </div>
  );
}; 