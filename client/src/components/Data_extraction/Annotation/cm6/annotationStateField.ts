/**
 * CM6 StateField для хранения аннотаций.
 * Хранит аннотации как отсортированный массив + автоматически сдвигает офсеты
 * при изменении документа через changes.mapPos().
 */
import { StateField, StateEffect, ChangeSet, Annotation as CMAnnotation } from '@codemirror/state';
import type { Annotation } from '../../../../services/api';

export interface AnnotationWithPos {
  uid: string;
  start: number;
  end: number;
  annotation_type: string;
  color: string;
  text: string;
  source?: string;
}

// Transaction effect для замены всего набора аннотаций
export const setAnnotationsEffect = StateEffect.define<AnnotationWithPos[]>();

// Transaction annotation-маркер: замена текста документа целиком (не редактирование пользователем).
// При наличии этого маркера mapAnnotations пропускается — офсеты остаются как есть.
export const replaceDocAnnotation = CMAnnotation.define<true>();

// Функция преобразования Annotation → AnnotationWithPos
export const toAnnotationWithPos = (a: Annotation): AnnotationWithPos => ({
  uid: a.uid,
  start: a.start_offset,
  end: a.end_offset,
  annotation_type: a.annotation_type,
  color: a.color,
  text: a.text,
  source: a.source,
});

// StateField: хранит аннотации, отсортированные по start
export const annotationField = StateField.define<AnnotationWithPos[]>({
  create: () => [],

  update(annotations, tr) {
    // При явном обновлении через setAnnotationsEffect — заменяем весь массив
    for (const effect of tr.effects) {
      if (effect.is(setAnnotationsEffect)) {
        // Сервер возвращает аннотации отсортированными по start_offset (ORDER BY в Cypher).
        // Копируем массив без сортировки: O(n) вместо O(n log n).
        return effect.value.slice();
      }
    }

    // При изменении документа — автоматически сдвигаем офсеты.
    // Исключение: замена всего текста целиком (смена документа/загрузка markdown) —
    // офсеты аннотаций привязаны к новому тексту, маппинг не нужен.
    if (tr.docChanged) {
      if (tr.annotation(replaceDocAnnotation)) return annotations;
      return mapAnnotations(annotations, tr.changes);
    }

    return annotations;
  },
});

/**
 * Сдвигаем офсеты аннотаций в соответствии с изменением документа.
 * Аннотации, чей текст был удалён, помечаются для удаления (start === end).
 */
function mapAnnotations(
  annotations: AnnotationWithPos[],
  changes: ChangeSet
): AnnotationWithPos[] {
  const docLen = changes.length; // длина документа ДО изменения
  return annotations
    .map(ann => {
      // Клэмпим позиции: mapPos требует pos <= changes.length
      const clampedStart = Math.min(ann.start, docLen);
      const clampedEnd   = Math.min(ann.end,   docLen);
      if (clampedStart >= clampedEnd) return null;
      const newStart = changes.mapPos(clampedStart, 1);
      const newEnd   = changes.mapPos(clampedEnd,  -1);
      if (newStart >= newEnd) return null;
      return { ...ann, start: newStart, end: newEnd };
    })
    .filter(Boolean) as AnnotationWithPos[];
}

/**
 * Быстрый запрос: все аннотации, перекрывающие диапазон [from, to].
 * Массив отсортирован по start.
 *
 * Стратегия:
 * - Бинарный поиск находит первый индекс, где start >= from (кандидаты с конца диапазона)
 * - Затем итерация вперёд по start < to
 * - Аннотации с start < from но end > from (длинные) ищем линейно назад от найденного индекса
 *
 * Для типичных аннотаций (короткий span) — O(log N + results).
 * Для очень длинных аннотаций, перекрывающих весь viewport, — O(log N + long_spans).
 */
export function queryAnnotationsInRange(
  annotations: AnnotationWithPos[],
  from: number,
  to: number
): AnnotationWithPos[] {
  if (annotations.length === 0) return [];

  // Бинарный поиск: первый индекс где start >= from
  let lo = 0, hi = annotations.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (annotations[mid].start < from) lo = mid + 1;
    else hi = mid;
  }
  // lo = первый индекс с start >= from

  const result: AnnotationWithPos[] = [];

  // 1. Аннотации с start >= from и start < to
  for (let i = lo; i < annotations.length && annotations[i].start < to; i++) {
    result.push(annotations[i]);
  }

  // 2. Аннотации с start < from но end > from (перекрывают начало диапазона)
  // Массив отсортирован по start, но не по end — нельзя сделать ранний выход.
  // Для типичных коротких аннотаций таких будет 0–3 штуки.
  for (let i = lo - 1; i >= 0; i--) {
    if (annotations[i].end > from) {
      result.push(annotations[i]);
    }
  }

  return result;
}
