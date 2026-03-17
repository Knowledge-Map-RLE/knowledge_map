/**
 * Обертка для EditorTabs с поддержкой валидации markdown и справкой
 */
import React, { useState, useRef, useEffect } from 'react';
import EditorTabs from './EditorTabs';
import ValidationErrorAlert, { ValidationResponse } from '../../MarkdownEditor/ValidationErrorAlert';
import MarkdownValidationRules from '../../MarkdownEditor/MarkdownValidationRules';
import useMarkdownValidation from '../../MarkdownEditor/useMarkdownValidation';
import AnnotationFilters from './AnnotationFilters';
import { Annotation, AnnotationRelation } from '../../../services/api';
import styles from './EditorTabsWithValidation.module.css';

export interface FilterProps {
  totalAnnotations: number;
  loadedAnnotationsCount: number;
  annotationsLimit: number;
  selectedCategories: string[];
  selectedSource: string | null;
  isLoadingMore: boolean;
  onCategoriesChange: (categories: string[]) => void;
  onSourceChange: (source: string | null) => void;
  onLimitChange: (limit: number) => void;
  onLoadMore: () => void;
  onResetFilters: () => void;
  annotations: Annotation[];
  hiddenTypes: Set<string>;
  onTypeVisibilityToggle: (type: string, visible: boolean) => void;
  onShowAllTypes: () => void;
}

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
  analysisProgress?: number | null;
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
  onDownloadMarkdown?: () => void;
  onValidationChange?: (validation: ValidationResponse | null) => void;
  filterProps?: FilterProps;
  onColorChange?: (color: string) => void;
  onRelationModeToggle?: () => void;
  onShowRelationsToggle?: () => void;
  onLineHeightToggle?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  forceTextVersion?: number;
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
      analysisProgress,
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
      onDownloadMarkdown,
      onValidationChange,
      filterProps,
      onColorChange,
      onRelationModeToggle,
      onShowRelationsToggle,
      onLineHeightToggle,
      onUndo,
      onRedo,
      forceTextVersion,
    },
    ref
  ) => {
    const [showColorPicker, setShowColorPicker] = useState(false);
    const [showValidationRules, setShowValidationRules] = useState(false);
    const [showValidationAlert, setShowValidationAlert] = useState(true);
    const [lastValidatedText, setLastValidatedText] = useState<string | null>(null);
    const [showFiltersDropdown, setShowFiltersDropdown] = useState(false);
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
        {/* Toolbar с кнопками инструментов */}
        <div className={styles.toolbarExtra}>
          {/* Цвет аннотации */}
          {onColorChange && (
            <div className={styles.filterDropdownWrapper}>
              <div
                className={styles.colorPreviewBtn}
                style={{ backgroundColor: selectedColor }}
                onClick={() => setShowColorPicker((v) => !v)}
                title="Выбрать цвет аннотации"
              />
              {showColorPicker && (
                <div className={styles.filterDropdown}>
                  <div style={{ padding: '10px' }}>
                    <input
                      type="color"
                      value={selectedColor}
                      onChange={(e) => onColorChange(e.target.value)}
                      style={{ width: '100%', height: '36px', border: 'none', borderRadius: '4px', cursor: 'pointer', marginBottom: '8px' }}
                    />
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px' }}>
                      {PREDEFINED_COLORS.map((color) => (
                        <div
                          key={color}
                          style={{ backgroundColor: color, width: '100%', aspectRatio: '1', borderRadius: '4px', cursor: 'pointer', border: '2px solid #ddd' }}
                          onClick={() => { onColorChange(color); setShowColorPicker(false); }}
                          title={color}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Кнопки Связей */}
          {onRelationModeToggle && (
            <button
              className={`${styles.helpButton} ${relationMode ? styles.helpButtonActive : ''}`}
              onClick={onRelationModeToggle}
              title={relationMode ? 'Выйти из режима создания связей' : 'Войти в режим создания связей'}
            >
              <span className={styles.helpText}>Режим связей</span>
            </button>
          )}
          {onShowRelationsToggle && (
            <button
              className={`${styles.helpButton} ${showRelations ? styles.helpButtonActive : ''}`}
              onClick={onShowRelationsToggle}
              title={showRelations ? 'Скрыть связи' : 'Показать связи'}
            >
              <span className={styles.helpText}>Показать связи</span>
            </button>
          )}
          {onLineHeightToggle && (
            <button
              className={`${styles.helpButton} ${largeLineHeight ? styles.helpButtonActive : ''}`}
              onClick={onLineHeightToggle}
              title="Межстрочный интервал"
            >
              <span className={styles.helpText}>Интервал</span>
            </button>
          )}

          {/* Фильтры */}
          {filterProps && (
            <div className={styles.filterDropdownWrapper}>
              <button
                className={styles.helpButton}
                onClick={() => setShowFiltersDropdown((v) => !v)}
                title="Фильтры аннотаций"
              >
                <span className={styles.helpText}>Фильтры</span>
              </button>
              {showFiltersDropdown && (
                <div className={styles.filterDropdown}>
                  <AnnotationFilters {...filterProps} />
                </div>
              )}
            </div>
          )}

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
            analysisProgress={analysisProgress}
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
            onDownloadMarkdown={onDownloadMarkdown}
            onUndo={onUndo}
            onRedo={onRedo}
            forceTextVersion={forceTextVersion}
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

const PREDEFINED_COLORS = [
  '#ffeb3b', '#ff9800', '#4caf50', '#2196f3', '#9c27b0',
  '#f44336', '#e91e63', '#00bcd4', '#8bc34a', '#cddc39',
  '#ffc107', '#ff5722', '#795548', '#9e9e9e', '#607d8b',
  '#673ab7', '#3f51b5', '#03a9f4', '#009688',
];

export default EditorTabsWithValidation;
