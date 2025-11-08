import React from 'react';
import { ANNOTATION_CATEGORIES } from './annotationTypes';

interface AnnotationFiltersProps {
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
}

const AnnotationFilters: React.FC<AnnotationFiltersProps> = ({
  totalAnnotations,
  loadedAnnotationsCount,
  annotationsLimit,
  selectedCategories,
  selectedSource,
  isLoadingMore,
  onCategoriesChange,
  onSourceChange,
  onLimitChange,
  onLoadMore,
  onResetFilters,
}) => {
  const handleCategoryToggle = (category: string, checked: boolean) => {
    if (checked) {
      onCategoriesChange([...selectedCategories, category]);
    } else {
      onCategoriesChange(selectedCategories.filter(c => c !== category));
    }
  };

  return (
    <div style={{
      padding: '10px',
      backgroundColor: '#f9f9f9',
      borderRadius: '4px'
    }}>
      <div style={{ marginBottom: '10px' }}>
        <strong>Фильтры:</strong>
        {totalAnnotations > annotationsLimit && (
          <div style={{ fontSize: '12px', color: '#f44336', marginTop: '5px' }}>
            ⚠️ Показано {loadedAnnotationsCount} из {totalAnnotations} аннотаций
          </div>
        )}
      </div>

      {/* Фильтр по источнику */}
      <div style={{ marginBottom: '10px' }}>
        <label style={{ fontSize: '13px', fontWeight: 'bold', display: 'block', marginBottom: '5px' }}>
          Источник:
        </label>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <label style={{ fontSize: '12px', cursor: 'pointer' }}>
            <input
              type="radio"
              name="source"
              checked={selectedSource === null}
              onChange={() => onSourceChange(null)}
            />
            {' '}Все
          </label>
          <label style={{ fontSize: '12px', cursor: 'pointer' }}>
            <input
              type="radio"
              name="source"
              checked={selectedSource === 'user'}
              onChange={() => onSourceChange('user')}
            />
            {' '}Пользователь
          </label>
          <label style={{ fontSize: '12px', cursor: 'pointer' }}>
            <input
              type="radio"
              name="source"
              checked={selectedSource === 'spacy'}
              onChange={() => onSourceChange('spacy')}
            />
            {' '}spaCy
          </label>
        </div>
      </div>

      {/* Фильтр по категориям */}
      <div style={{ marginBottom: '10px' }}>
        <label style={{ fontSize: '13px', fontWeight: 'bold', display: 'block', marginBottom: '5px' }}>
          Категории:
        </label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          {Object.keys(ANNOTATION_CATEGORIES).map(category => (
            <label key={category} style={{ fontSize: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={selectedCategories.includes(category)}
                onChange={(e) => handleCategoryToggle(category, e.target.checked)}
              />
              {' '}{category} ({ANNOTATION_CATEGORIES[category].length})
            </label>
          ))}
        </div>
      </div>

      {/* Лимит загрузки */}
      <div style={{ marginBottom: '5px' }}>
        <label style={{ fontSize: '13px', fontWeight: 'bold', display: 'block', marginBottom: '5px' }}>
          Лимит загрузки:
        </label>
        <select
          value={annotationsLimit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          style={{ fontSize: '12px', padding: '5px', width: '100%' }}
        >
          <option value={100}>100</option>
          <option value={500}>500</option>
          <option value={1000}>1000</option>
          <option value={2000}>2000</option>
          <option value={5000}>5000</option>
          <option value={10000}>10000</option>
        </select>
      </div>

      {/* Кнопка "Загрузить еще" */}
      {loadedAnnotationsCount < totalAnnotations && (
        <button
          onClick={onLoadMore}
          disabled={isLoadingMore}
          style={{
            fontSize: '12px',
            padding: '8px 10px',
            width: '100%',
            backgroundColor: isLoadingMore ? '#ccc' : '#2196F3',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: isLoadingMore ? 'not-allowed' : 'pointer',
            marginBottom: '5px',
            fontWeight: 'bold'
          }}
        >
          {isLoadingMore
            ? '⏳ Загрузка...'
            : `📥 Загрузить еще (${loadedAnnotationsCount} из ${totalAnnotations})`
          }
        </button>
      )}

      {/* Кнопка сброса фильтров */}
      {(selectedCategories.length > 0 || selectedSource !== null) && (
        <button
          onClick={onResetFilters}
          style={{
            fontSize: '12px',
            padding: '5px 10px',
            width: '100%',
            backgroundColor: '#f44336',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            marginTop: '5px'
          }}
        >
          Сбросить фильтры
        </button>
      )}
    </div>
  );
};

export default AnnotationFilters;
