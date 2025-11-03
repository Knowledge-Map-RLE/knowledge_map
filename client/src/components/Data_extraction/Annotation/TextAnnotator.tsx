import React, { useState, useEffect, useRef, useMemo, useCallback, forwardRef } from 'react';
import { Annotation, AnnotationRelation } from '../../../services/api';
import './TextAnnotator.css';

interface TextAnnotatorProps {
  text: string;
  annotations: Annotation[];
  relations: AnnotationRelation[];
  selectedAnnotationType: string | null;
  selectedColor: string;
  onTextSelect: (start: number, end: number, selectedText: string) => void;
  onAnnotationClick: (annotation: Annotation) => void;
  onAnnotationHover: (annotation: Annotation | null) => void;
  relationMode: boolean;
  onRelationCreate?: (sourceId: string, targetId: string) => void;
  showRelations: boolean;
  editable?: boolean;
}

interface AnnotatedSegment {
  text: string;
  start: number;
  end: number;
  annotations: Annotation[];
}

const TextAnnotator = forwardRef<HTMLDivElement, TextAnnotatorProps>(({
  text,
  annotations,
  relations,
  selectedAnnotationType,
  selectedColor,
  onTextSelect,
  onAnnotationClick,
  onAnnotationHover,
  relationMode,
  onRelationCreate,
  showRelations,
  editable = false,
}, forwardedRef) => {
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [hoveredAnnotation, setHoveredAnnotation] = useState<Annotation | null>(null);
  const [relationSourceId, setRelationSourceId] = useState<string | null>(null);
  const containerRef = (forwardedRef as React.RefObject<HTMLDivElement>) || useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  // Состояние для отслеживания выбранных индексов в перекрывающихся аннотациях
  // Ключ - это "start-end", значение - индекс в массиве аннотаций сегмента
  const [segmentSelectedIndex, setSegmentSelectedIndex] = useState<Record<string, number>>({});

  // Разбить текст на сегменты с учетом аннотаций
  const segments = useMemo(() => {
    if (!text || annotations.length === 0) {
      return [{ text, start: 0, end: text.length, annotations: [] }];
    }

    // Создаем список всех границ (начало и конец аннотаций)
    const boundaries = new Set<number>([0, text.length]);
    annotations.forEach(ann => {
      boundaries.add(ann.start_offset);
      boundaries.add(ann.end_offset);
    });

    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);
    const result: AnnotatedSegment[] = [];

    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
      const start = sortedBoundaries[i];
      const end = sortedBoundaries[i + 1];
      const segmentText = text.substring(start, end);

      // Найти все аннотации, которые покрывают этот сегмент
      const segmentAnnotations = annotations.filter(
        ann => ann.start_offset <= start && ann.end_offset >= end
      );

      result.push({
        text: segmentText,
        start,
        end,
        annotations: segmentAnnotations,
      });
    }

    return result;
  }, [text, annotations]);

  // Обработка выделения текста
  const handleMouseUp = useCallback((event: MouseEvent) => {
    // Проверяем, что клик был внутри нашего компонента
    if (!textRef.current || !textRef.current.contains(event.target as Node)) {
      return;
    }

    if (!editable || relationMode) return;

    // Даём браузеру время завершить выделение
    setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !textRef.current) return;

      const range = sel.getRangeAt(0);

      // Проверяем, что выделение внутри нашего компонента
      if (!textRef.current.contains(range.commonAncestorContainer)) {
        return;
      }

      // Вычисляем офсеты относительно всего текста
      const preSelectionRange = range.cloneRange();
      preSelectionRange.selectNodeContents(textRef.current);
      preSelectionRange.setEnd(range.startContainer, range.startOffset);
      const start = preSelectionRange.toString().length;
      const selectedText = range.toString();
      const end = start + selectedText.length;

      if (start !== end && selectedText.trim().length > 0) {
        setSelection({ start, end });
        onTextSelect(start, end, selectedText);
      }
    }, 10);
  }, [editable, relationMode, onTextSelect]);

  // Обработка клика на аннотацию с поддержкой циклического переключения
  const handleAnnotationClick = (segment: AnnotatedSegment, event: React.MouseEvent) => {
    event.stopPropagation();

    const segmentKey = `${segment.start}-${segment.end}`;
    const currentIndex = segmentSelectedIndex[segmentKey] || 0;

    if (relationMode) {
      const selectedAnnotation = segment.annotations[currentIndex];
      // Режим создания связей
      if (!relationSourceId) {
        // Выбрать источник
        setRelationSourceId(selectedAnnotation.uid);
      } else if (relationSourceId !== selectedAnnotation.uid) {
        // Создать связь
        if (onRelationCreate) {
          onRelationCreate(relationSourceId, selectedAnnotation.uid);
        }
        setRelationSourceId(null);
      }
    } else {
      // Обычный режим - циклически переключаемся между аннотациями
      const nextIndex = (currentIndex + 1) % segment.annotations.length;
      setSegmentSelectedIndex({
        ...segmentSelectedIndex,
        [segmentKey]: nextIndex,
      });

      // Передаем выбранную аннотацию
      const selectedAnnotation = segment.annotations[nextIndex];
      onAnnotationClick(selectedAnnotation);
    }
  };

  // Обработка наведения на аннотацию
  const handleAnnotationHover = (annotation: Annotation | null) => {
    setHoveredAnnotation(annotation);
    onAnnotationHover(annotation);
  };

  // Сброс режима связей при изменении флага
  useEffect(() => {
    if (!relationMode) {
      setRelationSourceId(null);
    }
  }, [relationMode]);

  // Добавляем глобальный обработчик выделения текста
  useEffect(() => {
    if (!editable) return;

    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [editable, handleMouseUp]);

  // Рендер сегмента текста
  const renderSegment = (segment: AnnotatedSegment, index: number) => {
    if (segment.annotations.length === 0) {
      // Обычный текст без аннотаций
      return <span key={index}>{segment.text}</span>;
    }

    // Получаем текущий выбранный индекс для этого сегмента
    const segmentKey = `${segment.start}-${segment.end}`;
    const currentIndex = segmentSelectedIndex[segmentKey] || 0;
    const selectedAnnotation = segment.annotations[currentIndex];

    const isHovered = hoveredAnnotation?.uid === selectedAnnotation.uid;
    const isRelationSource = relationSourceId === selectedAnnotation.uid;
    const hasMultipleAnnotations = segment.annotations.length > 1;

    // Используем полупрозрачную подсветку (opacity 0.2 = 80% прозрачность)
    const hexToRgba = (hex: string, alpha: number) => {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    const style: React.CSSProperties = {
      backgroundColor: hexToRgba(selectedAnnotation.color, 0.2),
      cursor: relationMode ? 'crosshair' : 'pointer',
      padding: '2px 0',
      borderRadius: '2px',
      position: 'relative',
      border: isHovered ? '2px solid #000' : undefined,
      outline: isRelationSource ? '3px solid #2196f3' : undefined,
      boxShadow: hasMultipleAnnotations ? '0 0 0 2px rgba(0,0,0,0.2)' : undefined,
    };

    const title = segment.annotations
      .map((ann, idx) => `${idx === currentIndex ? '→ ' : '  '}${ann.annotation_type} (${ann.text})`)
      .join('\n');

    return (
      <span
        key={index}
        style={style}
        title={title}
        onClick={(e) => handleAnnotationClick(segment, e)}
        onMouseEnter={() => handleAnnotationHover(selectedAnnotation)}
        onMouseLeave={() => handleAnnotationHover(null)}
        data-annotation-id={selectedAnnotation.uid}
      >
        {segment.text}
      </span>
    );
  };

  return (
    <div
      ref={containerRef}
      className={`text-annotator ${relationMode ? 'relation-mode' : ''}`}
      style={{ position: 'relative' }}
    >
      <div
        ref={textRef}
        className="annotated-text"
        style={{
          whiteSpace: 'pre-wrap',
          lineHeight: '1.8',
          fontSize: '14px',
          fontFamily: 'monospace',
          padding: '10px',
          userSelect: relationMode ? 'none' : 'text',
        }}
      >
        {segments.map((segment, index) => renderSegment(segment, index))}
      </div>

      {relationMode && relationSourceId && (
        <div
          style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            background: '#2196f3',
            color: 'white',
            padding: '8px 12px',
            borderRadius: '4px',
            fontSize: '12px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
          }}
        >
          Выберите целевую аннотацию
        </div>
      )}

      {showRelations && hoveredAnnotation && (
        <RelationsOverlay
          annotation={hoveredAnnotation}
          relations={relations}
          annotations={annotations}
          containerRef={textRef}
        />
      )}
    </div>
  );
});

