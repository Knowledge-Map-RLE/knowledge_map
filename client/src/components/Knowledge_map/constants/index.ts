// Размеры блока
export const BLOCK_WIDTH = 150;
export const BLOCK_HEIGHT = 80;

// Отступы
export const LEVEL_PADDING = 40; // Внутренний отступ уровня
export const SUBLEVEL_PADDING = 30; // Внутренний отступ подуровня

// Расстояния между элементами
export const SUBLEVEL_SPACING = 200; // Расстояние между подуровнями в пикселях
export const LAYER_SPACING = 300; // Расстояние между слоями в пикселях

// Константы для расчета размеров в алгоритме укладки
export const LEVEL_HEIGHT = 300; // Высота уровня
export const SUBLEVEL_HEIGHT = 120; // Высота подуровня внутри уровня
export const SUBLEVEL_MARGIN = 20; // Отступ между подуровнями
export const LEVEL_MARGIN = 50; // Отступ между уровнями
export const GRAPH_WIDTH = 2000; // Полная ширина графа
export const BLOCK_SPACING_X = 400; // Горизонтальный интервал между блоками
export const BLOCK_SPACING_Y = 180; // Вертикальный интервал между блоками

// Цвета для уровней
export const LEVEL_COLORS = [
    0x4682b4,  // lightsteelblue
    0x20b2aa,  // lightseagreen
    0xfa8072,  // lightsalmon
    0xf0e68c,  // khaki
    0xdda0dd,  // plum
    0xd3d3d3,  // lightgray
    0xe0ffff,  // lightcyan
    0xe6e6fa   // lavender
];

// Цвета для подуровней
export const SUBLEVEL_COLORS = [
    0xadd8e6,  // lightblue
    0x90ee90,  // lightgreen
    0xf08080,  // lightcoral
    0xffffe0,  // lightyellow
    0xffc0cb,  // pink
    0xd3d3d3,  // lightgray
    0xe0ffff,  // lightcyan
    0xe6e6fa,  // lavender
    0xffe4e1,  // mistyrose
    0xf0fff0   // honeydew
]; 