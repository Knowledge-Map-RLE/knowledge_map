/**
 * Компонент для отображения ошибок валидации markdown
 */
import React, { useState } from 'react';
import styles from './ValidationErrorAlert.module.css';

export interface ValidationError {
  error_type: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
  line?: number;
  column?: number;
  start_offset?: number;
  end_offset?: number;
  context?: string;
  suggestion?: string;
  metadata?: Record<string, unknown>;
}

export interface ValidationResponse {
  success: boolean;
  is_valid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
  message: string;
  total_errors: number;
  total_warnings: number;
  metadata?: Record<string, unknown>;
}

interface ValidationErrorAlertProps {
  validation: ValidationResponse | null;
  onDismiss?: () => void;
  compact?: boolean;
}

const ERROR_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  MISSING_H1: { label: 'Отсутствует H1', icon: '📌', color: '#d32f2f' },
  MULTIPLE_H1: { label: 'Несколько H1', icon: '❌', color: '#d32f2f' },
  MALFORMED_FRONTMATTER: { label: 'Ошибка frontmatter', icon: '⚠️', color: '#f57c00' },
  INVALID_YAML: { label: 'Невалидный YAML', icon: '❌', color: '#d32f2f' },
  MARKDOWN_TABLE_FOUND: { label: 'Markdown таблица', icon: '📊', color: '#d32f2f' },
  MARKDOWN_IMAGE_FOUND: { label: 'Markdown изображение', icon: '🖼️', color: '#d32f2f' },
  MISSING_REFERENCES_SECTION: { label: 'Отсутствует References', icon: '📚', color: '#f57c00' },
  CITATION_WITHOUT_REFERENCE: { label: 'Цитата без ссылки', icon: '🔗', color: '#d32f2f' },
  ORPHANED_REFERENCE: { label: 'Неиспользованная ссылка', icon: '🔗', color: '#1976d2' },
  DUPLICATE_REFERENCE_NUMBER: { label: 'Дубликат номера', icon: '❌', color: '#d32f2f' },
};

export const ValidationErrorAlert: React.FC<ValidationErrorAlertProps> = ({
  validation,
  onDismiss,
  compact = false,
}) => {
  const [expandedErrors, setExpandedErrors] = useState<Set<number>>(new Set());

  if (!validation || validation.is_valid) {
    return null;
  }

  const toggleExpanded = (index: number) => {
    const newExpanded = new Set(expandedErrors);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedErrors(newExpanded);
  };

  const allErrors = [...validation.errors, ...validation.warnings];

  const getErrorInfo = (errorType: string) => {
    return ERROR_LABELS[errorType] || { label: errorType, icon: '⚠️', color: '#ff9800' };
  };

  if (compact) {
    return (
      <div className={styles.compactAlert}>
        <div className={styles.compactContent}>
          <span className={styles.compactIcon}>❌</span>
          <span className={styles.compactText}>
            Markdown содержит {validation.total_errors} ошибок и {validation.total_warnings} предупреждений
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.alertContainer}>
      <div className={styles.alertHeader}>
        <div className={styles.headerContent}>
          <h3 className={styles.title}>❌ Ошибки валидации Markdown</h3>
          <p className={styles.subtitle}>
            Найдено {validation.total_errors} ошибок и {validation.total_warnings} предупреждений.
          </p>
        </div>
        {onDismiss && (
          <button className={styles.dismissButton} onClick={onDismiss} title="Закрыть">
            ✕
          </button>
        )}
      </div>

      <div className={styles.errorsList}>
        {allErrors.map((error, index) => {
          const errorInfo = getErrorInfo(error.error_type);
          const isExpanded = expandedErrors.has(index);
          const isError = error.severity === 'error';

          return (
            <div
              key={index}
              className={`${styles.errorItem} ${isError ? styles.error : styles.warning}`}
            >
              <button className={styles.errorHeader} onClick={() => toggleExpanded(index)}>
                <div className={styles.errorIcon}>{errorInfo.icon}</div>
                <div className={styles.errorTitleSection}>
                  <div className={styles.errorTitle}>
                    {errorInfo.label}
                    {error.line && (
                      <span className={styles.errorLocation}>
                        Строка {error.line}
                        {error.column && `, колонка ${error.column}`}
                      </span>
                    )}
                  </div>
                  <div className={styles.errorMessage}>{error.message}</div>
                </div>
                <div className={`${styles.expandIcon} ${isExpanded ? styles.expanded : ''}`}>▼</div>
              </button>

              {isExpanded && (
                <div className={styles.errorDetails}>
                  {error.context && (
                    <div className={styles.context}>
                      <strong>Контекст:</strong>
                      <code>{error.context}</code>
                    </div>
                  )}
                  {error.suggestion && (
                    <div className={styles.suggestion}>
                      <strong>💡 Рекомендация:</strong>
                      <p>{error.suggestion}</p>
                    </div>
                  )}
                  {error.start_offset !== undefined && error.end_offset !== undefined && (
                    <div className={styles.metadata}>
                      <strong>Позиция:</strong>
                      <span>{error.start_offset}-{error.end_offset}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.alertFooter}>
        <p className={styles.footerText}>
          💡 Используйте справку (кнопка "?" в верхнем меню) для изучения правил
        </p>
      </div>
    </div>
  );
};

export default ValidationErrorAlert;
