/**
 * React-хук, инкапсулирующий жизненный цикл CodeMirror 6 EditorView.
 * Монтирует редактор в containerRef, уничтожает при unmount.
 * Пробрасывает события через колбэки: onTextChange, onTextSelect, onCursorMove.
 */
import { useEffect, useRef, useCallback } from 'react';
import { EditorView, keymap, ViewPlugin } from '@codemirror/view';
import { EditorState, Transaction, Compartment } from '@codemirror/state';
import { defaultKeymap } from '@codemirror/commands';
import {
  annotationField,
  setAnnotationsEffect,
  toAnnotationWithPos,
  replaceDocAnnotation,
} from './annotationStateField';
import { annotationDecorationsPlugin } from './annotationDecorations';
import {
  cssHighlightPlugin,
  CSS_HIGHLIGHT_SUPPORTED,
  injectAnnotationHighlightStyles,
} from './cssHighlightPlugin';
import type { Annotation } from '../../../../services/api';

interface UseCM6EditorParams {
  containerRef: React.RefObject<HTMLDivElement>;
  initialText: string;
  editable: boolean;
  onTextChange?: (text: string) => void;
  onTextSelect?: (start: number, end: number, text: string) => void;
  onCursorMove?: (pos: number) => void;
  largeLineHeight?: boolean;
}

interface UseCM6EditorResult {
  viewRef: React.RefObject<EditorView | null>;
  setAnnotations: (annotations: Annotation[]) => void;
  doUndo: () => void;
  doRedo: () => void;
  scrollToOffset: (offset: number) => void;
}

export function useCM6Editor({
  containerRef,
  initialText,
  editable,
  onTextChange,
  onTextSelect,
  onCursorMove,
  largeLineHeight = false,
}: UseCM6EditorParams): UseCM6EditorResult {
  const viewRef = useRef<EditorView | null>(null);
  const editableCompartment = useRef(new Compartment());

  // Стабильные рефы для колбэков
  const onTextChangeRef = useRef(onTextChange);
  onTextChangeRef.current = onTextChange;
  const onTextSelectRef = useRef(onTextSelect);
  onTextSelectRef.current = onTextSelect;
  const onCursorMoveRef = useRef(onCursorMove);
  onCursorMoveRef.current = onCursorMove;

  // Ref для текущего текста — чтобы при создании view взять самое свежее значение
  const initialTextRef = useRef(initialText);
  initialTextRef.current = initialText;

  // Очередь аннотаций, пришедших до создания view
  const pendingAnnotationsRef = useRef<Annotation[] | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const listenerPlugin = ViewPlugin.fromClass(
      class {
        update(update: import('@codemirror/view').ViewUpdate) {
          if (update.docChanged) {
            onTextChangeRef.current?.(update.state.doc.toString());
          }
          const sel = update.state.selection.main;
          if (!sel.empty && update.selectionSet) {
            const selectedText = update.state.sliceDoc(sel.from, sel.to);
            if (selectedText.trim().length > 0) {
              onTextSelectRef.current?.(sel.from, sel.to, selectedText);
            }
          }
          if (update.selectionSet && onCursorMoveRef.current) {
            onCursorMoveRef.current(sel.head);
          }
        }
      }
    );

    if (CSS_HIGHLIGHT_SUPPORTED) {
      injectAnnotationHighlightStyles();
    }

    const highlightPlugin = CSS_HIGHLIGHT_SUPPORTED
      ? cssHighlightPlugin
      : annotationDecorationsPlugin;

    // Используем самый свежий текст на момент создания view
    const state = EditorState.create({
      doc: initialTextRef.current,
      extensions: [
        keymap.of([...defaultKeymap]),
        annotationField,
        highlightPlugin,
        listenerPlugin,
        editableCompartment.current.of(EditorView.editable.of(editable)),
        EditorView.lineWrapping,
        EditorView.theme({
          '&': {
            fontSize: '14px',
            fontFamily: 'monospace',
            backgroundColor: editable ? '#fafafa' : 'transparent',
          },
          '.cm-content': {
            padding: '10px',
            whiteSpace: 'pre-wrap',
            lineHeight: largeLineHeight ? '50px' : '1.8',
          },
          '.cm-line': {
            padding: '0',
          },
          '.cm-editor': {
            outline: editable ? '1px solid #ccc' : 'none',
          },
          '&.cm-focused': {
            outline: 'none',
          },
        }),
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });

    viewRef.current = view;

    // Применяем аннотации, которые пришли до создания view
    if (pendingAnnotationsRef.current !== null) {
      view.dispatch({
        effects: setAnnotationsEffect.of(
          pendingAnnotationsRef.current.map(toAnnotationWithPos)
        ),
      });
      pendingAnnotationsRef.current = null;
    }

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Синхронизация текста при изменении пропса снаружи.
  useEffect(() => {
    if (!viewRef.current) return;
    const currentDoc = viewRef.current.state.doc;
    if (currentDoc.toString() !== initialText) {
      viewRef.current.dispatch({
        changes: { from: 0, to: currentDoc.length, insert: initialText },
        // Маркер: не трогать аннотации при замене текста снаружи
        annotations: [Transaction.addToHistory.of(false), replaceDocAnnotation.of(true)],
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialText]);

  // Синхронизация editable
  useEffect(() => {
    if (!viewRef.current) return;
    viewRef.current.dispatch({
      effects: editableCompartment.current.reconfigure(EditorView.editable.of(editable)),
    });
  }, [editable]);

  // eslint-disable-next-line @typescript-eslint/no-empty-function
  useEffect(() => {}, [largeLineHeight]);

  const setAnnotations = useCallback((annotations: Annotation[]) => {
    if (!viewRef.current) {
      // View ещё не создан — сохраняем в очереди
      pendingAnnotationsRef.current = annotations;
      return;
    }
    viewRef.current.dispatch({
      effects: setAnnotationsEffect.of(annotations.map(toAnnotationWithPos)),
    });
  }, []);

  const doUndo = useCallback(() => {}, []);
  const doRedo = useCallback(() => {}, []);

  const scrollToOffset = useCallback((offset: number) => {
    if (!viewRef.current) return;
    viewRef.current.dispatch({
      selection: { anchor: offset },
      scrollIntoView: true,
    });
  }, []);

  return { viewRef, setAnnotations, doUndo, doRedo, scrollToOffset };
}

export type { UseCM6EditorResult };
