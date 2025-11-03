import React, { useState } from 'react';
import { ANNOTATION_CATEGORIES, getDefaultColor } from './annotationTypes';
import './AnnotationToolbar.css';

interface AnnotationToolbarProps {
  selectedType: string | null;
  selectedColor: string;
  onTypeSelect: (type: string) => void;
  onColorChange: (color: string) => void;
  relationMode: boolean;
  onRelationModeToggle: () => void;
  showRelations: boolean;
  onShowRelationsToggle: () => void;
  // Для мультиклассификации
  selectedTypes?: string[];
  onTypeToggle?: (type: string) => void;
  hasPendingSelection?: boolean;
}

const AnnotationToolbar: React.FC<AnnotationToolbarProps> = ({
  selectedType,
  selectedColor,
  onTypeSelect,
  onColorChange,
  relationMode,
  onRelationModeToggle,
  showRelations,
  onShowRelationsToggle,
  selectedTypes = [],
  onTypeToggle,
  hasPendingSelection = false,
}) => {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [showColorPicker, setShowColorPicker] = useState(false);

  const handleTypeClick = (type: string) => {
    // Если есть выделенный текст и onTypeToggle, используем мультивыбор
    if (hasPendingSelection && onTypeToggle) {
      onTypeToggle(type);
    } else {
      // Старое поведение для обратной совместимости
      onTypeSelect(type);
      const defaultColor = getDefaultColor(type);
      onColorChange(defaultColor);
    }
  };

  const toggleCategory = (category: string) => {
    setExpandedCategory(expandedCategory === category ? null : category);
  };

  return (
    <div className="annotation-toolbar">
      <div className="toolbar-section">
        <h4>Типы аннотаций</h4>
        {Object.entries(ANNOTATION_CATEGORIES).map(([category, types]) => (
          <div key={category} className="annotation-category">
            <div
              className="category-header"
              onClick={() => toggleCategory(category)}
              style={{ cursor: 'pointer', fontWeight: 'bold', padding: '8px 0' }}
            >
              {expandedCategory === category ? '▼' : '▶'} {category}
            </div>
            {expandedCategory === category && (
              <div className="category-types">
                {types.map((type) => {
                  const isSelected = hasPendingSelection
                    ? selectedTypes.includes(type)
                    : selectedType === type;
                  return (
                    <button
                      key={type}
                      className={`type-button ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleTypeClick(type)}
                      style={{
                        backgroundColor:
                          isSelected ? getDefaultColor(type) : '#f5f5f5',
                        color: isSelected ? '#000' : '#333',
                        border: isSelected ? '2px solid #000' : '1px solid #ddd',
                      }}
                      title={type}
                    >
                      {type}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="toolbar-section">
        <h4>Цвет</h4>
        <div className="color-picker-container">
          <div
            className="color-preview"
            style={{ backgroundColor: selectedColor }}
            onClick={() => setShowColorPicker(!showColorPicker)}
            title="Выбрать цвет"
          />
          {showColorPicker && (
            <div className="color-picker-popup">
              <input
                type="color"
                value={selectedColor}
                onChange={(e) => onColorChange(e.target.value)}
              />
              <div className="predefined-colors">
                {PREDEFINED_COLORS.map((color) => (
                  <div
                    key={color}
                    className="color-swatch"
                    style={{ backgroundColor: color }}
                    onClick={() => {
                      onColorChange(color);
                      setShowColorPicker(false);
                    }}
                    title={color}
                  />
                ))}
              </div>
              <button onClick={() => setShowColorPicker(false)}>Закрыть</button>
            </div>
          )}
        </div>
      </div>

      <div className="toolbar-section">
        <h4>Связи</h4>
        <button
          className={`mode-button ${relationMode ? 'active' : ''}`}
          onClick={onRelationModeToggle}
          title={
            relationMode
              ? 'Выйти из режима создания связей'
              : 'Войти в режим создания связей'
          }
        >
          {relationMode ? '🔗 Режим связей (вкл)' : '🔗 Режим связей'}
        </button>
        <button
          className={`mode-button ${showRelations ? 'active' : ''}`}
          onClick={onShowRelationsToggle}
          title={showRelations ? 'Скрыть связи' : 'Показать связи'}
        >
          {showRelations ? '👁 Показать связи (вкл)' : '👁 Показать связи'}
        </button>
      </div>

      {(hasPendingSelection ? selectedTypes.length > 0 : selectedType) && (
        <div className="toolbar-section selected-info">
          <h4>Выбрано</h4>
          <div className="selected-type-info">
            {hasPendingSelection ? (
              selectedTypes.map((type) => (
                <div
                  key={type}
                  className="selected-type-badge"
                  style={{ backgroundColor: getDefaultColor(type) }}
                >
                  {type}
                </div>
              ))
            ) : (
              <div
                className="selected-type-badge"
                style={{ backgroundColor: selectedColor }}
              >
                {selectedType}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Предопределенные цвета для быстрого выбора
const PREDEFINED_COLORS = [
  '#ffeb3b',
  '#ff9800',
  '#4caf50',
  '#2196f3',
  '#9c27b0',
  '#f44336',
  '#e91e63',
  '#00bcd4',
  '#8bc34a',
  '#cddc39',
  '#ffc107',
  '#ff5722',
  '#795548',
  '#9e9e9e',
  '#607d8b',
  '#673ab7',
  '#3f51b5',
  '#03a9f4',
  '#009688',
];

export default AnnotationToolbar;
