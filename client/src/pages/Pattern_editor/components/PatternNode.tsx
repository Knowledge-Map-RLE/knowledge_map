import { Container, Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { PixiText } from '../../../shared/pixi/PixiText';
import { useCallback, useEffect, useRef, memo } from 'react';
import { BLOCK_DEFS, getBlockPorts } from '../model';
import type { BlockType, Port } from '../model';

extend({ Container, Graphics });

const DPR = typeof window !== 'undefined' ? Math.max(1, window.devicePixelRatio || 1) : 1;
const PORT_HIT_RADIUS = 16;
const PORT_DRAW_RADIUS = 7;
// Сврехдискретизация текста для чёткой прорисовки в канвасе.
const TEXT_RESOLUTION = Math.max(2, DPR * 2);

function hexToNumber(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
}

/** Отрисовывает форму блока в локальных координатах от (0,0) до (w,h). Все блоки — прямоугольник со скруглениями, различаются только цветом. */
function drawShape(g: Graphics, _type: BlockType, w: number, h: number, color: number): void {
    g.roundRect(0, 0, w, h, 12).fill(color);
}

export interface PatternNodeProps {
    id: string;
    type: BlockType;
    x: number;
    y: number;
    width: number;
    height: number;
    text: string;
    selected: boolean;
    onDragStart: (e: any, id: string) => void;
    onPortPointerDown: (e: any, port: Port) => void;
    onSelect: (id: string) => void;
}

export const PatternNode = memo(function PatternNode({
    id,
    type,
    x,
    y,
    width,
    height,
    text,
    selected,
    onDragStart,
    onPortPointerDown,
    onSelect,
}: PatternNodeProps) {
    const containerRef = useRef<Container>(null);
    const def = BLOCK_DEFS[type];
    const color = hexToNumber(def.color);

    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.x = x;
            containerRef.current.y = y;
        }
    }, [x, y]);

    const drawBg = useCallback(
        (g: Graphics) => {
            g.clear();
            drawShape(g, type, width, height, color);
            if (selected) {
                g.roundRect(-3, -3, width + 6, height + 6, 12).stroke({ width: 2, color: 0xffee58 });
            }
        },
        [type, width, height, color, selected]
    );

    const cx = width / 2;
    const cy = height / 2;

    // Возвращает порт, если точка в локальных координатах попала в его зону.
    const hitTestPort = useCallback(
        (local: { x: number; y: number } | null): Port | null => {
            if (!local) return null;
            for (const ref of getBlockPorts({ id, type, width, height })) {
                const d2 = (local.x - ref.localX) ** 2 + (local.y - ref.localY) ** 2;
                if (d2 <= PORT_HIT_RADIUS ** 2) {
                    return ref.port;
                }
            }
            return null;
        },
        [id, type, width, height]
    );

    const handlePointerDown = useCallback(
        (e: any) => {
            const local = containerRef.current?.toLocal(e.global);
            const hitPort = hitTestPort(local ?? null);
            if (hitPort) {
                e.stopPropagation();
                onPortPointerDown(e, hitPort);
            } else {
                onSelect(id);
                onDragStart(e, id);
            }
        },
        [hitTestPort, onPortPointerDown, onSelect, onDragStart]
    );

    // Курсор меняется при наведении на порт (crosshair) / на корпус блока (grab).
    const handlePointerMove = useCallback(
        (e: any) => {
            const local = containerRef.current?.toLocal(e.global);
            const el = containerRef.current;
            if (!el) return;
            el.cursor = hitTestPort(local ?? null) ? 'crosshair' : 'grab';
        },
        [hitTestPort]
    );

    const handlePointerOut = useCallback(() => {
        const el = containerRef.current;
        if (el) el.cursor = 'grab';
    }, []);

    const drawPort = useCallback(
        (g: Graphics, portId: string) => {
            g.clear();
            g.circle(0, 0, PORT_DRAW_RADIUS).fill(0xffffff).stroke({ width: 3, color });
            g.circle(0, 0, PORT_DRAW_RADIUS).stroke({ width: 2, color: 0x000000, alpha: 0.3 });
            (g as any).portId = portId;
        },
        [color]
    );

    return (
        <container
            ref={containerRef}
            zIndex={selected ? 2 : 1}
            sortableChildren={true}
            eventMode="static"
            cursor="grab"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerOut={handlePointerOut}
        >
            <pixiGraphics draw={drawBg} zIndex={0} />
            <PixiText
                text={def.label}
                x={cx}
                y={cy - (text ? 4 : 0)}
                anchor={0.5}
                zIndex={1}
                resolution={TEXT_RESOLUTION}
                style={{ fontSize: 13, fill: 0xffffff, fontWeight: '600', fontFamily: 'Arial' }}
            />
            {text && (
                <PixiText
                    text={text.length > 18 ? text.slice(0, 18) + '…' : text}
                    x={cx}
                    y={cy + 14}
                    anchor={0.5}
                    zIndex={1}
                    resolution={TEXT_RESOLUTION}
                    style={{ fontSize: 10, fill: 0xffffff, fontFamily: 'Arial' }}
                />
            )}
            {getBlockPorts({ id, type, width, height }).map((ref) => (
                <pixiGraphics
                    key={ref.port.id}
                    x={ref.localX}
                    y={ref.localY}
                    zIndex={10}
                    draw={(g: Graphics) => drawPort(g, ref.port.id)}
                    eventMode="none"
                />
            ))}
        </container>
    );
});
