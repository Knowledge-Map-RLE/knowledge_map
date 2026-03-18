import React, { useState, useRef, useEffect } from 'react';
import { Annotation } from '../../../services/api';
import './AnnotationPanel.css';

interface AnnotationPanelProps {
  annotations: Annotation[];
  onAnnotationSelect: (annotation: Annotation | Annotation[]) => void;
  onAnnotationDelete: (annotationId: string) => void;
  onAnnotationEdit: (annotation: Annotation) => void;
  selectedAnnotation: Annotation | null;
  onTypeToggleForFragment?: (fragmentKey: string, type: string) => void;
}

interface AnnotationGroup {
  text: string;
  start_offset: number;
  end_offset: number;
  annotations: Annotation[];
}

const AnnotationPanel: React.FC<AnnotationPanelProps> = ({
  annotations,
  onAnnotationSelect,
  onAnnotationDelete,
  onAnnotationEdit,
  selectedAnnotation,
  onTypeToggleForFragment,
}) => {
  const [filterType, setFilterType] = useState<string>('');
  const [searchText, setSearchText] = useState<string>('');
  const selectedRef = useRef<HTMLDivElement>(null);

  // Скролл к выбранному элементу
  useEffect(() => {
    if (selectedAnnotation && selectedRef.current) {
      selectedRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedAnnotation]);

  // Фильтрация
  const filteredAnnotations = annotations.filter((ann) => {
    const matchesType = !filterType || ann.annotation_type === filterType;
    const matchesSearch =
      !searchText ||
      ann.text.toLowerCase().includes(searchText.toLowerCase()) ||
      ann.annotation_type.toLowerCase().includes(searchText.toLowerCase());
    return matchesType && matchesSearch;
  });

  const uniqueTypes = Array.from(new Set(annotations.map((ann) => ann.annotation_type))).sort();

  // Группировка по фрагментам
  const fragmentGroups: Record<string, AnnotationGroup> = {};
  filteredAnnotations.forEach((ann) => {
    const key = `${ann.start_offset}-${ann.end_offset}`;
    if (!fragmentGroups[key]) {
      fragmentGroups[key] = {
        text: ann.text,
        start_offset: ann.start_offset,
        end_offset: ann.end_offset,
        annotations: [],
      };
    }
    fragmentGroups[key].annotations.push(ann);
  });

  const groupedByFragment = Object.entries(fragmentGroups).sort((a, b) =>
    a[1].start_offset - b[1].start_offset
  );

  return (
    <div className="annotation-panel">
      <div className="panel-filters">
        <input
          type="text"
          placeholder="Поиск по тексту..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="search-input"
        />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="filter-select"
        >
          <option value="">Все типы</option>
          {uniqueTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div className="annotations-list">
        {groupedByFragment.length === 0 ? (
          <div className="empty-state">
            <p>Нет аннотаций</p>
            <small>Выделите текст и выберите тип аннотации</small>
          </div>
        ) : (
          groupedByFragment.map(([fragmentKey, group]) => {
            const isSelected = group.annotations.some(
              (ann) => ann.uid === selectedAnnotation?.uid
            );
            return (
              <div
                key={fragmentKey}
                ref={isSelected ? selectedRef : null}
                className={`fragment-group ${isSelected ? 'selected' : ''}`}
                style={{ position: 'relative' }}
              >
                <button
                  className="delete-fragment-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm(`Удалить весь фрагмент с ${group.annotations.length} типами?`)) {
                      group.annotations.forEach((ann) => onAnnotationDelete(ann.uid));
                    }
                  }}
                  title="Удалить весь фрагмент"
                >
                  ×
                </button>
                <div className="fragment-header">
                  <div style={{ cursor: 'pointer' }} onClick={() => onAnnotationSelect(group.annotations)}>
                    <div className="fragment-text">"{group.text}"</div>
                    <div className="fragment-meta">
                      [{group.start_offset} - {group.end_offset}]
                    </div>
                  </div>
                </div>
                <div className="fragment-types">
                  {group.annotations.map((ann) => (
                    <div
                      key={ann.uid}
                      className="type-badge"
                      style={{ backgroundColor: ann.color }}
                      title={ann.annotation_type}
                    >
                      {ann.annotation_type}
                      <button
                        className="type-remove-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(`Удалить тип "${ann.annotation_type}"?`)) {
                            onAnnotationDelete(ann.uid);
                          }
                        }}
                        title="Удалить этот тип"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default AnnotationPanel;
