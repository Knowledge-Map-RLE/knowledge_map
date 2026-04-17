import React, { useState } from 'react';
import { ANNOTATION_CATEGORIES, getDefaultColor } from './annotationTypes';
import './AnnotationToolbar.css';

interface AnnotationToolbarProps {
  selectedType: string | null;
  onTypeSelect: (type: string) => void;
  onColorChange: (color: string) => void;
  selectedTypes?: string[];
  onTypeToggle?: (type: string) => void;
  hasPendingSelection?: boolean;
}

const AnnotationToolbar: React.FC<AnnotationToolbarProps> = ({
  selectedType,
  onTypeSelect,
  onColorChange,
  selectedTypes = [],
  onTypeToggle,
  hasPendingSelection = false,
}) => {
  const [filterText, setFilterText] = useState<string>('');

  const handleTypeClick = (type: string) => {
    if (hasPendingSelection && onTypeToggle) {
      onTypeToggle(type);
    } else {
      onTypeSelect(type);
      const defaultColor = getDefaultColor(type);
      onColorChange(defaultColor);
    }
  };

  const lowerFilter = filterText.toLowerCase();

  return (
    <div className="annotation-toolbar">
      <div className="toolbar-section">
        <input
          type="text"
          className="type-search-input"
          placeholder="Поиск аннотации..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
        />
        {Object.entries(ANNOTATION_CATEGORIES).map(([category, types]) => {
          const filteredTypes = lowerFilter
            ? types.filter((t) => t.toLowerCase().includes(lowerFilter))
            : types;
          if (filteredTypes.length === 0) return null;
          return (
            <div key={category} className="annotation-category">
              <div className="category-label">{category}</div>
              <div className="category-types">
                {filteredTypes.map((type, idx) => {
                  const isSelected = hasPendingSelection
                    ? selectedTypes.includes(type)
                    : selectedType === type;
                  return (
                    <button
                      key={`${category}-${type}-${idx}`}
                      className={`type-button ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleTypeClick(type)}
                      style={{
                        backgroundColor: isSelected ? getDefaultColor(type) : '#f5f5f5',
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
            </div>
          );
        })}
      </div>

      {(hasPendingSelection ? selectedTypes.length > 0 : selectedType) && (
        <div className="toolbar-section selected-info">
          <h4>Выбрано</h4>
          <div className="selected-type-info">
            {hasPendingSelection ? (
              // Убираем дубликаты из selectedTypes перед рендером
              [...new Set(selectedTypes)].map((type, idx) => (
                <div
                  key={`selected-${type}-${idx}`}
                  className="selected-type-badge"
                  style={{ backgroundColor: getDefaultColor(type) }}
                >
                  {type}
                </div>
              ))
            ) : (
              <div
                className="selected-type-badge"
                style={{ backgroundColor: getDefaultColor(selectedType!) }}
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
