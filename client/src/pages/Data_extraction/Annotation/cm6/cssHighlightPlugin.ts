/**
 * CM6 ViewPlugin: рендеринг аннотаций через CSS Custom Highlight API.
 * Нулевые DOM-мутации — браузер рисует подсветку сам.
 * Активируется только если CSS.highlights поддерживается браузером.
 *
 * Преимущества vs Decoration.mark():
 * - Нет дополнительных DOM-узлов (0 span элементов для подсветки)
 * - Браузер рисует на этапе compositing — не вызывает reflow
 * - Нативная поддержка перекрывающихся диапазонов
 *
 * Browser support: Chrome 105+, Edge 105+, Safari 17.2+, Firefox 140+
 */
import { ViewPlugin, Decoration, DecorationSet } from '@codemirror/view';
import { RangeSet } from '@codemirror/state';
import type { ViewUpdate, EditorView } from '@codemirror/view';
import { annotationField, queryAnnotationsInRange } from './annotationStateField';

// Проверяем поддержку CSS Custom Highlight API
export const CSS_HIGHLIGHT_SUPPORTED =
  typeof CSS !== 'undefined' &&
  'highlights' in CSS &&
  typeof (globalThis as any).Highlight !== 'undefined';

const HIGHLIGHT_PREFIX = 'ann-';

/** Нормализует имя типа аннотации в допустимый CSS-идентификатор (ASCII-safe через хэш) */
function cssHighlightKey(annotationType: string): string {
  // Простой хэш строки → стабильный ASCII-идентификатор, избегает проблем с кириллицей в CSS
  let hash = 0;
  for (let i = 0; i < annotationType.length; i++) {
    hash = (Math.imul(31, hash) + annotationType.charCodeAt(i)) | 0;
  }
  // Преобразуем в беззнаковое hex
  const hex = (hash >>> 0).toString(16).padStart(8, '0');
  return HIGHLIGHT_PREFIX + hex;
}

// Кэш: annotationType → cssKey (чтобы не пересчитывать каждый раз)
const keyCache = new Map<string, string>();
function getCachedKey(annotationType: string): string {
  let key = keyCache.get(annotationType);
  if (!key) {
    key = cssHighlightKey(annotationType);
    keyCache.set(annotationType, key);
  }
  return key;
}

// Глобальный реестр зарегистрированных CSS-правил: cssKey → rgba-строка
const registeredStyles = new Map<string, string>();
let styleEl: HTMLStyleElement | null = null;

function ensureStyleEl(): HTMLStyleElement {
  if (!styleEl || !document.head.contains(styleEl)) {
    styleEl = document.getElementById('cm6-annotation-highlight-styles') as HTMLStyleElement | null;
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = 'cm6-annotation-highlight-styles';
      document.head.appendChild(styleEl);
    }
  }
  return styleEl;
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** Регистрирует CSS ::highlight() правило для типа, если ещё не зарегистрировано */
function ensureHighlightStyle(cssKey: string, color: string): void {
  const rgba = hexToRgba(color, 0.35);
  if (registeredStyles.get(cssKey) === rgba) return;
  registeredStyles.set(cssKey, rgba);
  const el = ensureStyleEl();
  // Добавляем правило в конец таблицы стилей
  el.textContent += `::highlight(${cssKey}) { background-color: ${rgba}; }\n`;
}

// Вызывается при монтировании — можно пустым, стили теперь добавляются динамически
export function injectAnnotationHighlightStyles(): void {
  // no-op: стили регистрируются динамически в updateHighlights по мере появления типов
}

