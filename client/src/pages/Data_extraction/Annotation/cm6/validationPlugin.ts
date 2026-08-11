import { ViewPlugin, Decoration, hoverTooltip } from '@codemirror/view';
import type { DecorationSet } from '@codemirror/view';
import { RangeSet } from '@codemirror/state';
import type { ViewUpdate, EditorView } from '@codemirror/view';
import { validationField } from './validationStateField';

function buildValidationDecorations(view: EditorView): DecorationSet {
  const errors = view.state.field(validationField);
  if (errors.length === 0) return Decoration.none;

  const ranges: { from: number; to: number; value: Decoration }[] = [];

  for (const err of errors) {
    if (err.start >= err.end) continue;

    ranges.push({
      from: err.start,
      to: err.end,
      value: Decoration.mark({
        attributes: {
          class: 'cm-validation-error',
          'data-error-type': err.error_type,
        },
      }),
    });
  }

  if (ranges.length === 0) return Decoration.none;
  return RangeSet.of(
    ranges.map(({ from, to, value }) => value.range(from, to)),
    true,
  );
}

export const validationDecorationsPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildValidationDecorations(view);
    }

    update(update: ViewUpdate) {
      if (
        update.viewportChanged ||
        update.state.field(validationField) !== update.startState.field(validationField)
      ) {
        this.decorations = buildValidationDecorations(update.view);
      }
    }
  },
  { decorations: v => v.decorations },
);

export const validationTooltip = hoverTooltip((view, pos, _side) => {
  const errors = view.state.field(validationField);
  for (const err of errors) {
    if (pos >= err.start && pos <= err.end) {
      return {
        pos: err.start,
        end: err.end,
        above: true,
        create() {
          const dom = document.createElement('div');
          dom.className = 'cm-validation-tooltip';

          const header = document.createElement('div');
          header.className = 'cm-validation-tooltip-header';
          header.textContent = err.error_type.replace(/_/g, ' ');
          dom.appendChild(header);

          const message = document.createElement('div');
          message.className = 'cm-validation-tooltip-message';
          message.textContent = err.message;
          dom.appendChild(message);

          if (err.suggestion) {
            const suggestion = document.createElement('div');
            suggestion.className = 'cm-validation-tooltip-suggestion';
            suggestion.textContent = `💡 ${err.suggestion}`;
            dom.appendChild(suggestion);
          }

          return { dom };
        },
      };
    }
  }
  return null;
});