TextAnnotator.displayName = 'TextAnnotator';

// Компонент для отображения связей при наведении
const RelationsOverlay: React.FC<{
  annotation: Annotation;
  relations: AnnotationRelation[];
  annotations: Annotation[];
  containerRef: React.RefObject<HTMLDivElement>;
}> = ({ annotation, relations, annotations, containerRef }) => {
  // Найти все связи с текущей аннотацией
  const relevantRelations = relations.filter(
    rel => rel.source_uid === annotation.uid || rel.target_uid === annotation.uid
  );

  if (relevantRelations.length === 0) return null;

  return (
    <svg
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1000,
      }}
    >
      {relevantRelations.map((relation, index) => {
        // Определяем, является ли наведённая аннотация источником или целью
        const isSource = relation.source_uid === annotation.uid;
        const sourceId = relation.source_uid;
        const targetId = relation.target_uid;

        const sourceElement = containerRef.current?.querySelector(
          `[data-annotation-id="${sourceId}"]`
        ) as HTMLElement;

        const targetElement = containerRef.current?.querySelector(
          `[data-annotation-id="${targetId}"]`
        ) as HTMLElement;

        if (!sourceElement || !targetElement || !containerRef.current) return null;

        const sourceRect = sourceElement.getBoundingClientRect();
        const targetRect = targetElement.getBoundingClientRect();
        const containerRect = containerRef.current.getBoundingClientRect();

        // Стрелка всегда идёт от source к target
        const x1 = sourceRect.left + sourceRect.width / 2 - containerRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - containerRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - containerRect.top;

        // Кривая Безье для красивой связи
        const cx1 = x1;
        const cy1 = y1 + (y2 - y1) / 3;
        const cx2 = x2;
        const cy2 = y2 - (y2 - y1) / 3;

        return (
          <g key={`${relation.source_uid}-${relation.target_uid}-${index}`}>
            <path
              d={`M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`}
              stroke="#2196f3"
              strokeWidth="2"
              fill="none"
              opacity="0.6"
              markerEnd="url(#arrowhead)"
            />
            <text
              x={(x1 + x2) / 2}
              y={(y1 + y2) / 2 - 10}
              fill="#2196f3"
              fontSize="11px"
              fontWeight="bold"
              textAnchor="middle"
              style={{ pointerEvents: 'none' }}
            >
              {relation.relation_type}
            </text>
          </g>
        );
      })}
      <defs>
        <marker
          id="arrowhead"
          markerWidth="10"
          markerHeight="10"
          refX="9"
          refY="3"
          orient="auto"
        >
          <polygon points="0 0, 10 3, 0 6" fill="#2196f3" opacity="0.6" />
        </marker>
      </defs>
    </svg>
  );
};

export default TextAnnotator;
