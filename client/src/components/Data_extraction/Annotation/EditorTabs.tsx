import React, { forwardRef } from 'react';
import TextAnnotator from './TextAnnotator';
import { Annotation, AnnotationRelation } from '../../../services/api';

interface EditorTabsProps {
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
  onUndo?: () => void;
  onRedo?: () => void;
  forceTextVersion?: number;
  onShiftLeft?: () => void;
  onShiftRight?: () => void;
  hasCursor?: boolean;
  onCursorMove?: (pos: number) => void;
}

const EditorTabs = forwardRef<HTMLDivElement, EditorTabsProps>(({
  mainTab,
  localText,
  visualAnnotations,
  relations,
  selectedType,
  selectedColor,
  relationMode,
  showRelations,
  largeLineHeight = false,
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
  onUndo,
  onRedo,
  forceTextVersion,
  onShiftLeft,
  onShiftRight,
  hasCursor,
  onCursorMove,
}, ref) => {
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onImportCSV) {
      onImportCSV(file);
      // Сбросить input для возможности повторного выбора того же файла
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };
  return (
    <div ref={ref} style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="main-tabs" style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '12px 16px',
        backgroundColor: '#f5f5f5',
        borderBottom: '1px solid #ddd',
        borderRadius: '4px 4px 0 0',
        flexWrap: 'wrap',
        flexShrink: 0
      }}>
        <div style={{ flex: 1 }}></div>

        {/* Multi-Level анализ кнопка */}
        {onMultiLevelAnnotate && (
          <button
            className="multilevel-annotate-button"
            onClick={onMultiLevelAnnotate}
            disabled={isAutoAnnotating || readOnly}
            title="Multi-level NLP анализ с голосованием (spaCy + NLTK)"
            style={{
              backgroundColor: isAutoAnnotating ? '#e0e0e0' : '#2196F3',
              color: isAutoAnnotating ? '#999' : 'white',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '4px',
              cursor: isAutoAnnotating || readOnly ? 'not-allowed' : 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            {isAutoAnnotating ? (
              analysisProgress !== null ? (
                `Обработано ${analysisProgress}%`
              ) : (
                'Обработка...'
              )
            ) : (
              'Автоматическая разметка'
            )}
          </button>
        )}

        {/* Загрузить Markdown */}
        {onDownloadMarkdown && (
          <button
            className="download-markdown-button"
            onClick={onDownloadMarkdown}
            title="Загрузить Markdown с изображениями в ZIP-архиве"
            style={{
              backgroundColor: '#009688',
              color: 'white',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            Загрузить Markdown
          </button>
        )}

        {/* Сдвиг аннотаций влево/вправо */}
        {onShiftLeft && (
          <button
            className="shift-left-button"
            onClick={onShiftLeft}
            disabled={!hasCursor}
            title={hasCursor ? 'Сдвинуть разметку влево от курсора' : 'Поставьте курсор в текст'}
            style={{
              backgroundColor: hasCursor ? '#5C6BC0' : '#e0e0e0',
              color: hasCursor ? 'white' : '#999',
              border: 'none',
              padding: '10px 12px',
              borderRadius: '4px',
              cursor: hasCursor ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            ← Влево
          </button>
        )}
        {onShiftRight && (
          <button
            className="shift-right-button"
            onClick={onShiftRight}
            disabled={!hasCursor}
            title={hasCursor ? 'Сдвинуть разметку вправо от курсора' : 'Поставьте курсор в текст'}
            style={{
              backgroundColor: hasCursor ? '#5C6BC0' : '#e0e0e0',
              color: hasCursor ? 'white' : '#999',
              border: 'none',
              padding: '10px 12px',
              borderRadius: '4px',
              cursor: hasCursor ? 'pointer' : 'not-allowed',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            Вправо →
          </button>
        )}

        {/* Импорт CSV */}
        {onImportCSV && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <button
              className="import-csv-button"
              onClick={handleImportClick}
              disabled={readOnly || !!importProgress}
              title="Импортировать аннотации из CSV"
              style={{
                backgroundColor: (readOnly || !!importProgress) ? '#e0e0e0' : '#FF9800',
                color: (readOnly || !!importProgress) ? '#999' : 'white',
                border: 'none',
                padding: '10px 16px',
                borderRadius: '4px',
                cursor: (readOnly || !!importProgress) ? 'not-allowed' : 'pointer',
                fontSize: '13px',
                fontWeight: '500',
                whiteSpace: 'nowrap',
                height: '36px',
                display: 'flex',
                alignItems: 'center'
              }}
            >
              {importProgress ? `Импорт ${importProgress.current}/${importProgress.total}` : 'Импорт CSV'}
            </button>
          </>
        )}

        {/* Экспорт CSV */}
        {onExportCSV && (
          <button
            className="export-csv-button"
            onClick={onExportCSV}
            title="Экспортировать аннотации в CSV"
            style={{
              backgroundColor: '#9C27B0',
              color: 'white',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            Экспорт CSV
          </button>
        )}

        {/* Сохранить для тестов */}
        {onSaveForTests && (
          <button
            className="save-for-tests-button"
            onClick={onSaveForTests}
            title="Сохранить документ с аннотациями в тестовый датасет"
            style={{
              backgroundColor: '#00BCD4',
              color: 'white',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '500',
              whiteSpace: 'nowrap',
              height: '36px',
              display: 'flex',
              alignItems: 'center'
            }}
          >
            Сохранить для тестов
          </button>
        )}

        {/* Удалить все аннотации */}
        <button
          className="delete-all-button"
          onClick={onDeleteAllAnnotations}
          disabled={readOnly}
          title="Удалить все аннотации документа"
          style={{
            backgroundColor: readOnly ? '#e0e0e0' : '#f44336',
            color: readOnly ? '#999' : 'white',
            border: 'none',
            padding: '10px 16px',
            borderRadius: '4px',
            cursor: readOnly ? 'not-allowed' : 'pointer',
            fontSize: '13px',
            fontWeight: '500',
            whiteSpace: 'nowrap',
            height: '36px',
            display: 'flex',
            alignItems: 'center'
          }}
        >
          Удалить все
        </button>

        {/* Сохранить */}
        <button
          className="save-button"
          onClick={onSave}
          disabled={!hasUnsavedChanges}
          style={{
            backgroundColor: !hasUnsavedChanges ? '#e0e0e0' : '#4CAF50',
            color: !hasUnsavedChanges ? '#999' : 'white',
            border: 'none',
            padding: '10px 16px',
            borderRadius: '4px',
            cursor: !hasUnsavedChanges ? 'not-allowed' : 'pointer',
            fontSize: '13px',
            fontWeight: '500',
            whiteSpace: 'nowrap',
            height: '36px',
            display: 'flex',
            alignItems: 'center'
          }}
        >
          {hasUnsavedChanges ? 'Сохранить *' : 'Сохранить'}
        </button>
      </div>

      <div className="main-content">
        <TextAnnotator
          ref={textAnnotatorRef}
          text={localText}
          annotations={visualAnnotations}
          relations={relations}
          selectedAnnotationType={selectedType}
          selectedColor={selectedColor}
          onTextSelect={onTextSelect}
          onAnnotationClick={onAnnotationClick}
          onAnnotationHover={() => {}}
          relationMode={relationMode}
          onRelationCreate={onRelationCreate}
          showRelations={showRelations}
          largeLineHeight={largeLineHeight}
          editable={!readOnly}
          onTextChange={onTextChange}
          selectedRelation={selectedRelation}
          onRelationClick={onRelationClick}
          onRelationDelete={onRelationDelete}
          onUndo={onUndo}
          onRedo={onRedo}
          forceTextVersion={forceTextVersion}
          onCursorMove={onCursorMove}
        />
      </div>
    </div>
  );
});

EditorTabs.displayName = 'EditorTabs';

export default EditorTabs;
