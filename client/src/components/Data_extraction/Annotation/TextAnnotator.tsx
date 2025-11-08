import React, { useState, useEffect, useRef, useMemo, useCallback, forwardRef, memo } from 'react';
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
  onTextChange?: (text: string) => void;
}

interface AnnotatedSegment {
  text: string;
  start: number;
  end: number;
  annotations: Annotation[];
}

// Утилита для преобразования hex в rgba
const hexToRgba = (hex: string, alpha: number): string => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

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
  onTextChange,
}, forwardedRef) => {
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [hoveredAnnotation, setHoveredAnnotation] = useState<Annotation | null>(null);
  const [relationSourceId, setRelationSourceId] = useState<string | null>(null);
  const containerRef = (forwardedRef as React.RefObject<HTMLDivElement>) || useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  // Локальное состояние текста для предотвращения потери фокуса
  const [localText, setLocalText] = useState(text);
  const cursorPositionRef = useRef<number | null>(null);
  const scrollPositionRef = useRef<number | null>(null);
  const windowScrollPositionRef = useRef<{ x: number; y: number } | null>(null);
  const isUpdatingRef = useRef(false);

  // Состояние для отслеживания выбранных индексов в перекрывающихся аннотациях
  // Ключ - это "start-end", значение - индекс в массиве аннотаций сегмента
  const [segmentSelectedIndex, setSegmentSelectedIndex] = useState<Record<string, number>>({});

  // Ограничиваем количество одновременно рендерящихся сегментов для производительности
  const MAX_RENDERED_SEGMENTS = 5000;

  // Синхронизация внешнего text с локальным состоянием
  // Обновляем только когда элемент не в фокусе, чтобы не нарушать редактирование
  useEffect(() => {
    if (!isUpdatingRef.current && text !== localText) {
      const hasFocus = textRef.current && document.activeElement === textRef.current;
      if (!hasFocus) {
        setLocalText(text);
      }
    }
  }, [text, localText]);

  // Восстановление позиции курсора и прокрутки после обновления
  useEffect(() => {
    if (editable && (cursorPositionRef.current !== null || scrollPositionRef.current !== null || windowScrollPositionRef.current !== null) && textRef.current) {
      const restore = () => {
        try {
          // Восстановление прокрутки окна
          if (windowScrollPositionRef.current !== null) {
            window.scrollTo(windowScrollPositionRef.current.x, windowScrollPositionRef.current.y);
            windowScrollPositionRef.current = null;
          }

          // Восстановление прокрутки в контейнере (где overflow: auto)
          if (scrollPositionRef.current !== null && containerRef.current) {
            containerRef.current.scrollTop = scrollPositionRef.current;
            scrollPositionRef.current = null;
          }

          // Восстановление курсора
          if (cursorPositionRef.current !== null) {
            const selection = window.getSelection();
            if (!selection || !textRef.current) return;

            const targetPosition = cursorPositionRef.current!;
            let currentPosition = 0;
            let targetNode: Node | null = null;
            let targetOffset = 0;

            // Рекурсивная функция для поиска позиции курсора в дереве DOM
            const findNodeAtPosition = (node: Node): boolean => {
              if (node.nodeType === Node.TEXT_NODE) {
                const textLength = node.textContent?.length || 0;
                if (currentPosition + textLength >= targetPosition) {
                  targetNode = node;
                  targetOffset = targetPosition - currentPosition;
                  return true;
                }
                currentPosition += textLength;
              } else if (node.nodeType === Node.ELEMENT_NODE) {
                for (let i = 0; i < node.childNodes.length; i++) {
                  if (findNodeAtPosition(node.childNodes[i])) {
                    return true;
                  }
                }
              }
              return false;
            };

            findNodeAtPosition(textRef.current);

            if (targetNode) {
              const range = document.createRange();
              range.setStart(targetNode, Math.min(targetOffset, targetNode.textContent?.length || 0));
              range.collapse(true);
              selection.removeAllRanges();
              selection.addRange(range);
            }

            cursorPositionRef.current = null;
          }
        } catch (e) {
          // Игнорируем ошибки восстановления курсора
          cursorPositionRef.current = null;
          scrollPositionRef.current = null;
          windowScrollPositionRef.current = null;
        }
      };

      // Небольшая задержка для завершения рендера
      requestAnimationFrame(restore);
    }
  }, [localText, editable]);

  // Разбить текст на сегменты с учетом аннотаций
  const segments = useMemo(() => {
    if (!localText || annotations.length === 0) {
      return [{ text: localText, start: 0, end: localText.length, annotations: [] }];
    }

    // Создаем список всех границ (начало и конец аннотаций)
    const boundaries = new Set<number>([0, localText.length]);
    annotations.forEach(ann => {
      boundaries.add(ann.start_offset);
      boundaries.add(ann.end_offset);
    });

    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);
    const result: AnnotatedSegment[] = [];

    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
      const start = sortedBoundaries[i];
      const end = sortedBoundaries[i + 1];
      const segmentText = localText.substring(start, end);

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

    // Ограничиваем количество сегментов для производительности
    if (result.length > MAX_RENDERED_SEGMENTS) {
      console.warn(`Слишком много сегментов (${result.length}), ограничиваем до ${MAX_RENDERED_SEGMENTS}`);
      return result.slice(0, MAX_RENDERED_SEGMENTS);
    }

    return result;
  }, [localText, annotations, MAX_RENDERED_SEGMENTS]);

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

  // Обработка наведения на аннотацию без debounce для быстрой реакции UI
  const handleAnnotationHover = useCallback((annotation: Annotation | null) => {
    setHoveredAnnotation(annotation);
    onAnnotationHover(annotation);
  }, [onAnnotationHover]);

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

  // Мемоизированный рендер сегмента текста
  const renderSegment = useCallback((segment: AnnotatedSegment, index: number) => {
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

    const style: React.CSSProperties = {
      backgroundColor: hexToRgba(selectedAnnotation.color, 0.2),
      cursor: relationMode ? 'crosshair' : 'pointer',
      padding: '2px 0',
      borderRadius: '2px',
      position: 'relative',
      border: isHovered ? '1px solid #000' : '1px solid transparent',
      outline: isRelationSource ? '2px solid #2196f3' : undefined,
      boxShadow: hasMultipleAnnotations ? '0 0 0 1px rgba(0,0,0,0.2)' : undefined,
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
  }, [segmentSelectedIndex, hoveredAnnotation, relationSourceId, relationMode]);

  return (
    <div
      ref={containerRef}
      className={`text-annotator ${relationMode ? 'relation-mode' : ''}`}
      style={{ position: 'relative' }}
    >
      <div style={{ position: 'relative' }}>
        <div
          ref={textRef}
          className="annotated-text"
          contentEditable={editable}
          suppressContentEditableWarning
          onInput={(e) => {
            if (editable && onTextChange) {
              // Сохраняем позицию прокрутки окна
              windowScrollPositionRef.current = {
                x: window.scrollX || window.pageXOffset,
                y: window.scrollY || window.pageYOffset
              };

              // Сохраняем позицию прокрутки из контейнера (где overflow: auto)
              if (containerRef.current) {
                scrollPositionRef.current = containerRef.current.scrollTop;
              }

              // Сохраняем позицию курсора
              const selection = window.getSelection();
              if (selection && selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const preCaretRange = range.cloneRange();
                preCaretRange.selectNodeContents(e.currentTarget);
                preCaretRange.setEnd(range.endContainer, range.endOffset);
                cursorPositionRef.current = preCaretRange.toString().length;
              }

              const newText = e.currentTarget.textContent || '';
              isUpdatingRef.current = true;
              setLocalText(newText);
              onTextChange(newText);

              // Сбрасываем флаг после небольшой задержки
              setTimeout(() => {
                isUpdatingRef.current = false;
              }, 50);
            }
          }}
          style={{
            whiteSpace: 'pre-wrap',
            lineHeight: '1.8',
            fontSize: '14px',
            fontFamily: 'monospace',
            padding: '10px',
            userSelect: relationMode ? 'none' : 'text',
            willChange: 'contents', // Оптимизация для браузера
            outline: editable ? '1px solid #ccc' : 'none',
            backgroundColor: editable ? '#fafafa' : 'transparent',
          }}
        >
          {segments.map((segment, index) => (
            <React.Fragment key={`seg-${segment.start}-${segment.end}-${index}`}>
              {renderSegment(segment, index)}
            </React.Fragment>
          ))}
        </div>

        {showRelations && (
          <RelationsOverlay
            annotation={hoveredAnnotation}
            relations={relations}
            annotations={annotations}
            containerRef={textRef}
          />
        )}
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
    </div>
  );
});

