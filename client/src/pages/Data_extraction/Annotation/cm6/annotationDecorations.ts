/**
 * CM6 ViewPlugin: строит декорации ТОЛЬКО для видимого viewport.
 * Поддерживает перекрывающиеся аннотации через RangeSet.of() с sort:true.
 * Используется как fallback когда CSS Custom Highlight API недоступен.
 */
import { ViewPlugin, Decoration } from '@codemirror/view';
import type { DecorationSet } from '@codemirror/view';
import { RangeSet } from '@codemirror/state';
import type { ViewUpdate, EditorView } from '@codemirror/view';
import { annotationField, queryAnnotationsInRange } from './annotationStateField';
import type { AnnotationWithPos } from './annotationStateField';

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '');
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function buildDecorations(view: EditorView): DecorationSet {
  const annotations = view.state.field(annotationField);
  if (annotations.length === 0) return Decoration.none;

  const docLength = view.state.doc.length;

  // Собираем все аннотации во всех видимых диапазонах
  const visible: AnnotationWithPos[] = [];
  const seen = new Set<string>();

  for (const { from, to } of view.visibleRanges) {
    for (const ann of queryAnnotationsInRange(annotations, from, to)) {
      if (!seen.has(ann.uid)) {
        seen.add(ann.uid);
        visible.push(ann);
      }
    }
  }

  if (visible.length === 0) return Decoration.none;

  // Строим массив Range-значений для RangeSet.of()
  // RangeSet.of() с sort:true сам сортирует и поддерживает перекрытия
  const ranges: { from: number; to: number; value: Decoration }[] = [];

  for (const ann of visible) {
    const from = Math.max(0, ann.start);
    const to   = Math.min(docLength, ann.end);
    if (from >= to) continue;

    const { r, g, b } = hexToRgb(ann.color || '#ffeb3b');
    ranges.push({
      from,
      to,
      value: Decoration.mark({
        attributes: {
          'data-annotation-id': ann.uid,
          'data-ann': ann.uid,
          style: `background-color:rgba(${r},${g},${b},0.35);border-radius:2px;cursor:pointer;`,
          title: `${ann.annotation_type}: "${ann.text}"`,
        },
      }),
    });
  }

  if (ranges.length === 0) return Decoration.none;

  // sort:true — CM6 сам сортирует и корректно обрабатывает перекрытия
  return RangeSet.of(
    ranges.map(({ from, to, value }) => value.range(from, to)),
    true // sort
  );
}

export const annotationDecorationsPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildDecorations(view);
    }

    update(update: ViewUpdate) {
      if (
        update.docChanged ||
        update.viewportChanged ||
        update.state.field(annotationField) !== update.startState.field(annotationField)
      ) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: v => v.decorations }
);
