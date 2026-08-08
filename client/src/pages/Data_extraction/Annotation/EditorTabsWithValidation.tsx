/**
 * Обертка для EditorTabs с поддержкой валидации markdown и справкой
 */
import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import EditorTabs from './EditorTabs';
import { ValidationErrorAlert, type ValidationResponse, type ValidationError } from '../../../widgets/MarkdownEditor';
import { MarkdownValidationRules } from '../../../widgets/MarkdownEditor';
import { useMarkdownValidation } from '../../../widgets/MarkdownEditor';
import AnnotationFilters from './AnnotationFilters';
import { Annotation, AnnotationRelation } from '../../../services/api';
import styles from './EditorTabsWithValidation.module.css';

export interface FilterProps {
  totalAnnotations: number;
  selectedCategories: string[];
  selectedSource: string | null;
  onCategoriesChange: (categories: string[]) => void;
  onSourceChange: (source: string | null) => void;
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
  importProgress?: { current: number; total: number } | null;
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
  onShiftLeft?: () => void;
  onShiftRight?: () => void;
  hasCursor?: boolean;
  onCursorMove?: (pos: number) => void;
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
      importProgress,
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
      onShiftLeft,
      onShiftRight,
      hasCursor,
      onCursorMove,
    },
    ref
  ) => {
    const [showColorPicker, setShowColorPicker] = useState(false);
    const [showValidationRules, setShowValidationRules] = useState(false);
    const [showValidationAlert, setShowValidationAlert] = useState(true);
    const [showFiltersDropdown, setShowFiltersDropdown] = useState(false);
    const validationTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    // Флаг: пользователь сам вводил текст через onTextChange
    const userEditedRef = useRef(false);

    const { validation, isValidating, validateMarkdown, clearValidation } =
      useMarkdownValidation({
        apiUrl: '/api/data_extraction/markdown/validate',
      });

    // Обёртка над onTextChange: ставим флаг при реальном вводе пользователя
    const handleTextChange = useCallback((text: string) => {
      userEditedRef.current = true;
      onTextChange(text);
    }, [onTextChange]);

    // Автоматическая валидация с debounce — только после реального ввода
    useEffect(() => {
      if (!userEditedRef.current) return;

      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current);
      }

      validationTimeoutRef.current = setTimeout(() => {
        validateMarkdown(localText, false);
      }, 1500);

      return () => {
        if (validationTimeoutRef.current) {
          clearTimeout(validationTimeoutRef.current);
        }
      };
    }, [localText, validateMarkdown]);

    // Уведомляем родительский компонент об изменении валидации
    useEffect(() => {
      if (onValidationChange) {
        onValidationChange(validation);
      }
    }, [validation, onValidationChange]);

    // Handle save with validation check
    const handleSaveWithValidation = () => {
      if (validation && !validation.is_valid) {
        // Показать ошибки валидации, но не блокировать сохранение
        setShowValidationAlert(true);
        console.warn('Markdown validation failed, saving anyway', validation);
      }
      onSave();
      return true;
    };

    // Ошибки валидации с координатами в тексте — для подсветки в аннотаторе
    const validationErrorsWithOffsets: ValidationError[] = useMemo(() => {
      if (!validation) return [];
      const all = [...validation.errors, ...validation.warnings];
      return all.filter(
        e => e.start_offset !== undefined && e.end_offset !== undefined && e.start_offset < e.end_offset
      );
    }, [validation]);

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

          {/* Inline-индикатор валидации в панели */}
          {isValidating && (
            <span className={styles.validationBadge} title="Проверка markdown...">
              <span className={styles.spinner}>⟳</span>
            </span>
          )}
          {!isValidating && validation && validation.is_valid && validation.total_warnings === 0 && (
            <span className={styles.validationBadgeOk} title="Markdown валидный">✓</span>
          )}
          {!isValidating && validation && (!validation.is_valid || validation.total_warnings > 0) && (
            <button
              className={styles.validationBadgeError}
              title={`${validation.errors?.length ?? 0} ошибок, ${validation.total_warnings ?? 0} предупреждений`}
              onClick={() => setShowValidationAlert((v) => !v)}
            >
              ✗ {validation.errors?.length ?? 0}
            </button>
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
            onTextChange={handleTextChange}
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
            importProgress={importProgress}
            onSaveForTests={onSaveForTests}
            onDownloadMarkdown={onDownloadMarkdown}
            onUndo={onUndo}
            onRedo={onRedo}
            forceTextVersion={forceTextVersion}
            onShiftLeft={onShiftLeft}
            onShiftRight={onShiftRight}
            hasCursor={hasCursor}
            onCursorMove={onCursorMove}
            validationErrors={validationErrorsWithOffsets}
          />

          {/* Validation Alert — под редактором */}
          {showValidationAlert && validation && (!validation.is_valid || validation.total_warnings > 0) && (
            <ValidationErrorAlert
              validation={validation}
              onDismiss={() => setShowValidationAlert(false)}
            />
          )}
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