function updateHighlights(view: EditorView): Set<string> {
  if (!CSS_HIGHLIGHT_SUPPORTED) return new Set();

  const annotations = view.state.field(annotationField);
  if (annotations.length === 0) return new Set();

  const docLength = view.state.doc.length;

  // Группируем Range по "приоритет-бакету" длины аннотации:
  // Более короткие аннотации = выше приоритет = рисуются поверх длинных.
  // Ключ: `${cssTypeKey}__${priorityBucket}` (0=длинные, 1=средние, 2=короткие)
  // CSS-правило привязано к typeKey, поэтому один бакет-ключ → один цвет.
  // Highlight.priority задаёт z-order между Highlight-объектами.

  // Приоритет по длине: короткие аннотации рисуются поверх длинных.
  // 3 бакета: 0=длинные (>500), 1=средние (50-500), 2=короткие (<50)
  const byBucketKey = new Map<string, { ranges: Range[]; priority: number; cssTypeKey: string; color: string }>();

  for (const { from, to } of view.visibleRanges) {
    for (const ann of queryAnnotationsInRange(annotations, from, to)) {
      const rangeFrom = Math.max(0, ann.start);
      const rangeTo   = Math.min(docLength, ann.end);
      if (rangeFrom >= rangeTo) continue;

      // Получаем DOM-позиции из CM6
      const startCoords = view.domAtPos(rangeFrom);
      const endCoords   = view.domAtPos(rangeTo);
      if (!startCoords.node || !endCoords.node) continue;

      const range = new Range();
      try {
        range.setStart(startCoords.node, startCoords.offset);
        range.setEnd(endCoords.node, endCoords.offset);
      } catch {
        continue; // DOM-позиция невалидна (может быть вне viewport)
      }

      const cssTypeKey = getCachedKey(ann.annotation_type);
      const color = ann.color || '#ffeb3b';
      // Убеждаемся что CSS-правило для этого ключа существует
      ensureHighlightStyle(cssTypeKey, color);

      const len = rangeTo - rangeFrom;
      const bucket = len < 50 ? 2 : len < 500 ? 1 : 0;
      const bucketKey = `${cssTypeKey}__${bucket}`;
      if (!byBucketKey.has(bucketKey)) {
        byBucketKey.set(bucketKey, { ranges: [], priority: bucket, cssTypeKey, color });
      }
      byBucketKey.get(bucketKey)!.ranges.push(range);
    }
  }

  const usedKeys = new Set<string>();
  for (const [, { ranges, priority, cssTypeKey, color }] of byBucketKey) {
    const fullKey = priority > 0 ? `${cssTypeKey}__p${priority}` : cssTypeKey;
    ensureHighlightStyle(fullKey, color);
    const highlight = new (globalThis as any).Highlight(...ranges);
    highlight.priority = priority;
    CSS.highlights.set(fullKey, highlight);
    usedKeys.add(fullKey);
  }

  return usedKeys;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '');
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

/**
 * Строит DecorationSet с data-атрибутами для поиска аннотаций из RelationsOverlay.
 * Когда CSS Custom Highlight API недоступен — также добавляет стили подсветки.
 * Когда Highlight API доступен — стили рисует браузер, декорации нужны только
 * для querySelector([data-annotation-id]) в RelationsOverlay.
 */
function buildDecorations(view: EditorView): DecorationSet {
  const annotations = view.state.field(annotationField);
  if (annotations.length === 0) return Decoration.none;

  const docLength = view.state.doc.length;
  const ranges: { from: number; to: number; value: Decoration }[] = [];
  const seen = new Set<string>();

  for (const { from, to } of view.visibleRanges) {
    for (const ann of queryAnnotationsInRange(annotations, from, to)) {
      if (seen.has(ann.uid)) continue;
      seen.add(ann.uid);

      const annFrom = Math.max(0, ann.start);
      const annTo   = Math.min(docLength, ann.end);
      if (annFrom >= annTo) continue;

      const attrs: Record<string, string> = {
        'data-annotation-id': ann.uid,
        'data-ann': ann.uid,
      };

      // Когда Highlight API недоступен — применяем стили через Decoration.mark
      if (!CSS_HIGHLIGHT_SUPPORTED) {
        const { r, g, b } = hexToRgb(ann.color || '#ffeb3b');
        attrs.style = `background-color:rgba(${r},${g},${b},0.35);border-radius:2px;cursor:pointer;`;
        attrs.title = `${ann.annotation_type}: "${ann.text}"`;
      }

      ranges.push({
        from: annFrom,
        to: annTo,
        value: Decoration.mark({ attributes: attrs }),
      });
    }
  }

  if (ranges.length === 0) return Decoration.none;
  return RangeSet.of(ranges.map(({ from, to, value }) => value.range(from, to)), true);
}

export const cssHighlightPlugin = ViewPlugin.fromClass(
  class {
    private usedKeys: Set<string> = new Set();
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildDecorations(view);
      this.scheduleMeasure(view);
    }

    update(update: ViewUpdate) {
      const annotationsChanged =
        update.state.field(annotationField) !== update.startState.field(annotationField);

      if (update.docChanged || annotationsChanged || update.viewportChanged) {
        this.clearKeys();
        this.usedKeys = updateHighlights(update.view);
        this.decorations = buildDecorations(update.view);
        this.scheduleMeasure(update.view);
      }
    }

    private scheduleMeasure(view: EditorView) {
      view.requestMeasure({
        key: this,
        read: () => {
          this.clearKeys();
          this.usedKeys = updateHighlights(view);
          return null;
        },
      });
    }

    private clearKeys() {
      for (const key of this.usedKeys) {
        CSS.highlights.delete(key);
      }
      this.usedKeys.clear();
    }

    destroy() {
      for (const key of this.usedKeys) {
        CSS.highlights.delete(key);
      }
      this.usedKeys.clear();
    }
  },
  {
    decorations: v => v.decorations,
  }
);
