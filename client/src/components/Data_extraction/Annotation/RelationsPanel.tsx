import React, { useState, useRef, useMemo } from 'react';
import { AnnotationRelation } from '../../../services/api';
import './RelationsPanel.css';

interface RelationsPanelProps {
  relations: AnnotationRelation[];
  onRelationDelete: (sourceId: string, targetId: string) => void;
  onRelationEdit: (relation: AnnotationRelation) => void;
  onAnnotationHighlight?: (annotationId: string | null) => void;
}

const RelationsPanel: React.FC<RelationsPanelProps> = ({
  relations,
  onRelationDelete,
  onRelationEdit,
  onAnnotationHighlight,
}) => {
  const [filterType, setFilterType] = useState<string>('');
  const [hoveredRelation, setHoveredRelation] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // Получить уникальные типы связей
  const uniqueTypes = Array.from(new Set(relations.map((rel) => rel.relation_type))).sort();

  // Фильтрация связей
  const filteredRelations = relations.filter((rel) => {
    return !filterType || rel.relation_type === filterType;
  });

  const handleDelete = async (sourceId: string, targetId: string) => {
    if (window.confirm('Удалить эту связь?')) {
      onRelationDelete(sourceId, targetId);
    }
  };

  // Виртуализация: показываем только видимые элементы
  const ITEM_HEIGHT = 180; // Примерная высота одного элемента связи
  const CONTAINER_HEIGHT = 600; // Высота контейнера
  const OVERSCAN = 5; // Количество дополнительных элементов

  const visibleRange = useMemo(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - OVERSCAN);
    const endIndex = Math.min(
      filteredRelations.length,
      Math.ceil((scrollTop + CONTAINER_HEIGHT) / ITEM_HEIGHT) + OVERSCAN
    );
    return { startIndex, endIndex };
  }, [scrollTop, filteredRelations.length]);

  const visibleItems = useMemo(() => {
    return filteredRelations.slice(visibleRange.startIndex, visibleRange.endIndex);
  }, [filteredRelations, visibleRange]);

  const totalHeight = filteredRelations.length * ITEM_HEIGHT;
  const offsetY = visibleRange.startIndex * ITEM_HEIGHT;

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  };

  return (
    <div className="relations-panel">
      <div className="panel-filters">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="filter-select"
        >
          <option value="">Все типы связей</option>
          {uniqueTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div className="relations-list" ref={listRef} onScroll={handleScroll}>
        {filteredRelations.length === 0 ? (
          <div className="empty-state">
            <p>Нет связей</p>
            <small>Используйте режим связей для создания</small>
          </div>
        ) : (
          <div style={{ height: totalHeight, position: 'relative' }}>
            <div style={{ transform: `translateY(${offsetY}px)` }}>
              {visibleItems.map((relation, idx) => {
                const itemKey = relation.relation_uid || `${relation.source_uid}-${relation.target_uid}-${idx}`;
                return (
                  <div
                    key={itemKey}
                    className={`relation-item ${hoveredRelation === itemKey ? 'hovered' : ''}`}
                    style={{ minHeight: ITEM_HEIGHT }}
                    onMouseEnter={() => {
                      setHoveredRelation(itemKey);
                      if (onAnnotationHighlight) {
                        onAnnotationHighlight(relation.source_uid);
                      }
                    }}
                    onMouseLeave={() => {
                      setHoveredRelation(null);
                      if (onAnnotationHighlight) {
                        onAnnotationHighlight(null);
                      }
                    }}
                  >
                    <div className="relation-header">
                      <span className="relation-type-badge">{relation.relation_type}</span>
                      <div className="relation-actions">
                        <button
                          className="action-btn edit-btn"
                          onClick={() => onRelationEdit(relation)}
                          title="Редактировать тип связи"
                        >
                          ✏️
                        </button>
                        <button
                          className="action-btn delete-btn"
                          onClick={() => handleDelete(relation.source_uid, relation.target_uid)}
                          title="Удалить связь"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>

                    <div className="relation-content">
                      <div className="annotation-box source-box">
                        <div className="annotation-label">Источник</div>
                        <div className="annotation-details">
                          <span className="annotation-type">{relation.source_annotation_type ?? relation.source_uid}</span>
                          <span className="annotation-text">"{relation.source_text ?? '—'}"</span>
                        </div>
                      </div>

                      <div className="relation-arrow">→</div>

                      <div className="annotation-box target-box">
                        <div className="annotation-label">Цель</div>
                        <div className="annotation-details">
                          <span className="annotation-type">{relation.target_annotation_type ?? relation.target_uid}</span>
                          <span className="annotation-text">"{relation.target_text ?? '—'}"</span>
                        </div>
                      </div>
                    </div>

                    {relation.created_date && (
                      <div className="relation-meta">
                        Создана: {new Date(relation.created_date).toLocaleString('ru-RU')}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RelationsPanel;
