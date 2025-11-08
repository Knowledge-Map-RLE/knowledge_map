/**
 * Константы для типов аннотаций
 * Включает все 94 типа из spaCy + пользовательские научные типы
 */

export interface AnnotationType {
  label: string;
  category: string;
  defaultColor: string;
  source?: 'spacy' | 'user' | 'custom';
}

// Типы аннотаций, организованные по категориям (всего 94 типа spaCy + пользовательские)
export const ANNOTATION_TYPES: Record<string, AnnotationType> = {
  // === ЧАСТИ РЕЧИ (18 типов) ===
  'Существительное': { label: 'Существительное', category: 'Части речи', defaultColor: '#FFEB3B', source: 'spacy' },
  'Глагол': { label: 'Глагол', category: 'Части речи', defaultColor: '#8BC34A', source: 'spacy' },
  'Прилагательное': { label: 'Прилагательное', category: 'Части речи', defaultColor: '#4CAF50', source: 'spacy' },
  'Наречие': { label: 'Наречие', category: 'Части речи', defaultColor: '#FF9800', source: 'spacy' },
  'Местоимение': { label: 'Местоимение', category: 'Части речи', defaultColor: '#FFC107', source: 'spacy' },
  'Предлог': { label: 'Предлог', category: 'Части речи', defaultColor: '#2196F3', source: 'spacy' },
  'Сочинительный союз': { label: 'Сочинительный союз', category: 'Части речи', defaultColor: '#00BCD4', source: 'spacy' },
  'Подчинительный союз': { label: 'Подчинительный союз', category: 'Части речи', defaultColor: '#03A9F4', source: 'spacy' },
  'Междометие': { label: 'Междометие', category: 'Части речи', defaultColor: '#E91E63', source: 'spacy' },
  'Определитель': { label: 'Определитель', category: 'Части речи', defaultColor: '#3F51B5', source: 'spacy' },
  'Числительное': { label: 'Числительное', category: 'Части речи', defaultColor: '#00E676', source: 'spacy' },
  'Частица': { label: 'Частица', category: 'Части речи', defaultColor: '#FF5722', source: 'spacy' },
  'Имя собственное': { label: 'Имя собственное', category: 'Части речи', defaultColor: '#CDDC39', source: 'spacy' },
  'Пунктуация': { label: 'Пунктуация', category: 'Части речи', defaultColor: '#9E9E9E', source: 'spacy' },
  'Символ': { label: 'Символ', category: 'Части речи', defaultColor: '#607D8B', source: 'spacy' },
  'Прочее': { label: 'Прочее', category: 'Части речи', defaultColor: '#795548', source: 'spacy' },
  'Пробел': { label: 'Пробел', category: 'Части речи', defaultColor: '#FFFFFF', source: 'spacy' },
  'Вспомогательный глагол': { label: 'Вспомогательный глагол', category: 'Части речи', defaultColor: '#9C27B0', source: 'spacy' },

  // === СИНТАКСИС (42 типа зависимостей) ===
  'Придаточное определение': { label: 'Придаточное определение', category: 'Синтаксис', defaultColor: '#E1BEE7', source: 'spacy' },
  'Адъективное дополнение': { label: 'Адъективное дополнение', category: 'Синтаксис', defaultColor: '#C5CAE9', source: 'spacy' },
  'Обстоятельственное придаточное': { label: 'Обстоятельственное придаточное', category: 'Синтаксис', defaultColor: '#B2DFDB', source: 'spacy' },
  'Обстоятельство': { label: 'Обстоятельство', category: 'Синтаксис', defaultColor: '#C8E6C9', source: 'spacy' },
  'Агенс': { label: 'Агенс', category: 'Синтаксис', defaultColor: '#DCEDC8', source: 'spacy' },
  'Определение (прилагательное)': { label: 'Определение (прилагательное)', category: 'Синтаксис', defaultColor: '#F0F4C3', source: 'spacy' },
  'Приложение': { label: 'Приложение', category: 'Синтаксис', defaultColor: '#FFECB3', source: 'spacy' },
  'Именная часть сказуемого': { label: 'Именная часть сказуемого', category: 'Синтаксис', defaultColor: '#FFE0B2', source: 'spacy' },
  'Вспомогательный глагол (синт.)': { label: 'Вспомогательный глагол (синт.)', category: 'Синтаксис', defaultColor: '#FFCCBC', source: 'spacy' },
  'Вспомогательный глагол (страд.)': { label: 'Вспомогательный глагол (страд.)', category: 'Синтаксис', defaultColor: '#D7CCC8', source: 'spacy' },
  'Падежный показатель': { label: 'Падежный показатель', category: 'Синтаксис', defaultColor: '#CFD8DC', source: 'spacy' },
  'Сочинительный союз (синт.)': { label: 'Сочинительный союз (синт.)', category: 'Синтаксис', defaultColor: '#F8BBD0', source: 'spacy' },
  'Придаточное дополнение': { label: 'Придаточное дополнение', category: 'Синтаксис', defaultColor: '#E1BEE7', source: 'spacy' },
  'Сложное слово': { label: 'Сложное слово', category: 'Синтаксис', defaultColor: '#D1C4E9', source: 'spacy' },
  'Однородный член': { label: 'Однородный член', category: 'Синтаксис', defaultColor: '#C5CAE9', source: 'spacy' },
  'Придаточное подлежащее': { label: 'Придаточное подлежащее', category: 'Синтаксис', defaultColor: '#BBDEFB', source: 'spacy' },
  'Придаточное подлежащее (страд.)': { label: 'Придаточное подлежащее (страд.)', category: 'Синтаксис', defaultColor: '#B3E5FC', source: 'spacy' },
  'Дательный падеж': { label: 'Дательный падеж', category: 'Синтаксис', defaultColor: '#B2EBF2', source: 'spacy' },
  'Неопределённая зависимость': { label: 'Неопределённая зависимость', category: 'Синтаксис', defaultColor: '#B2DFDB', source: 'spacy' },
  'Определитель (синт.)': { label: 'Определитель (синт.)', category: 'Синтаксис', defaultColor: '#C8E6C9', source: 'spacy' },
  'Прямое дополнение': { label: 'Прямое дополнение', category: 'Синтаксис', defaultColor: '#DCEDC8', source: 'spacy' },
  'Формальное подлежащее': { label: 'Формальное подлежащее', category: 'Синтаксис', defaultColor: '#F0F4C3', source: 'spacy' },
  'Междометие (синт.)': { label: 'Междометие (синт.)', category: 'Синтаксис', defaultColor: '#FFECB3', source: 'spacy' },
  'Маркер (союз)': { label: 'Маркер (союз)', category: 'Синтаксис', defaultColor: '#FFE0B2', source: 'spacy' },
  'Мета-модификатор': { label: 'Мета-модификатор', category: 'Синтаксис', defaultColor: '#FFCCBC', source: 'spacy' },
  'Отрицание': { label: 'Отрицание', category: 'Синтаксис', defaultColor: '#D7CCC8', source: 'spacy' },
  'Именной модификатор': { label: 'Именной модификатор', category: 'Синтаксис', defaultColor: '#CFD8DC', source: 'spacy' },
  'Именная группа (обстоятельство)': { label: 'Именная группа (обстоятельство)', category: 'Синтаксис', defaultColor: '#F8BBD0', source: 'spacy' },
  'Числовой модификатор': { label: 'Числовой модификатор', category: 'Синтаксис', defaultColor: '#D7CCC8', source: 'spacy' },
  'Объектный предикат': { label: 'Объектный предикат', category: 'Синтаксис', defaultColor: '#CFD8DC', source: 'spacy' },
  'Паратаксис': { label: 'Паратаксис', category: 'Синтаксис', defaultColor: '#F8BBD0', source: 'spacy' },
  'Дополнение предлога': { label: 'Дополнение предлога', category: 'Синтаксис', defaultColor: '#E1BEE7', source: 'spacy' },
  'Объект предлога': { label: 'Объект предлога', category: 'Синтаксис', defaultColor: '#D1C4E9', source: 'spacy' },
  'Притяжательный модификатор': { label: 'Притяжательный модификатор', category: 'Синтаксис', defaultColor: '#C5CAE9', source: 'spacy' },
  'Предсоюз': { label: 'Предсоюз', category: 'Синтаксис', defaultColor: '#BBDEFB', source: 'spacy' },
  'Предопределитель': { label: 'Предопределитель', category: 'Синтаксис', defaultColor: '#B3E5FC', source: 'spacy' },
  'Предложное дополнение': { label: 'Предложное дополнение', category: 'Синтаксис', defaultColor: '#B2EBF2', source: 'spacy' },
  'Частица (синт.)': { label: 'Частица (синт.)', category: 'Синтаксис', defaultColor: '#B2DFDB', source: 'spacy' },
  'Пунктуация (синт.)': { label: 'Пунктуация (синт.)', category: 'Синтаксис', defaultColor: '#9E9E9E', source: 'spacy' },
  'Модификатор квантора': { label: 'Модификатор квантора', category: 'Синтаксис', defaultColor: '#C8E6C9', source: 'spacy' },
  'Относительное придаточное': { label: 'Относительное придаточное', category: 'Синтаксис', defaultColor: '#DCEDC8', source: 'spacy' },
  'Корень предложения': { label: 'Корень предложения', category: 'Синтаксис', defaultColor: '#F44336', source: 'spacy' },
  'Инфинитивное дополнение': { label: 'Инфинитивное дополнение', category: 'Синтаксис', defaultColor: '#E91E63', source: 'spacy' },

  // === ЧЛЕНЫ ПРЕДЛОЖЕНИЯ (2 типа из синтаксиса) ===
  'Подлежащее': { label: 'Подлежащее', category: 'Члены предложения', defaultColor: '#FFCDD2', source: 'spacy' },
  'Подлежащее (страд.)': { label: 'Подлежащее (страд.)', category: 'Члены предложения', defaultColor: '#FFCCBC', source: 'spacy' },

  // === ИМЕНОВАННЫЕ СУЩНОСТИ (18 типов) ===
  'Персона': { label: 'Персона', category: 'Именованные сущности', defaultColor: '#FF6B6B', source: 'spacy' },
  'Национальность/Религия/Политика': { label: 'Национальность/Религия/Политика', category: 'Именованные сущности', defaultColor: '#FFA07A', source: 'spacy' },
  'Здание/Сооружение': { label: 'Здание/Сооружение', category: 'Именованные сущности', defaultColor: '#FFD93D', source: 'spacy' },
  'Организация': { label: 'Организация', category: 'Именованные сущности', defaultColor: '#6BCF7F', source: 'spacy' },
  'Страна/Город/Штат': { label: 'Страна/Город/Штат', category: 'Именованные сущности', defaultColor: '#4ECDC4', source: 'spacy' },
  'Локация': { label: 'Локация', category: 'Именованные сущности', defaultColor: '#45B7D1', source: 'spacy' },
  'Продукт': { label: 'Продукт', category: 'Именованные сущности', defaultColor: '#96CEB4', source: 'spacy' },
  'Событие': { label: 'Событие', category: 'Именованные сущности', defaultColor: '#FFEAA7', source: 'spacy' },
  'Произведение искусства': { label: 'Произведение искусства', category: 'Именованные сущности', defaultColor: '#DFE6E9', source: 'spacy' },
  'Закон': { label: 'Закон', category: 'Именованные сущности', defaultColor: '#74B9FF', source: 'spacy' },
  'Язык': { label: 'Язык', category: 'Именованные сущности', defaultColor: '#A29BFE', source: 'spacy' },
  'Дата': { label: 'Дата', category: 'Именованные сущности', defaultColor: '#FD79A8', source: 'spacy' },
  'Время (сущность)': { label: 'Время (сущность)', category: 'Именованные сущности', defaultColor: '#FDCB6E', source: 'spacy' },
  'Процент': { label: 'Процент', category: 'Именованные сущности', defaultColor: '#55EFC4', source: 'spacy' },
  'Деньги': { label: 'Деньги', category: 'Именованные сущности', defaultColor: '#81ECEC', source: 'spacy' },
  'Количество': { label: 'Количество', category: 'Именованные сущности', defaultColor: '#74B9FF', source: 'spacy' },
  'Порядковое числительное': { label: 'Порядковое числительное', category: 'Именованные сущности', defaultColor: '#A29BFE', source: 'spacy' },
  'Количественное числительное': { label: 'Количественное числительное', category: 'Именованные сущности', defaultColor: '#FD79A8', source: 'spacy' },

  // === МОРФОЛОГИЯ (14 категорий) ===
  'Время': { label: 'Время', category: 'Морфология', defaultColor: '#E8F5E9', source: 'spacy' },
  'Вид': { label: 'Вид', category: 'Морфология', defaultColor: '#F1F8E9', source: 'spacy' },
  'Наклонение': { label: 'Наклонение', category: 'Морфология', defaultColor: '#F9FBE7', source: 'spacy' },
  'Залог': { label: 'Залог', category: 'Морфология', defaultColor: '#FFFDE7', source: 'spacy' },
  'Число': { label: 'Число', category: 'Морфология', defaultColor: '#FFF8E1', source: 'spacy' },
  'Лицо': { label: 'Лицо', category: 'Морфология', defaultColor: '#FFF3E0', source: 'spacy' },
  'Род': { label: 'Род', category: 'Морфология', defaultColor: '#FBE9E7', source: 'spacy' },
  'Падеж': { label: 'Падеж', category: 'Морфология', defaultColor: '#EFEBE9', source: 'spacy' },
  'Степень': { label: 'Степень', category: 'Морфология', defaultColor: '#ECEFF1', source: 'spacy' },
  'Форма глагола': { label: 'Форма глагола', category: 'Морфология', defaultColor: '#F3E5F5', source: 'spacy' },
  'Тип местоимения': { label: 'Тип местоимения', category: 'Морфология', defaultColor: '#EDE7F6', source: 'spacy' },
  'Притяжательное': { label: 'Притяжательное', category: 'Морфология', defaultColor: '#E8EAF6', source: 'spacy' },
  'Возвратное': { label: 'Возвратное', category: 'Морфология', defaultColor: '#E3F2FD', source: 'spacy' },
  'Тип числительного': { label: 'Тип числительного', category: 'Морфология', defaultColor: '#E1F5FE', source: 'spacy' },

  // === ПОЛЬЗОВАТЕЛЬСКИЕ НАУЧНЫЕ ТИПЫ ===
  'Вид животного': { label: 'Вид животного', category: 'Научные сущности', defaultColor: '#9e9e9e', source: 'user' },
  'Модель животного': { label: 'Модель животного', category: 'Научные сущности', defaultColor: '#607d8b', source: 'user' },
  'Болезнь': { label: 'Болезнь', category: 'Научные сущности', defaultColor: '#f44336', source: 'user' },
  'Интервенция': { label: 'Интервенция', category: 'Научные сущности', defaultColor: '#e91e63', source: 'user' },
  'Гипотеза': { label: 'Гипотеза', category: 'Научные сущности', defaultColor: '#9c27b0', source: 'user' },
  'Тезис': { label: 'Тезис', category: 'Научные сущности', defaultColor: '#673ab7', source: 'user' },
  'Ген': { label: 'Ген', category: 'Научные сущности', defaultColor: '#3f51b5', source: 'user' },
  'Белок': { label: 'Белок', category: 'Научные сущности', defaultColor: '#2196f3', source: 'user' },
  'Единицы измерения': { label: 'Единицы измерения', category: 'Научные сущности', defaultColor: '#4caf50', source: 'user' },
  'Аббревиатура': { label: 'Аббревиатура', category: 'Научные сущности', defaultColor: '#8bc34a', source: 'user' },
};

// Группировка по категориям для UI (автоматически генерируется из ANNOTATION_TYPES)
export const ANNOTATION_CATEGORIES: Record<string, string[]> = {};

// Автоматически группируем типы по категориям
for (const [typeName, typeInfo] of Object.entries(ANNOTATION_TYPES)) {
  const category = typeInfo.category;
  if (!ANNOTATION_CATEGORIES[category]) {
    ANNOTATION_CATEGORIES[category] = [];
  }
  ANNOTATION_CATEGORIES[category].push(typeName);
}

// Получить цвет по умолчанию для типа
export function getDefaultColor(annotationType: string): string {
  return ANNOTATION_TYPES[annotationType]?.defaultColor || '#ffeb3b';
}

// Получить категорию для типа
export function getCategory(annotationType: string): string {
  return ANNOTATION_TYPES[annotationType]?.category || 'Другое';
}
