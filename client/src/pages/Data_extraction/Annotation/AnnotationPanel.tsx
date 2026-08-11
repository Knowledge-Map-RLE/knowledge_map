import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Annotation } from '../../../services/api';
import './AnnotationPanel.css';

interface AnnotationPanelProps {
  annotations: Annotation[];
  onAnnotationSelect: (annotation: Annotation | Annotation[]) => void;
  onAnnotationDelete: (annotationId: string) => void;
  onAnnotationEdit: (annotation: Annotation) => void;
  selectedAnnotation: Annotation | null;
  onTypeToggleForFragment?: (fragmentKey: string, type: string) => void;
  cursorPosition?: number | null;
}

interface AnnotationGroup {
  key: string;
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
  cursorPosition,
}) => {
  const [filterType, setFilterType] = useState<string>('');
  const [searchText, setSearchText] = useState<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const uniqueTypes = useMemo(
    () => Array.from(new Set(annotations.map((ann) => ann.annotation_type))).sort(),
    [annotations]
  );

  // Фильтрация + группировка по фрагментам (мемоизировано)
  const groupedByFragment = useMemo((): AnnotationGroup[] => {
    const filtered = annotations.filter((ann) => {
      const matchesType = !filterType || ann.annotation_type === filterType;
      const matchesSearch =
        !searchText ||
        ann.text.toLowerCase().includes(searchText.toLowerCase()) ||
        ann.annotation_type.toLowerCase().includes(searchText.toLowerCase());
      return matchesType && matchesSearch;
    });

    const fragmentMap = new Map<string, AnnotationGroup>();
    for (const ann of filtered) {
      const key = `${ann.start_offset}-${ann.end_offset}`;
      if (!fragmentMap.has(key)) {
        fragmentMap.set(key, {
          key,
          text: ann.text,
          start_offset: ann.start_offset,
          end_offset: ann.end_offset,
          annotations: [],
        });
      }
      fragmentMap.get(key)!.annotations.push(ann);
    }

    return Array.from(fragmentMap.values()).sort((a, b) => a.start_offset - b.start_offset);
  }, [annotations, filterType, searchText]);

  // O(1) lookup uid → group index для скролла к выбранной аннотации
  const uidToGroupIndex = useMemo(() => {
    const map = new Map<string, number>();
    for (let i = 0; i < groupedByFragment.length; i++) {
      for (const ann of groupedByFragment[i].annotations) {
        map.set(ann.uid, i);
      }
    }
    return map;
  }, [groupedByFragment]);

  // O(log n) lookup offset → group index через бинарный поиск
  const findGroupByOffset = useMemo((): ((offset: number) => number | null) => {
    if (groupedByFragment.length === 0) return () => null;
    const groups = groupedByFragment;
    return (offset: number) => {
      let lo = 0, hi = groups.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const g = groups[mid];
        if (offset >= g.start_offset && offset < g.end_offset) return mid;
        if (offset < g.start_offset) hi = mid - 1;
        else lo = mid + 1;
      }
      // Ближайшая группа перед курсором
      return hi >= 0 ? hi : 0;
    };
  }, [groupedByFragment]);

  // Виртуализация списка групп
  const rowVirtualizer = useVirtualizer({
    count: groupedByFragment.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 80,
    overscan: 5,
  });

  // Скролл к выбранной аннотации
  useEffect(() => {
    if (!selectedAnnotation) return;
    const idx = uidToGroupIndex.get(selectedAnnotation.uid);
    if (idx !== undefined) {
      rowVirtualizer.scrollToIndex(idx, { align: 'auto', behavior: 'smooth' });
    }
  }, [selectedAnnotation]); // eslint-disable-line react-hooks/exhaustive-deps

  // Авто-скролл к группе аннотации под курсором (с debounce 300мс)
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cursorPositionRef = useRef<number | null>(null);
  const findGroupByOffsetRef = useRef(findGroupByOffset);
  const groupedLengthRef = useRef(groupedByFragment.length);

  cursorPositionRef.current = cursorPosition;
  findGroupByOffsetRef.current = findGroupByOffset;
  groupedLengthRef.current = groupedByFragment.length;

  useEffect(() => {
    if (cursorPosition == null) return;

    // Debounce: ждём 300мс без изменений курсора перед скроллом
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => {
      const pos = cursorPositionRef.current;
      if (pos == null) return;
      const idx = findGroupByOffsetRef.current(pos);
      if (idx !== null && idx < groupedLengthRef.current) {
        rowVirtualizer.scrollToIndex(idx, { align: 'center', behavior: 'smooth' });
      }
    }, 300);

    return () => {
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, [cursorPosition]);

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

      <div className="annotations-list" ref={scrollRef}>
        {groupedByFragment.length === 0 ? (
          <div className="empty-state">
            <p>Нет аннотаций</p>
            <small>Выделите текст и выберите тип аннотации</small>
          </div>
        ) : (
          // Виртуальный контейнер — только видимые строки в DOM
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualItem) => {
              const group = groupedByFragment[virtualItem.index];
              const isSelected = selectedAnnotation != null &&
                uidToGroupIndex.get(selectedAnnotation.uid) === virtualItem.index;

              return (
                <div
                  key={group.key}
                  data-index={virtualItem.index}
                  ref={rowVirtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualItem.start}px)`,
                  }}
                >
                  <div
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
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default AnnotationPanel;
