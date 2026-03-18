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
  largeLineHeight?: boolean;
  editable?: boolean;
  onTextChange?: (text: string) => void;
  selectedRelation?: AnnotationRelation | null;
  onRelationClick?: (relation: AnnotationRelation) => void;
  onRelationDelete?: (sourceId: string, targetId: string) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  forceTextVersion?: number;
}

// ── HTML-утилиты ──────────────────────────────────────────────────────────────

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const escapeAttr = (s: string) =>
  s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// ── Утилиты позиции курсора ───────────────────────────────────────────────────

const getCaretPosition = (el: HTMLElement): number => {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return 0;
  const range = sel.getRangeAt(0).cloneRange();
  range.selectNodeContents(el);
  range.setEnd(sel.getRangeAt(0).endContainer, sel.getRangeAt(0).endOffset);
  return range.toString().length;
};

const setCaretPosition = (el: HTMLElement, pos: number) => {
  const sel = window.getSelection();
  if (!sel) return;
  let currentPos = 0;
  let done = false;
  const walk = (node: Node) => {
    if (done) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const len = node.textContent?.length || 0;
      if (currentPos + len >= pos) {
        const range = document.createRange();
        range.setStart(node, pos - currentPos);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
        done = true;
      }
      currentPos += len;
    } else {
      node.childNodes.forEach(walk);
    }
  };
  walk(el);
};

// ── Построитель HTML с аннотациями ────────────────────────────────────────────

const buildAnnotatedHTML = (txt: string, anns: Annotation[], activeUids?: Set<string>): string => {
  if (!txt) return '';
  // Фильтруем аннотации с невалидными офсетами
  const validAnns = anns.filter(a =>
    a.start_offset >= 0 &&
    a.end_offset > a.start_offset &&
    a.end_offset <= txt.length &&
    txt.substring(a.start_offset, a.end_offset) === a.text
  );
  if (validAnns.length === 0) return escapeHtml(txt);

  const boundaries = new Set<number>([0, txt.length]);
  validAnns.forEach(a => {
    boundaries.add(a.start_offset);
    boundaries.add(a.end_offset);
  });
  const sorted = Array.from(boundaries).sort((a, b) => a - b);

  let html = '';
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i];
    const end = sorted[i + 1];
    const chunk = escapeHtml(txt.substring(start, end));
    const segAnns = validAnns.filter(a => a.start_offset <= start && a.end_offset >= end);
    if (segAnns.length === 0) {
      html += chunk;
    } else {
      // Активная (верхняя) аннотация — та чей uid в activeUids, иначе первая
      const activeAnn = (activeUids && segAnns.find(a => activeUids.has(a.uid))) ?? segAnns[0];
      const r = parseInt(activeAnn.color.slice(1, 3), 16);
      const g = parseInt(activeAnn.color.slice(3, 5), 16);
      const b = parseInt(activeAnn.color.slice(5, 7), 16);
      const title = segAnns.map(a => `${a.annotation_type}: "${a.text}"`).join('\n');
      const allUids = segAnns.map(a => a.uid).join(',');
      // Невидимые якоря для всех uid — чтобы RelationLine мог найти любую аннотацию в группе
      const anchors = segAnns.slice(1).map(a =>
        `<span data-annotation-id="${escapeAttr(a.uid)}" style="position:absolute;pointer-events:none;"></span>`
      ).join('');
      html += `<span data-ann="${escapeAttr(activeAnn.uid)}" data-anns="${escapeAttr(allUids)}" data-annotation-id="${escapeAttr(activeAnn.uid)}" style="background-color:rgba(${r},${g},${b},0.25);border-radius:2px;cursor:pointer;position:relative;" title="${escapeAttr(title)}">${chunk}${anchors}</span>`;
    }
  }
  return html;
};

