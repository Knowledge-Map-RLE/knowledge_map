import React, { useCallback, useEffect, useRef, useState } from 'react';
import styles from './BlockContextMenu.module.css';
import { SCALE_UNITS, type ScaleUnit, readableScaleToExponent, exponentToReadableScale } from '../utils/scaleUtils';

interface BlockContextMenuProps {
  x: number;
  y: number;
  isPinned: boolean;
  doi?: string;
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
  doi,
  currentPhysicalScale = 0, // по умолчанию 1 метр (10^0)
  onPin,
  onUnpin,
  onPinWithScale,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const showDoi = Boolean(doi);
  const shortDoi = doi && doi.length > 32 ? `${doi.slice(0, 29)}...` : doi;
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
    const handleClickOutside = (event: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    // capture-фаза: ловим клики (ЛКМ и ПКМ) где угодно вне меню.
    // Только capture на document доходит до нас даже тогда, когда страница
    // вешает блокировщики pointer-событий на canvas при открытом меню.
    document.addEventListener('pointerdown', handleClickOutside, true);
    document.addEventListener('keydown', handleEscape);

    return () => {
      document.removeEventListener('pointerdown', handleClickOutside, true);
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

  // Копируем DOI в полном формате (как URL), чтобы его можно было
  // вставить как ссылку на страницу-источник статьи.
  const handleCopyDoi = useCallback(() => {
    if (!doi) return;
    const url = `https://doi.org/${doi}`;
    const copyText = async () => {
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(url);
        } else {
          const textarea = document.createElement('textarea');
          textarea.value = url;
          textarea.style.position = 'fixed';
          textarea.style.opacity = '0';
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand('copy');
          document.body.removeChild(textarea);
        }
      } catch (error) {
        console.error('Ошибка копирования DOI:', error);
      }
    };
    copyText();
    onClose();
  }, [doi, onClose]);

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
          {showDoi && (
            <button
              className={styles.menuItem}
              onClick={() => handleMenuItemClick(handleCopyDoi)}
            >
              Скопировать DOI {shortDoi}
            </button>
          )}
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