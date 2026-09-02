import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, memo } from 'react';

extend({ Graphics });

export interface PatternEdgeProps {
    sx: number;
    sy: number;
    tx: number;
    ty: number;
    color?: number;
    width?: number;
    dashed?: boolean;
    selected?: boolean;
    interactive?: boolean;
    onSelect?: (id: string) => void;
    id?: string;
}

const ARROW_SIZE = 8;

/** Кривая Безье с направленной стрелкой; при клике можно выделить/удалить связь. */
export const PatternEdge = memo(function PatternEdge({
    sx,
    sy,
    tx,
    ty,
    color = 0x9e9e9e,
    width = 2,
    dashed = false,
    selected = false,
    interactive = false,
    onSelect,
    id = '',
}: PatternEdgeProps) {
    const draw = useCallback(
        (g: Graphics) => {
            const mx = (sx + tx) / 2;
            const mcY = ty;
            g.clear();

            // Невидимая широкая зона для удобного клика по тонкой линии
            g.moveTo(sx, sy);
            g.bezierCurveTo(mx, sy, mx, mcY, tx, ty);
            g.stroke({ width: 14, alpha: 0, cap: 'round', join: 'round' });

            const strokeColor = selected ? 0xffe24d : color;
            const strokeWidth = selected ? width + 2 : width;
            g.moveTo(sx, sy);
            g.bezierCurveTo(mx, sy, mx, mcY, tx, ty);
            g.stroke({
                width: strokeWidth,
                color: strokeColor,
                cap: 'round',
                join: 'round',
                ...(dashed ? { dash: [8, 6], alpha: 0.8 } : {}),
            });

            // Направление стрелки — касательная в конечной точке кривой
            const dx = tx - mx;
            const dy = ty - mcY;
            const len = Math.hypot(dx, dy) || 1;
            const ux = dx / len;
            const uy = dy / len;
            const px = -uy;
            const py = ux;
            const size = ARROW_SIZE;
            const baseX = tx - ux * size;
            const baseY = ty - uy * size;

            g.moveTo(tx, ty);
            g.lineTo(baseX + px * size, baseY + py * size);
            g.lineTo(baseX - px * size, baseY - py * size);
            g.closePath();
            g.fill(strokeColor);
        },
        [sx, sy, tx, ty, color, width, dashed, selected]
    );

    return (
        <pixiGraphics
            draw={draw}
            zIndex={0}
            eventMode={interactive ? 'static' : 'none'}
            cursor={interactive ? 'pointer' : undefined}
            onPointerDown={interactive && onSelect ? () => onSelect(id) : undefined}
        />
    );
});
