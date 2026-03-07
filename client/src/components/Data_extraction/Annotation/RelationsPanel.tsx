import React, { useState, useRef, useMemo } from 'react';
import { Annotation, AnnotationRelation, deleteAnnotationRelation } from '../../../services/api';
import './RelationsPanel.css';

interface RelationsPanelProps {
  relations: AnnotationRelation[];
  annotations: Annotation[];
  onRelationDelete: (sourceId: string, targetId: string) => void;
  onRelationEdit: (relation: AnnotationRelation) => void;
  onAnnotationHighlight?: (annotationId: string | null) => void;
}

const RelationsPanel: React.FC<RelationsPanelProps> = ({
  relations,
  annotations,
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

  // Найти аннотацию по ID
  const getAnnotation = (uid: string) => {
    return annotations.find((ann) => ann.uid === uid);
  };

  const handleDelete = async (sourceId: string, targetId: string) => {
    if (window.confirm('Удалить эту связь?')) {
      onRelationDelete(sourceId, targetId);
    }
  };

  // Виртуализация: показываем только видимые элементы
  const ITEM_HEIGHT = 180; // Примерная высота одного элемента связи
  const CONTAINER_HEIGHT = 600; // Высота контейнера
  const OVERSCAN = 3; // Количество дополнительных элементов

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
              {visibleItems.map((relation) => {
                const sourceAnn = getAnnotation(relation.source_uid);
                const targetAnn = getAnnotation(relation.target_uid);

                if (!sourceAnn || !targetAnn) return null;

                return (
                  <div
                    key={relation.relation_uid}
                    className={`relation-item ${hoveredRelation === relation.relation_uid ? 'hovered' : ''}`}
                    style={{ minHeight: ITEM_HEIGHT }}
                    onMouseEnter={() => {
                      setHoveredRelation(relation.relation_uid);
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
                          <span className="annotation-type">{sourceAnn.annotation_type}</span>
                          <span className="annotation-text">"{sourceAnn.text}"</span>
                        </div>
                      </div>

                      <div className="relation-arrow">→</div>

                      <div className="annotation-box target-box">
                        <div className="annotation-label">Цель</div>
                        <div className="annotation-details">
                          <span className="annotation-type">{targetAnn.annotation_type}</span>
                          <span className="annotation-text">"{targetAnn.text}"</span>
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
