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
  onAutoAnnotate: () => void;
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
  onAutoAnnotate,
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
    <div ref={ref} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="main-tabs" style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px',
        backgroundColor: '#f5f5f5',
        borderBottom: '1px solid #ddd',
        borderRadius: '4px 4px 0 0'
      }}>
        <div style={{ flex: 1 }}></div>
        <button
          className="auto-annotate-button"
          onClick={onAutoAnnotate}
          disabled={isAutoAnnotating || readOnly}
          title="Автоматическая аннотация с помощью spaCy"
          style={{
            backgroundColor: isAutoAnnotating ? '#ccc' : '#4CAF50',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: isAutoAnnotating || readOnly ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold'
          }}
        >
          {isAutoAnnotating ? '⏳ Обработка...' : '🤖 Автоаннотация spaCy'}
        </button>
        <button
          className="delete-all-button"
          onClick={onDeleteAllAnnotations}
          disabled={readOnly}
          title="Удалить все аннотации документа"
          style={{
            backgroundColor: readOnly ? '#ccc' : '#f44336',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: readOnly ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold'
          }}
        >
          🗑️ Удалить все аннотации
        </button>
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
                backgroundColor: readOnly ? '#ccc' : '#FF9800',
                color: 'white',
                border: 'none',
                padding: '8px 16px',
                borderRadius: '4px',
                cursor: readOnly ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: 'bold'
              }}
            >
              📥 Импортировать CSV
            </button>
          </>
        )}
        {onExportCSV && (
          <button
            className="export-csv-button"
            onClick={onExportCSV}
            title="Экспортировать аннотации в CSV"
            style={{
              backgroundColor: '#9C27B0',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
          >
            📤 Экспортировать CSV
          </button>
        )}
        <button
          className="save-button"
          onClick={onSave}
          disabled={!hasUnsavedChanges}
          style={{
            backgroundColor: !hasUnsavedChanges ? '#ccc' : '#2196F3',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: !hasUnsavedChanges ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold'
          }}
        >
          {hasUnsavedChanges ? '💾 Сохранить *' : '💾 Сохранить'}
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