TextAnnotator.displayName = 'TextAnnotator';

// Компонент для отдельной связи (без memo для гарантированного обновления)
const RelationLine: React.FC<{
  relation: AnnotationRelation;
  isHighlighted: boolean;
  containerRef: React.RefObject<HTMLDivElement>;
  annotationsVersion: number; // Добавляем версию для принудительного обновления
}> = ({ relation, isHighlighted, containerRef, annotationsVersion }) => {
  const [, forceUpdate] = useState({});
  const sourceId = relation.source_uid;
  const targetId = relation.target_uid;

  // Принудительно обновляем компонент после монтирования для поиска элементов
  useEffect(() => {
    // Небольшая задержка чтобы дать React время отрендерить DOM
    const timer = setTimeout(() => forceUpdate({}), 10);
    return () => clearTimeout(timer);
  }, [annotationsVersion]);

  const sourceElement = containerRef.current?.querySelector(
    `[data-annotation-id="${sourceId}"]`
  ) as HTMLElement;

  const targetElement = containerRef.current?.querySelector(
    `[data-annotation-id="${targetId}"]`
  ) as HTMLElement;

  if (!sourceElement || !targetElement || !containerRef.current) {
    return null;
  }

  const sourceRect = sourceElement.getBoundingClientRect();
  const targetRect = targetElement.getBoundingClientRect();
  const containerRect = containerRef.current.getBoundingClientRect();

  // Стрелка всегда идёт от source к target - используем относительные координаты
  const x1 = sourceRect.left + sourceRect.width / 2 - containerRect.left;
  const y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
  const x2 = targetRect.left + targetRect.width / 2 - containerRect.left;
  const y2 = targetRect.top + targetRect.height / 2 - containerRect.top;

  // Проверка корректности координат
  if (isNaN(x1) || isNaN(y1) || isNaN(x2) || isNaN(y2)) {
    return null;
  }

  // Кривая Безье для красивой связи
  const cx1 = x1;
  const cy1 = y1 + (y2 - y1) / 3;
  const cx2 = x2;
  const cy2 = y2 - (y2 - y1) / 3;

  // Выделяем связи при наведении более ярким цветом и толще
  const strokeColor = isHighlighted ? '#ff5722' : '#2196f3';
  const strokeWidth = isHighlighted ? 3 : 2;
  const opacity = isHighlighted ? 0.9 : 0.4;
  const markerEnd = isHighlighted ? 'url(#arrowhead-highlighted)' : 'url(#arrowhead)';

  return (
    <g>
      <path
        d={`M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill="none"
        opacity={opacity}
        markerEnd={markerEnd}
      />
      <text
        x={(x1 + x2) / 2}
        y={(y1 + y2) / 2 - 10}
        fill={strokeColor}
        fontSize="11px"
        fontWeight="bold"
        textAnchor="middle"
        opacity={opacity}
        style={{ pointerEvents: 'none' }}
      >
        {relation.relation_type}
      </text>
    </g>
  );
};

RelationLine.displayName = 'RelationLine';

// Мемоизированный компонент для отображения связей при наведении или всех связей
const RelationsOverlay: React.FC<{
  annotation: Annotation | null;
  relations: AnnotationRelation[];
  annotations: Annotation[];
  containerRef: React.RefObject<HTMLDivElement>;
}> = memo(({ annotation, relations, annotations, containerRef }) => {
  // Версия аннотаций для принудительного обновления (основана на длине массива)
  const annotationsVersion = annotations.length;

  // Максимальное количество связей для рендеринга (для производительности)
  const MAX_RELATIONS = 1000;

  // Если аннотация указана - показываем только её связи
  // Иначе показываем все связи для видимых аннотаций
  const relevantRelations = useMemo(() => {
    let filtered: AnnotationRelation[];

    if (annotation) {
      // При наведении - только связи для этой аннотации
      filtered = relations.filter(
        rel => rel.source_uid === annotation.uid || rel.target_uid === annotation.uid
      );
    } else {
      // При показе всех связей - только для загруженных аннотаций
      const annotationIds = new Set(annotations.map(a => a.uid));
      filtered = relations.filter(
        rel => annotationIds.has(rel.source_uid) && annotationIds.has(rel.target_uid)
      );
    }

    // Ограничиваем количество связей для производительности
    if (filtered.length > MAX_RELATIONS) {
      console.warn(`Слишком много связей (${filtered.length}), показываем только ${MAX_RELATIONS}`);
      return filtered.slice(0, MAX_RELATIONS);
    }

    return filtered;
  }, [annotation, relations, annotations]);

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
        transform: 'translateZ(0)', // GPU-ускорение
        willChange: 'transform', // Подсказка браузеру для оптимизации
      }}
    >
      {relevantRelations.map((relation) => {
        const isHighlighted = annotation && (
          relation.source_uid === annotation.uid ||
          relation.target_uid === annotation.uid
        );

        return (
          <RelationLine
            key={`${relation.source_uid}-${relation.target_uid}`}
            relation={relation}
            isHighlighted={!!isHighlighted}
            containerRef={containerRef}
            annotationsVersion={annotationsVersion}
          />
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
          <polygon points="0 0, 10 3, 0 6" fill="#2196f3" opacity="0.4" />
        </marker>
        <marker
          id="arrowhead-highlighted"
          markerWidth="10"
          markerHeight="10"
          refX="9"
          refY="3"
          orient="auto"
        >
          <polygon points="0 0, 10 3, 0 6" fill="#ff5722" opacity="0.9" />
        </marker>
      </defs>
    </svg>
  );
});

RelationsOverlay.displayName = 'RelationsOverlay';

export default TextAnnotator;
