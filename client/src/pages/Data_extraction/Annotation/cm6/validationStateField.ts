import { StateField, StateEffect } from '@codemirror/state';
import type { ValidationError } from '../../../../widgets/MarkdownEditor';

export interface ValidationErrorWithPos {
  error_type: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
  start: number;
  end: number;
  suggestion?: string;
}

export const setValidationErrorsEffect = StateEffect.define<ValidationErrorWithPos[]>();

export const validationField = StateField.define<ValidationErrorWithPos[]>({
  create: () => [],
  update(errors, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setValidationErrorsEffect)) {
        return effect.value.slice().sort((a, b) => a.start - b.start || a.end - b.end);
      }
    }
    return errors;
  },
});

export function toValidationErrorWithPos(err: ValidationError): ValidationErrorWithPos | null {
  if (err.start_offset === undefined || err.end_offset === undefined) return null;
  if (err.start_offset >= err.end_offset) return null;
  return {
    error_type: err.error_type,
    message: err.message,
    severity: err.severity,
    start: err.start_offset,
    end: err.end_offset,
    suggestion: err.suggestion,
  };
}
