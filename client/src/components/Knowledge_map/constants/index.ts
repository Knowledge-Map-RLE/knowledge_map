// Размеры и расстояния
export const BLOCK_WIDTH = 200;
export const BLOCK_HEIGHT = 80;
export const BLOCK_MARGIN = 40;
export const LEVEL_PADDING = 30;
export const LAYER_SPACING = 220;
export const LEVEL_SPACING = 200;
export const LEVEL_HEIGHT = 120;
export const LEVEL_MARGIN = 20;

// Дополнительные константы для алгоритма раскладки
// Ширина области графа по оси X
export const GRAPH_WIDTH = 2000;
// Горизонтальное расстояние между слоями
export const BLOCK_SPACING_X = 250;
// Вертикальное расстояние между блоками в одном слое
export const BLOCK_SPACING_Y = 130;
// Высота подуровня и внутренние отступы подуровней
export const SUBLEVEL_HEIGHT = 120;
export const SUBLEVEL_MARGIN = 10;

// Цвета для блоков и уровней
export const BLOCK_COLORS = {
  default: '#E6F3FF',
  selected: '#99D6FF',
  pinned: '#FFE6CC',
  hover: '#CCEBFF'
};

export const LEVEL_COLORS = [
  '#F0F8FF', // Alice Blue
  '#F5F5DC', // Beige
  '#FFEFD5', // Papaya Whip
  '#E0FFFF', // Light Cyan
  '#F0FFF0', // Honeydew
  '#FFF8DC', // Cornsilk
  '#F5FFFA', // Mint Cream
  '#FFFAF0', // Floral White
  '#F0FFFF', // Azure
  '#FFF5EE'  // Seashell
];

// Настройки отображения
export const VIEWPORT_SETTINGS = {
  minZoom: 0.1,
  maxZoom: 3.0,
  defaultZoom: 1.0
}; 