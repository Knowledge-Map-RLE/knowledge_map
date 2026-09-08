import { Graphics, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import { useRef, useMemo, useCallback, useEffect, memo } from 'react';
import { PixiText } from '../../shared/pixi/PixiText';

extend({ Graphics, Text });

export const TRIPLE_BLOCK_WIDTH = 250;
export const TRIPLE_BLOCK_MIN_HEIGHT = 64;
export const TRIPLE_BLOCK_MAX_HEIGHT = 200;
const PADDING = 8;
const ID_FONT_SIZE = 10;
const ID_LINE_HEIGHT = 14;
const CONTENT_GAP = 6;
const CONTENT_FONT_SIZE = 13;
const MIN_CONTENT_FONT_SIZE = 9;
const LINE_HEIGHT_RATIO = 1.38;

interface TripleBlockProps {
  id: string;
  content: string;
  x: number;
  y: number;
  isPlaceholder?: boolean;
  isSelected?: boolean;
  isGoal?: boolean;
  isPlan?: boolean;
  onClick?: (id: string) => void;
}

/** Высота перенесённого текста при заданном размере шрифта (в px). */
function measureWrappedText(text: string, fontSize: number): number {
  const lineHeight = Math.round(fontSize * LINE_HEIGHT_RATIO);
  try {
    const probe = new Text({
      text: text || '',
      style: {
        fontFamily: 'Arial',
        fontSize,
        wordWrap: true,
        wordWrapWidth: TRIPLE_BLOCK_WIDTH - PADDING * 2,
        lineHeight,
      } as any,
    });
    const h = probe.height || lineHeight;
    probe.destroy();
    return h;
  } catch {
    return lineHeight;
  }
}

/** Подбирает размер шрифта и высоту блока так, чтобы содержимое помещалось. */
function computeBlockLayout(contentLine: string): {
  boxHeight: number;
  contentFont: number;
  contentLineHeight: number;
} {
  const maxContentH =
    TRIPLE_BLOCK_MAX_HEIGHT - PADDING * 2 - ID_LINE_HEIGHT;

  let contentFont = CONTENT_FONT_SIZE;
  for (let fs = CONTENT_FONT_SIZE; fs >= MIN_CONTENT_FONT_SIZE; fs--) {
    if (measureWrappedText(contentLine, fs) <= maxContentH) {
      contentFont = fs;
      break;
    }
  }

  const textH = measureWrappedText(contentLine, contentFont);
  const boxHeight = Math.max(
    TRIPLE_BLOCK_MIN_HEIGHT,
    PADDING * 2 + ID_LINE_HEIGHT + CONTENT_GAP + textH,
  );
  return {
    boxHeight,
    contentFont,
    contentLineHeight: Math.round(contentFont * LINE_HEIGHT_RATIO),
  };
}

/**
 * Pixi-блок триплета: прямоугольник с двумя текстовыми строками —
 * первая строка идентификатор (uid), вторая — содержимое триплета.
 * Ширина блока фиксированная, высота подстраивается под перенесённый
 * текст; при длинном содержимом размер шрифта уменьшается, чтобы
 * текст поместился в максимальную высоту блока.
 */
export const TripleBlock = memo(function TripleBlock({
  id,
  content,
  x,
  y,
  isPlaceholder = false,
  isSelected = false,
  isGoal = false,
  isPlan = false,
  onClick,
}: TripleBlockProps) {
  const containerRef = useRef<any>(null);

  const lines = content.split('\n');
  const idLine = lines[0] || id;
  const contentLine = lines.slice(1).join('\n') || content;

  const { boxHeight, contentFont, contentLineHeight } = useMemo(
    () => computeBlockLayout(contentLine),
    [contentLine],
  );

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.x = x;
      containerRef.current.y = y;
    }
  }, [x, y]);

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      const highlighted = isGoal || isPlan;
      const bg = isPlaceholder
        ? 0xfff7ed
        : isSelected
          ? 0x93c5fd
          : highlighted
            ? 0xfef3c7
            : 0xffffff;
      const border = isPlaceholder
        ? 0xf59e0b
        : isSelected
          ? 0x2563eb
          : highlighted
            ? 0xf59e0b
            : 0xd1d5db;
      const w = TRIPLE_BLOCK_WIDTH;
      const h = boxHeight;
      g.roundRect(-w / 2, -h / 2, w, h, 10);
      g.fill(bg);
      g.stroke({
        width: isSelected || isPlaceholder || highlighted ? 2 : 1,
        color: border,
      });
    },
    [isPlaceholder, isSelected, isGoal, isPlan, boxHeight],
  );

  return (
    <container
      ref={containerRef}
      eventMode="static"
      cursor="pointer"
      zIndex={1}
      onClick={onClick ? () => onClick(id) : undefined}
    >
      <pixiGraphics draw={draw} />
      <PixiText
        text={idLine}
        x={0}
        y={-boxHeight / 2 + PADDING}
        anchor={{ x: 0.5, y: 0 }}
        style={{
          fontSize: ID_FONT_SIZE,
          fill: isPlaceholder ? 0xb45309 : 0x9ca3af,
          fontFamily: 'monospace',
          align: 'center',
        }}
      />
      <PixiText
        text={contentLine}
        x={0}
        y={-boxHeight / 2 + PADDING + ID_LINE_HEIGHT}
        anchor={{ x: 0.5, y: 0 }}
        style={{
          fontSize: contentFont,
          fill: 0x1f2937,
          align: 'center',
          wordWrap: true,
          wordWrapWidth: TRIPLE_BLOCK_WIDTH - PADDING * 2,
          fontFamily: 'Arial',
          lineHeight: contentLineHeight,
        }}
      />
    </container>
  );
});