// ── Основной компонент ────────────────────────────────────────────────────────

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
  largeLineHeight = false,
  editable = false,
  onTextChange,
  selectedRelation = null,
  onRelationClick,
  onRelationDelete,
  onUndo,
  onRedo,
  forceTextVersion,
}, forwardedRef) => {
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [hoveredAnnotation, setHoveredAnnotation] = useState<Annotation | null>(null);
  const [relationSourceId, setRelationSourceId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; relation: AnnotationRelation } | null>(null);
  // Активные uid для групп с наложением — ключ: "start-end", значение: uid верхней аннотации
  const [activeLayerUids, setActiveLayerUids] = useState<Record<string, string>>({});

  const containerRef = (forwardedRef as React.RefObject<HTMLDivElement>) || useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  // Локальный текст хранится в ref — без setState, чтобы не вызывать ре-рендер при вводе
  const localTextRef = useRef<string>(text);

  // Актуальные аннотации в ref — чтобы debounce и undo/redo всегда видели свежие данные
  const annotationsRef = useRef<Annotation[]>(annotations);
  annotationsRef.current = annotations;
  const activeLayerUidsRef = useRef<Record<string, string>>({});
  activeLayerUidsRef.current = activeLayerUids;

  // Актуальные колбэки в ref — capture-обработчик всегда видит свежие функции
  const onUndoRef = useRef(onUndo);
  onUndoRef.current = onUndo;
  const onRedoRef = useRef(onRedo);
  onRedoRef.current = onRedo;

  // Ref для таймера debounce
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── applyAnnotatedHTML ──────────────────────────────────────────────────────

  const applyAnnotatedHTML = useCallback((html: string) => {
    if (!textRef.current) return;
    const hasFocus = document.activeElement === textRef.current;
    const pos = hasFocus ? getCaretPosition(textRef.current) : null;
    textRef.current.innerHTML = html;
    if (hasFocus) {
      // innerHTML сбрасывает фокус — возвращаем его обратно
      textRef.current.focus();
      if (pos !== null) {
        setCaretPosition(textRef.current, pos);
      }
    }
  }, []);

  // ── scheduleAnnotationRefresh (debounce 800ms) ──────────────────────────────

  const scheduleAnnotationRefresh = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      applyAnnotatedHTML(buildAnnotatedHTML(localTextRef.current, annotationsRef.current, new Set(Object.values(activeLayerUidsRef.current))));
    }, 800);
  }, [applyAnnotatedHTML]);

  // ── useEffect: монтирование — рендерим начальный HTML ──────────────────────

  useEffect(() => {
    if (editable && textRef.current) {
      applyAnnotatedHTML(buildAnnotatedHTML(localTextRef.current, annotationsRef.current, new Set(Object.values(activeLayerUidsRef.current))));
    }
    // Только при монтировании
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable]);

  // ── useEffect: смена annotations снаружи — немедленно перерисовываем ───────

  useEffect(() => {
    if (editable && textRef.current) {
      applyAnnotatedHTML(buildAnnotatedHTML(localTextRef.current, annotationsRef.current, new Set(Object.values(activeLayerUidsRef.current))));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [annotations]); // annotations в deps — чтобы эффект срабатывал при их смене

  // ── useEffect: смена text снаружи (не в фокусе) ────────────────────────────

  useEffect(() => {
    const hasFocus = textRef.current && document.activeElement === textRef.current;
    if (!hasFocus) {
      localTextRef.current = text;
      if (editable && textRef.current) {
        applyAnnotatedHTML(buildAnnotatedHTML(text, annotationsRef.current, new Set(Object.values(activeLayerUidsRef.current))));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  // ── useEffect: forceTextVersion (undo/redo) — немедленно, без debounce ─────

  useEffect(() => {
    if (forceTextVersion !== undefined && forceTextVersion > 0) {
      localTextRef.current = text;
      if (textRef.current) {
        applyAnnotatedHTML(buildAnnotatedHTML(text, annotationsRef.current, new Set(Object.values(activeLayerUidsRef.current))));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceTextVersion]);

  // ── Обработка выделения текста ─────────────────────────────────────────────

  const handleMouseUp = useCallback((event: MouseEvent) => {
    if (!textRef.current || !textRef.current.contains(event.target as Node)) return;
    if (!editable || relationMode) return;

    setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !textRef.current) return;

      const range = sel.getRangeAt(0);
      if (!textRef.current.contains(range.commonAncestorContainer)) return;

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

  // ── Наведение на аннотацию ─────────────────────────────────────────────────

  const handleAnnotationHover = useCallback((annotation: Annotation | null) => {
    setHoveredAnnotation(annotation);
    onAnnotationHover(annotation);
  }, [onAnnotationHover]);

  // ── useEffect: глобальный mouseup ──────────────────────────────────────────

  useEffect(() => {
    if (!editable) return;
    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, [editable, handleMouseUp]);

  // ── useEffect: сброс режима связей ─────────────────────────────────────────

  useEffect(() => {
    if (!relationMode) setRelationSourceId(null);
  }, [relationMode]);

  // ── useEffect: перехват Ctrl+Z / Ctrl+Shift+Z на фазе capture ─────────────
  // Нужно capture=true, иначе браузер выполняет native undo в contentEditable
  // синхронно до React-обработчика

  useEffect(() => {
    if (!editable) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!textRef.current) return;
      // Проверяем что фокус на нашем div или внутри него
      const active = document.activeElement;
      if (active !== textRef.current && !textRef.current.contains(active)) return;
      if (e.ctrlKey && (e.code === 'KeyZ') && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        onUndoRef.current?.();
      } else if (e.ctrlKey && (e.code === 'KeyZ') && e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        onRedoRef.current?.();
      } else if (e.ctrlKey && e.code === 'KeyY') {
        e.preventDefault();
        e.stopPropagation();
        onRedoRef.current?.();
      }
    };
    document.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => document.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, [editable]);

  // ── useEffect: контекстное меню ────────────────────────────────────────────

  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    if (contextMenu) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [contextMenu]);

  // ── Для read-only режима: сегменты для рендера React children ──────────────

  const segments = useMemo(() => {
    if (!text || annotations.length === 0) {
      return [{ text, start: 0, end: text.length, annotations: [] as Annotation[] }];
    }
    const boundaries = new Set<number>([0, text.length]);
    annotations.forEach(ann => {
      boundaries.add(ann.start_offset);
      boundaries.add(ann.end_offset);
    });
    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);
    const result: { text: string; start: number; end: number; annotations: Annotation[] }[] = [];
    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
      const start = sortedBoundaries[i];
      const end = sortedBoundaries[i + 1];
      result.push({
        text: text.substring(start, end),
        start,
        end,
        annotations: annotations.filter(ann => ann.start_offset <= start && ann.end_offset >= end),
      });
    }
    // Объединяем соседние сегменты без аннотаций
    const optimized: typeof result = [];
    for (const seg of result) {
      if (seg.annotations.length === 0 && optimized.length > 0 && optimized[optimized.length - 1].annotations.length === 0) {
        const prev = optimized[optimized.length - 1];
        prev.text += seg.text;
        prev.end = seg.end;
      } else {
        optimized.push(seg);
      }
    }
    return optimized;
  }, [text, annotations]);

  // ── JSX ────────────────────────────────────────────────────────────────────

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
              const newText = e.currentTarget.textContent || '';
              localTextRef.current = newText;
              onTextChange(newText);
              scheduleAnnotationRefresh();
            }
          }}
          onClick={(e) => {
            if (!editable) return;
            const target = e.target as HTMLElement;
            const span = (target.dataset.ann ? target : target.closest('[data-ann]')) as HTMLElement | null;
            if (!span) return;
            const allUids = span.dataset.anns?.split(',').filter(Boolean) ?? [span.dataset.ann!];
            const allAnns = allUids.map(uid => annotationsRef.current.find(a => a.uid === uid)).filter(Boolean) as Annotation[];
            if (allAnns.length === 0) return;

            if (relationMode) {
              const primaryAnn = allAnns[0];
              if (!relationSourceId) {
                setRelationSourceId(primaryAnn.uid);
              } else if (relationSourceId !== primaryAnn.uid) {
                if (onRelationCreate) onRelationCreate(relationSourceId, primaryAnn.uid);
                setRelationSourceId(null);
              }
              return;
            }

            if (allAnns.length > 1) {
              // Циклически переключаем верхний слой
              const segKey = `${allAnns[0].start_offset}-${allAnns[0].end_offset}`;
              const currentUid = activeLayerUids[segKey] ?? allUids[0];
              const currentIdx = allUids.indexOf(currentUid);
              const nextUid = allUids[(currentIdx + 1) % allUids.length];
              const nextAnn = allAnns.find(a => a.uid === nextUid)!;
              setActiveLayerUids(prev => ({ ...prev, [segKey]: nextUid }));
              // Перерисовываем с новым активным слоем
              const newActiveUids = new Set(Object.values({ ...activeLayerUids, [segKey]: nextUid }));
              applyAnnotatedHTML(buildAnnotatedHTML(localTextRef.current, annotationsRef.current, newActiveUids));
              onAnnotationClick(nextAnn);
            } else {
              onAnnotationClick(allAnns[0]);
            }
          }}
          onMouseMove={(e) => {
            if (!editable) return;
            const target = e.target as HTMLElement;
            const annId = target.dataset.ann;
            if (annId) {
              const ann = annotations.find(a => a.uid === annId);
              if (ann && hoveredAnnotation?.uid !== ann.uid) {
                handleAnnotationHover(ann);
              }
            } else if (hoveredAnnotation !== null) {
              handleAnnotationHover(null);
            }
          }}
          onMouseLeave={() => {
            if (editable && hoveredAnnotation !== null) {
              handleAnnotationHover(null);
            }
          }}
          style={{
            whiteSpace: 'pre-wrap',
            lineHeight: largeLineHeight ? '50px' : '1.8',
            fontSize: '14px',
            fontFamily: 'monospace',
            padding: '10px',
            userSelect: relationMode ? 'none' : 'text',
            willChange: 'contents',
            outline: editable ? '1px solid #ccc' : 'none',
            backgroundColor: editable ? '#fafafa' : 'transparent',
          }}
        >
          {!editable && segments.map((segment) => {
            const segmentKey = `seg-${segment.start}-${segment.end}`;
            if (segment.annotations.length === 0) {
              return <span key={segmentKey}>{segment.text}</span>;
            }
            const ann = segment.annotations[0];
            const r = parseInt(ann.color.slice(1, 3), 16);
            const g = parseInt(ann.color.slice(3, 5), 16);
            const b = parseInt(ann.color.slice(5, 7), 16);
            const isHovered = hoveredAnnotation?.uid === ann.uid;
            const isRelationSource = relationSourceId === ann.uid;
            const title = segment.annotations
              .map(a => `${a.annotation_type} (${a.text})`)
              .join('\n');
            return (
              <span
                key={segmentKey}
                data-annotation-id={ann.uid}
                style={{
                  backgroundColor: `rgba(${r},${g},${b},0.2)`,
                  cursor: relationMode ? 'crosshair' : 'pointer',
                  padding: '2px 0',
                  borderRadius: '2px',
                  position: 'relative',
                  border: isHovered ? '1px solid #000' : '1px solid transparent',
                  outline: isRelationSource ? '2px solid #2196f3' : undefined,
                  boxShadow: segment.annotations.length > 1 ? '0 0 0 1px rgba(0,0,0,0.2)' : undefined,
                }}
                title={title}
                onClick={(e) => {
                  e.stopPropagation();
                  if (relationMode) {
                    if (!relationSourceId) {
                      setRelationSourceId(ann.uid);
                    } else if (relationSourceId !== ann.uid) {
                      if (onRelationCreate) onRelationCreate(relationSourceId, ann.uid);
                      setRelationSourceId(null);
                    }
                  } else {
                    onAnnotationClick(ann);
                  }
                }}
                onMouseEnter={() => handleAnnotationHover(ann)}
                onMouseLeave={() => handleAnnotationHover(null)}
              >
                {segment.text}
              </span>
            );
          })}
        </div>

        {showRelations && (
          <RelationsOverlay
            annotation={hoveredAnnotation}
            relations={relations}
            annotations={annotations}
            containerRef={textRef}
            selectedRelation={selectedRelation}
            onRelationClick={onRelationClick}
            onRelationContextMenu={(relation, x, y) => setContextMenu({ relation, x, y })}
          />
        )}

        {contextMenu && (
          <div
            style={{
              position: 'fixed',
              left: contextMenu.x,
              top: contextMenu.y,
              backgroundColor: 'white',
              border: '1px solid #ccc',
              borderRadius: '4px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
              zIndex: 10000,
              minWidth: '150px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#f44336',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#f5f5f5'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
              onClick={() => {
                if (onRelationDelete) {
                  onRelationDelete(contextMenu.relation.source_uid, contextMenu.relation.target_uid);
                }
                setContextMenu(null);
              }}
            >
              🗑️ Удалить связь
            </div>
          </div>
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

// ── RelationLine ──────────────────────────────────────────────────────────────

const RelationLine: React.FC<{
  relation: AnnotationRelation;
  isHighlighted: boolean;
  isSelected: boolean;
  containerRef: React.RefObject<HTMLDivElement>;
  annotationsVersion: number;
  onRelationClick?: (relation: AnnotationRelation) => void;
  onRelationContextMenu?: (relation: AnnotationRelation, x: number, y: number) => void;
}> = ({ relation, isHighlighted, isSelected, containerRef, annotationsVersion, onRelationClick, onRelationContextMenu }) => {
  const [, forceUpdate] = useState({});

  useEffect(() => {
    const timer = setTimeout(() => forceUpdate({}), 10);
    return () => clearTimeout(timer);
  }, [annotationsVersion]);

  const sourceElement = containerRef.current?.querySelector(
    `[data-annotation-id="${relation.source_uid}"]`
  ) as HTMLElement | null;

  const targetElement = containerRef.current?.querySelector(
    `[data-annotation-id="${relation.target_uid}"]`
  ) as HTMLElement | null;

  if (!sourceElement || !targetElement || !containerRef.current) return null;

  const sourceRect = sourceElement.getBoundingClientRect();
  const targetRect = targetElement.getBoundingClientRect();
  const containerRect = containerRef.current.getBoundingClientRect();

  const x1 = sourceRect.left + sourceRect.width / 2 - containerRect.left;
  const y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
  const x2 = targetRect.left + targetRect.width / 2 - containerRect.left;
  const y2 = targetRect.top + targetRect.height / 2 - containerRect.top;

  if (isNaN(x1) || isNaN(y1) || isNaN(x2) || isNaN(y2)) return null;

  const upOffset = 20;
  const point2_x = x1;
  const point2_y = y1 - upOffset;
  const point3_x = x2;
  const point3_y = y2 - upOffset;

  let strokeColor = '#2196f3';
  let strokeWidth = 2;
  let opacity = 0.4;

  if (isSelected) {
    strokeColor = '#4caf50';
    strokeWidth = 3;
    opacity = 1.0;
  } else if (isHighlighted) {
    strokeColor = '#ff5722';
    strokeWidth = 3;
    opacity = 0.9;
  }

  const markerEnd = isSelected ? 'url(#arrowhead-selected)' :
    isHighlighted ? 'url(#arrowhead-highlighted)' :
      'url(#arrowhead)';

  return (
    <g
      onClick={(e) => { e.stopPropagation(); onRelationClick?.(relation); }}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); onRelationContextMenu?.(relation, e.clientX, e.clientY); }}
      style={{ cursor: 'pointer' }}
    >
      <path
        d={`M ${x1} ${y1} L ${point2_x} ${point2_y} L ${point3_x} ${point3_y} L ${x2} ${y2}`}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        fill="none"
        opacity={opacity}
        markerEnd={markerEnd}
        style={{ pointerEvents: 'stroke' }}
      />
      <text
        x={(x1 + x2) / 2}
        y={point2_y - 5}
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

// ── RelationsOverlay ──────────────────────────────────────────────────────────

const RelationsOverlay: React.FC<{
  annotation: Annotation | null;
  relations: AnnotationRelation[];
  annotations: Annotation[];
  containerRef: React.RefObject<HTMLDivElement>;
  selectedRelation?: AnnotationRelation | null;
  onRelationClick?: (relation: AnnotationRelation) => void;
  onRelationContextMenu?: (relation: AnnotationRelation, x: number, y: number) => void;
}> = memo(({ annotation, relations, annotations, containerRef, selectedRelation, onRelationClick, onRelationContextMenu }) => {
  const annotationsVersion = annotations.length;
  const MAX_RELATIONS = 1000;

  const relevantRelations = useMemo(() => {
    let filtered: AnnotationRelation[];
    if (annotation) {
      filtered = relations.filter(
        rel => rel.source_uid === annotation.uid || rel.target_uid === annotation.uid
      );
    } else {
      const annotationIds = new Set(annotations.map(a => a.uid));
      filtered = relations.filter(
        rel => annotationIds.has(rel.source_uid) && annotationIds.has(rel.target_uid)
      );
    }
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
        transform: 'translateZ(0)',
        willChange: 'transform',
      }}
    >
      {relevantRelations.map((relation) => {
        const isHighlighted = !!annotation && (
          relation.source_uid === annotation.uid || relation.target_uid === annotation.uid
        );
        const isSelected = !!selectedRelation &&
          selectedRelation.source_uid === relation.source_uid &&
          selectedRelation.target_uid === relation.target_uid;
        return (
          <RelationLine
            key={`${relation.source_uid}-${relation.target_uid}`}
            relation={relation}
            isHighlighted={isHighlighted}
            isSelected={isSelected}
            containerRef={containerRef}
            annotationsVersion={annotationsVersion}
            onRelationClick={onRelationClick}
            onRelationContextMenu={onRelationContextMenu}
          />
        );
      })}
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#2196f3" opacity="0.4" />
        </marker>
        <marker id="arrowhead-highlighted" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#ff5722" opacity="0.9" />
        </marker>
        <marker id="arrowhead-selected" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="#4caf50" opacity="1.0" />
        </marker>
      </defs>
    </svg>
  );
});

RelationsOverlay.displayName = 'RelationsOverlay';

export default TextAnnotator;
