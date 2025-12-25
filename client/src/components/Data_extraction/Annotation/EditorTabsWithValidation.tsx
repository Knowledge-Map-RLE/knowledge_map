/**
 * Обертка для EditorTabs с поддержкой валидации markdown и справкой
 */
import React, { useState, useRef, useEffect } from 'react';
import EditorTabs from './EditorTabs';
import ValidationErrorAlert, { ValidationResponse } from '../../MarkdownEditor/ValidationErrorAlert';
import MarkdownValidationRules from '../../MarkdownEditor/MarkdownValidationRules';
import useMarkdownValidation from '../../MarkdownEditor/useMarkdownValidation';
import { Annotation, AnnotationRelation } from '../../../services/api';
import styles from './EditorTabsWithValidation.module.css';

interface EditorTabsWithValidationProps {
  mainTab: 'text' | 'annotator';
  localText: string;
  visualAnnotations: Annotation[];
  relations: AnnotationRelation[];
  selectedType: string | null;
  selectedColor: string;
  relationMode: boolean;
  showRelations: boolean;
  largeLineHeight?: boolean;
  readOnly: boolean;
  onTabChange: (tab: 'text' | 'annotator') => void;
  onTextChange: (text: string) => void;
  onTextSelect: (start: number, end: number, text: string) => void;
  onAnnotationClick: (annotation: Annotation | Annotation[]) => void;
  onRelationCreate: (sourceId: string, targetId: string) => void;
  onMultiLevelAnnotate?: () => void;
  onSave: () => void;
  onDeleteAllAnnotations: () => void;
  isAutoAnnotating: boolean;
  hasUnsavedChanges: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  textAnnotatorRef: React.RefObject<HTMLDivElement>;
  selectedRelation?: AnnotationRelation | null;
  onRelationClick?: (relation: AnnotationRelation) => void;
  onRelationDelete?: (sourceId: string, targetId: string) => void;
  onExportCSV?: () => void;
  onImportCSV?: (file: File) => void;
  onSaveForTests?: () => void;
  onValidationChange?: (validation: ValidationResponse | null) => void;
}

const EditorTabsWithValidation = React.forwardRef<
  HTMLDivElement,
  EditorTabsWithValidationProps
>(
  (
    {
      mainTab,
      localText,
      visualAnnotations,
      relations,
      selectedType,
      selectedColor,
      relationMode,
      showRelations,
      largeLineHeight,
      readOnly,
      onTabChange,
      onTextChange,
      onTextSelect,
      onAnnotationClick,
      onRelationCreate,
      onMultiLevelAnnotate,
      onSave,
      onDeleteAllAnnotations,
      isAutoAnnotating,
      hasUnsavedChanges,
      textareaRef,
      textAnnotatorRef,
      selectedRelation,
      onRelationClick,
      onRelationDelete,
      onExportCSV,
      onImportCSV,
      onSaveForTests,
      onValidationChange,
    },
    ref
  ) => {
    const [showValidationRules, setShowValidationRules] = useState(false);
    const [showValidationAlert, setShowValidationAlert] = useState(true);
    const [lastValidatedText, setLastValidatedText] = useState<string | null>(null);
    const validationTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const { validation, isValidating, validateMarkdown, clearValidation } =
      useMarkdownValidation({
        apiUrl: '/api/data_extraction/markdown/validate',
      });

    // Автоматическая валидация при изменении текста (с debounce)
    useEffect(() => {
      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current);
      }

      if (localText && localText !== lastValidatedText) {
        validationTimeoutRef.current = setTimeout(() => {
          validateMarkdown(localText, false);
          setLastValidatedText(localText);
        }, 1500); // Delay 1.5s после последнего изменения
      }

      return () => {
        if (validationTimeoutRef.current) {
          clearTimeout(validationTimeoutRef.current);
        }
      };
    }, [localText, validateMarkdown, lastValidatedText]);

    // Уведомляем родительский компонент об изменении валидации
    useEffect(() => {
      if (onValidationChange) {
        onValidationChange(validation);
      }
    }, [validation, onValidationChange]);

    // Handle save with validation check
    const handleSaveWithValidation = () => {
      if (validation && !validation.is_valid) {
        // Показать ошибки валидации
        setShowValidationAlert(true);
        console.warn('Cannot save: Markdown validation failed', validation);
        return false;
      }
      onSave();
      return true;
    };

    return (
      <div ref={ref} className={styles.container}>
        {/* Toolbar с кнопкой справки */}
        <div className={styles.toolbarExtra}>
          <button
            className={styles.helpButton}
            onClick={() => setShowValidationRules(true)}
            title="Показать правила валидации markdown"
            disabled={readOnly}
          >
            <span className={styles.helpIcon}>?</span>
            <span className={styles.helpText}>Правила Markdown</span>
          </button>
        </div>

        {/* Editor and validation wrapper */}
        <div className={styles.editorWrapper}>
          {/* Validation Alert */}
          {showValidationAlert && validation && !validation.is_valid && (
            <ValidationErrorAlert
              validation={validation}
              onDismiss={() => setShowValidationAlert(false)}
            />
          )}

          {/* Loading state during validation */}
          {isValidating && (
            <div className={styles.validatingIndicator}>
              <span className={styles.spinner}>⟳</span>
              <span>Проверка markdown...</span>
            </div>
          )}

          {/* Valid indicator */}
          {validation && validation.is_valid && (
            <div className={styles.validIndicator}>
              <span className={styles.validIcon}>✓</span>
              <span>Markdown валидный</span>
            </div>
          )}

          {/* Main Editor Tabs Component */}
          <EditorTabs
            mainTab={mainTab}
            localText={localText}
            visualAnnotations={visualAnnotations}
            relations={relations}
            selectedType={selectedType}
            selectedColor={selectedColor}
            relationMode={relationMode}
            showRelations={showRelations}
            largeLineHeight={largeLineHeight}
            readOnly={readOnly}
            onTabChange={onTabChange}
            onTextChange={onTextChange}
            onTextSelect={onTextSelect}
            onAnnotationClick={onAnnotationClick}
            onRelationCreate={onRelationCreate}
            onMultiLevelAnnotate={onMultiLevelAnnotate}
            onSave={handleSaveWithValidation}
            onDeleteAllAnnotations={onDeleteAllAnnotations}
            isAutoAnnotating={isAutoAnnotating}
            hasUnsavedChanges={hasUnsavedChanges}
            textareaRef={textareaRef}
            textAnnotatorRef={textAnnotatorRef}
            selectedRelation={selectedRelation}
            onRelationClick={onRelationClick}
            onRelationDelete={onRelationDelete}
            onExportCSV={onExportCSV}
            onImportCSV={onImportCSV}
            onSaveForTests={onSaveForTests}
          />
        </div>

        {/* Validation Rules Modal */}
        <MarkdownValidationRules
          isOpen={showValidationRules}
          onClose={() => setShowValidationRules(false)}
        />
      </div>
    );
  }
);

EditorTabsWithValidation.displayName = 'EditorTabsWithValidation';

export default EditorTabsWithValidation;
