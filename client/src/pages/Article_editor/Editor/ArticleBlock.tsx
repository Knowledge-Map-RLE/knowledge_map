import { Graphics, Text, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { PixiText } from '../../../shared/pixi/PixiText';
import { useCallback, useEffect, useRef, memo } from 'react';
import { getBlockTypeDef } from './blockTypes';
import { OUTCOME_COLORS } from './articleMapGraph';
import type { ArticleMapNode } from './articleMapGraph';

extend({ Container, Graphics, Text });

const BLOCK_WIDTH = 200;
const BLOCK_HEIGHT = 75;

const DPR = typeof window !== 'undefined' ? Math.max(1, window.devicePixelRatio || 1) : 1;

function hexToNumber(hex: string): number {
    const h = hex.replace('#', '');
    return parseInt(h, 16);
}

function shortId(uuid: string): string {
    return uuid.length > 8 ? uuid.slice(0, 8) + '…' : uuid;
}

interface ArticleBlockProps {
    blockData: ArticleMapNode;
    hovered: boolean;
    highlighted: boolean;
    dimmed: boolean;
    onHover: (id: string | null) => void;
}

export const ArticleBlock = memo(function ArticleBlock({
    blockData,
    hovered,
    highlighted,
    dimmed,
    onHover,
}: ArticleBlockProps) {
    const { id, x, y, blockType, label, outcome, outcomeLabel } = blockData;
    const containerRef = useRef<Container>(null);

    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.x = x;
            containerRef.current.y = y;
        }
    }, [x, y]);

    const typeDef = getBlockTypeDef(blockType);
    const typeColor = typeDef?.color ? hexToNumber(typeDef.color) : 0x6366f1;
    const outcomeColor = OUTCOME_COLORS[outcome];

    const drawBg = useCallback((g: Graphics) => {
        g.clear();
        g.roundRect(-BLOCK_WIDTH / 2, -BLOCK_HEIGHT / 2, BLOCK_WIDTH, BLOCK_HEIGHT, 8);
        if (highlighted) {
            const color = outcome === 'neutral' ? 0x9ca3af : outcomeColor;
            g.fill({ color, alpha: outcome === 'neutral' ? 0.1 : 0.16 });
            g.stroke({ width: hovered ? 3 : 2, color: hovered ? 0x111827 : color });
        } else {
            g.fill(0xffffff);
            g.stroke({ width: hovered ? 3 : 2, color: hovered ? 0x111827 : 0x6366f1 });
        }
    }, [highlighted, hovered, outcome, outcomeColor]);

    return (
        <container
            ref={containerRef}
            zIndex={1}
            alpha={dimmed ? 0.35 : 1}
            eventMode="static"
            cursor="pointer"
            onPointerEnter={() => onHover(id)}
            onPointerLeave={() => onHover(null)}
        >
            <pixiGraphics draw={drawBg} />
            <PixiText
                text={typeDef?.name ?? `T${blockType}`}
                x={0}
                y={-BLOCK_HEIGHT / 2 + 12}
                anchor={0.5}
                resolution={DPR}
                style={{ fontSize: 9, fill: typeColor, fontWeight: '600' }}
            />
            <PixiText
                text={label.slice(0, 44)}
                x={0}
                y={-BLOCK_HEIGHT / 2 + 30}
                anchor={0.5}
                resolution={DPR}
                style={{ fontSize: 10, fill: 0x111827, fontWeight: '500' }}
            />
            {outcome !== 'neutral' && outcomeLabel ? (
                <PixiText
                    text={outcomeLabel.slice(0, 40)}
                    x={0}
                    y={BLOCK_HEIGHT / 2 - 10}
                    anchor={0.5}
                    resolution={DPR}
                    style={{ fontSize: 9, fill: outcomeColor, fontStyle: 'italic' }}
                />
            ) : null}
            <PixiText
                text={shortId(id)}
                x={BLOCK_WIDTH / 2 - 4}
                y={BLOCK_HEIGHT / 2 - 4}
                anchor={{ x: 1, y: 1 }}
                resolution={DPR}
                style={{ fontSize: 8, fill: 0x9ca3af }}
            />
        </container>
    );
});
