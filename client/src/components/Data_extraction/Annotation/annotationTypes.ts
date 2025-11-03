/**
 * Константы для типов аннотаций
 */

export interface AnnotationType {
  label: string;
  category: string;
  defaultColor: string;
}

// Типы аннотаций, организованные по категориям
export const ANNOTATION_TYPES: Record<string, AnnotationType> = {
  // Части речи
  'Существительное': { label: 'Существительное', category: 'Части речи', defaultColor: '#ffeb3b' },
  'Глагол': { label: 'Глагол', category: 'Части речи', defaultColor: '#ff9800' },
  'Прилагательное': { label: 'Прилагательное', category: 'Части речи', defaultColor: '#4caf50' },
  'Наречие': { label: 'Наречие', category: 'Части речи', defaultColor: '#2196f3' },
  'Местоимение': { label: 'Местоимение', category: 'Части речи', defaultColor: '#9c27b0' },
  'Предлог': { label: 'Предлог', category: 'Части речи', defaultColor: '#f44336' },
  'Союз': { label: 'Союз', category: 'Части речи', defaultColor: '#e91e63' },
  'Междометие': { label: 'Междометие', category: 'Части речи', defaultColor: '#00bcd4' },

  // Члены предложения
  'Подлежащее': { label: 'Подлежащее', category: 'Члены предложения', defaultColor: '#8bc34a' },
  'Сказуемое': { label: 'Сказуемое', category: 'Члены предложения', defaultColor: '#cddc39' },
  'Дополнение': { label: 'Дополнение', category: 'Члены предложения', defaultColor: '#ffc107' },
  'Обстоятельство': { label: 'Обстоятельство', category: 'Члены предложения', defaultColor: '#ff5722' },
  'Определение': { label: 'Определение', category: 'Члены предложения', defaultColor: '#795548' },

  // Научные сущности
  'Вид животного': { label: 'Вид животного', category: 'Научные сущности', defaultColor: '#9e9e9e' },
  'Модель животного': { label: 'Модель животного', category: 'Научные сущности', defaultColor: '#607d8b' },
  'Болезнь': { label: 'Болезнь', category: 'Научные сущности', defaultColor: '#f44336' },
  'Интервенция': { label: 'Интервенция', category: 'Научные сущности', defaultColor: '#e91e63' },
  'Гипотеза': { label: 'Гипотеза', category: 'Научные сущности', defaultColor: '#9c27b0' },
  'Тезис': { label: 'Тезис', category: 'Научные сущности', defaultColor: '#673ab7' },
  'Ген': { label: 'Ген', category: 'Научные сущности', defaultColor: '#3f51b5' },
  'Белок': { label: 'Белок', category: 'Научные сущности', defaultColor: '#2196f3' },

  // Общие сущности
  'Персона': { label: 'Персона', category: 'Общие сущности', defaultColor: '#03a9f4' },
  'Место': { label: 'Место', category: 'Общие сущности', defaultColor: '#00bcd4' },
  'Число': { label: 'Число', category: 'Общие сущности', defaultColor: '#009688' },
  'Единицы измерения': { label: 'Единицы измерения', category: 'Общие сущности', defaultColor: '#4caf50' },
  'Аббревиатура': { label: 'Аббревиатура', category: 'Общие сущности', defaultColor: '#8bc34a' },
  'Организация': { label: 'Организация', category: 'Общие сущности', defaultColor: '#cddc39' },
};

// Группировка по категориям для UI
export const ANNOTATION_CATEGORIES = {
  'Части речи': [
    'Существительное',
    'Глагол',
    'Прилагательное',
    'Наречие',
    'Местоимение',
    'Предлог',
    'Союз',
    'Междометие',
  ],
  'Члены предложения': [
    'Подлежащее',
    'Сказуемое',
    'Дополнение',
    'Обстоятельство',
    'Определение',
  ],
  'Научные сущности': [
    'Вид животного',
    'Модель животного',
    'Болезнь',
    'Интервенция',
    'Гипотеза',
    'Тезис',
    'Ген',
    'Белок',
  ],
  'Общие сущности': [
    'Персона',
    'Место',
    'Число',
    'Единицы измерения',
    'Аббревиатура',
    'Организация',
  ],
};

// Получить цвет по умолчанию для типа
export function getDefaultColor(annotationType: string): string {
  return ANNOTATION_TYPES[annotationType]?.defaultColor || '#ffeb3b';
}

// Получить категорию для типа
export function getCategory(annotationType: string): string {
  return ANNOTATION_TYPES[annotationType]?.category || 'Другое';
}
