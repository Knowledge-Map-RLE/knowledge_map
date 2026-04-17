import React, { useEffect, useRef, useState } from 'react';
import styles from './BlockContextMenu.module.css';
import { SCALE_UNITS, type ScaleUnit, readableScaleToExponent, exponentToReadableScale } from '../utils/scaleUtils';

interface BlockContextMenuProps {
  x: number;
  y: number;
  isPinned: boolean;
  currentPhysicalScale?: number; // текущий физический масштаб блока
  onPin: () => void;
  onUnpin: () => void;
  onPinWithScale: (physicalScale: number) => void; // новый колбэк для закрепления с масштабом
  onClose: () => void;
}

export const BlockContextMenu: React.FC<BlockContextMenuProps> = ({
  x,
  y,
  isPinned,
  currentPhysicalScale = 0, // по умолчанию 1 метр (10^0)
  onPin,
  onUnpin,
  onPinWithScale,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const [showScaleInput, setShowScaleInput] = useState(false);
  const [scaleValue, setScaleValue] = useState(1);
  const [selectedUnit, setSelectedUnit] = useState<ScaleUnit>(SCALE_UNITS.find(u => u.exponent === 0)!);

  // Инициализируем значения из текущего масштаба
  useEffect(() => {
    const { value, unit } = exponentToReadableScale(currentPhysicalScale);
    setScaleValue(value);
    setSelectedUnit(unit);
  }, [currentPhysicalScale]);

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
    if (!showScaleInput) {
      onClose();
    }
  };

  const handlePinWithScale = () => {
    const physicalScale = readableScaleToExponent(scaleValue, selectedUnit);
    onPinWithScale(physicalScale);
    onClose();
  };

  const handleScaleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    if (!isNaN(value) && value > 0) {
      setScaleValue(value);
    }
  };

  const handleUnitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const unit = SCALE_UNITS.find(u => u.symbol === e.target.value);
    if (unit) {
      setSelectedUnit(unit);
    }
  };

  return (
    <div
      ref={menuRef}
      className={styles.contextMenu}
      style={{
        left: x,
        top: y,
      }}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {!showScaleInput ? (
        <>
          <button
            className={styles.menuItem}
            onClick={() => handleMenuItemClick(isPinned ? onUnpin : onPin)}
          >
            {isPinned ? '📌 Открепить от уровня' : '📌 Закрепить за уровнем'}
          </button>
          
          {!isPinned && (
            <button
              className={styles.menuItem}
              onClick={() => setShowScaleInput(true)}
            >
              📏 Закрепить за уровнем с масштабом
            </button>
          )}
        </>
      ) : (
        <div className={styles.scaleInput}>
          <div className={styles.scaleInputHeader}>
            <span>📏 Физический масштаб уровня</span>
            <button 
              className={styles.closeButton}
              onClick={() => setShowScaleInput(false)}
            >
              ✕
            </button>
          </div>
          
          <div className={styles.inputRow}>
            <input
              type="number"
              value={scaleValue}
              onChange={handleScaleChange}
              min="0.001"
              step="any"
              className={styles.scaleValueInput}
              autoFocus
            />
            <select
              value={selectedUnit.symbol}
              onChange={handleUnitChange}
              className={styles.unitSelect}
            >
              {SCALE_UNITS.map(unit => (
                <option key={unit.symbol} value={unit.symbol}>
                  {unit.symbol}
                </option>
              ))}
            </select>
          </div>
          
          <div className={styles.scaleButtons}>
            <button
              className={styles.confirmButton}
              onClick={handlePinWithScale}
            >
              Закрепить
            </button>
            <button
              className={styles.cancelButton}
              onClick={() => setShowScaleInput(false)}
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}; 