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
  onSaveForTests?: () => void;
  onDownloadMarkdown?: () => void;
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
  onSaveForTests,
  onDownloadMarkdown,
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
              disabled={readOnly}
              title="Импортировать аннотации из CSV"
              style={{
                backgroundColor: readOnly ? '#e0e0e0' : '#FF9800',
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
              Импорт CSV
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
        />
      </div>
    </div>
  );
});

EditorTabs.displayName = 'EditorTabs';

export default EditorTabs;
