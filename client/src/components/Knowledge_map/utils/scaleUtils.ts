export interface ScaleUnit {
  name: string;
  symbol: string;
  exponent: number; // степень 10 относительно метра
}

export const SCALE_UNITS: ScaleUnit[] = [
  { name: 'нанометры', symbol: 'нм', exponent: -9 },
  { name: 'микрометры', symbol: 'мкм', exponent: -6 },
  { name: 'миллиметры', symbol: 'мм', exponent: -3 },
  { name: 'сантиметры', symbol: 'см', exponent: -2 },
  { name: 'дециметры', symbol: 'дм', exponent: -1 },
  { name: 'метры', symbol: 'м', exponent: 0 },
  { name: 'километры', symbol: 'км', exponent: 3 },
  { name: 'мегаметры', symbol: 'Мм', exponent: 6 },
  { name: 'гигаметры', symbol: 'Гм', exponent: 9 },
];

/**
 * Конвертирует экспоненту (степень 10) в удобные единицы измерения
 * @param exponent степень 10 в метрах
 * @returns объект с числом и единицей измерения
 */
export function exponentToReadableScale(exponent: number): { value: number; unit: ScaleUnit } {
  // Находим наиболее подходящую единицу измерения (кратную 10^3 или близкую к ней)
  let bestUnit = SCALE_UNITS.find(unit => unit.exponent === 0)!; // по умолчанию метры
  
  for (const unit of SCALE_UNITS) {
    if (unit.exponent <= exponent) {
      bestUnit = unit;
    } else {
      break;
    }
  }
  
  const value = Math.pow(10, exponent - bestUnit.exponent);
  return { value, unit: bestUnit };
}

/**
 * Конвертирует значение и единицу измерения в экспоненту (степень 10 в метрах)
 * @param value числовое значение
 * @param unit единица измерения  
 * @returns экспонента (степень 10 в метрах)
 */
export function readableScaleToExponent(value: number, unit: ScaleUnit): number {
  return Math.log10(value) + unit.exponent;
}

/**
 * Форматирует экспоненту в читаемый вид для отображения уровня
 * @param exponent степень 10 в метрах
 * @returns строка для отображения (например, "1 м", "10 км", "1 мм")
 */
export function formatScaleForDisplay(exponent: number): string {
  const { value, unit } = exponentToReadableScale(exponent);
  
  // Округляем значение для красивого отображения
  let displayValue: string;
  if (value === Math.floor(value)) {
    displayValue = value.toString();
  } else if (value < 1) {
    displayValue = value.toFixed(3).replace(/\.?0+$/, '');
  } else {
    displayValue = value.toFixed(1).replace(/\.?0+$/, '');
  }
  
  return `${displayValue} ${unit.symbol}`;
}

/**
 * Получает имя уровня по экспоненте масштаба
 * @param exponent степень 10 в метрах (по умолчанию 0 = 1 метр)
 * @returns отформатированное имя уровня
 */
export function getLevelName(exponent: number = 0): string {
  return formatScaleForDisplay(exponent);
} 