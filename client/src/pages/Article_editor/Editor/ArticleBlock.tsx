import { CanvasTextMetrics, Graphics, Text, TextStyle, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { PixiText } from '../../../shared/pixi/PixiText';
import { useCallback, useEffect, useRef, memo } from 'react';
import { getBlockTypeDef } from './blockTypes';
import { OUTCOME_COLORS } from './articleMapGraph';
import type { ArticleMapNode } from './articleMapGraph';

extend({ Container, Graphics, Text });

export const ARTICLE_BLOCK_WIDTH = 200;
const MIN_BLOCK_HEIGHT = 75;
const LABEL_WIDTH = ARTICLE_BLOCK_WIDTH - 24;
const LABEL_TOP_OFFSET = 24;
const LABEL_STYLE = new TextStyle({
    fontFamily: 'Arial',
    fontSize: 10,
    fontWeight: '500',
    wordWrap: true,
    wordWrapWidth: LABEL_WIDTH,
    breakWords: true,
    align: 'center',
});

export function getArticleBlockHeight(label: string, hasFooter: boolean): number {
    const textHeight = CanvasTextMetrics.measureText(label || ' ', LABEL_STYLE).height;
    const footerHeight = hasFooter ? 24 : 18;
    return Math.max(MIN_BLOCK_HEIGHT, LABEL_TOP_OFFSET + textHeight + footerHeight);
}

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
    const { id, x, y, blockType, label, outcome, outcomeLabel, isGoal } = blockData;
    const hasFooter = Boolean(isGoal || (outcome !== 'neutral' && outcomeLabel));
    const blockHeight = blockData.height ?? getArticleBlockHeight(label, hasFooter);
    const labelMetrics = CanvasTextMetrics.measureText(label || ' ', LABEL_STYLE);
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
        g.roundRect(-ARTICLE_BLOCK_WIDTH / 2, -blockHeight / 2, ARTICLE_BLOCK_WIDTH, blockHeight, 8);
        if (highlighted) {
            const color = isGoal ? 0xea580c : outcome === 'neutral' ? 0x9ca3af : outcomeColor;
            g.fill({ color, alpha: isGoal ? 0.16 : outcome === 'neutral' ? 0.1 : 0.16 });
            g.stroke({ width: hovered ? 3 : 2, color: hovered ? 0x111827 : color });
        } else {
            g.fill(0xffffff);
            g.stroke({ width: hovered ? 3 : 2, color: hovered ? 0x111827 : isGoal ? 0xea580c : 0x6366f1 });
        }
    }, [blockHeight, highlighted, hovered, outcome, outcomeColor, isGoal]);

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
                text={typeDef?.name ?? blockType}
                x={0}
                y={-blockHeight / 2 + 12}
                anchor={0.5}
                resolution={DPR}
                style={{ fontSize: 9, fill: typeColor, fontWeight: '600' }}
            />
            <PixiText
                text={label}
                x={0}
                y={-blockHeight / 2 + LABEL_TOP_OFFSET + labelMetrics.height / 2}
                anchor={0.5}
                resolution={DPR}
                style={{ ...LABEL_STYLE, fill: 0x111827 }}
            />
            {isGoal ? (
                <PixiText
                    text="ЦЕЛЬ"
                    x={0}
                    y={blockHeight / 2 - 10}
                    anchor={0.5}
                    resolution={DPR}
                    style={{ fontSize: 9, fill: 0xea580c, fontWeight: '700' }}
                />
            ) : outcome !== 'neutral' && outcomeLabel ? (
                <PixiText
                    text={outcomeLabel.slice(0, 40)}
                    x={0}
                    y={blockHeight / 2 - 10}
                    anchor={0.5}
                    resolution={DPR}
                    style={{ fontSize: 9, fill: outcomeColor, fontStyle: 'italic' }}
                />
            ) : null}
            <PixiText
                text={shortId(id)}
                x={ARTICLE_BLOCK_WIDTH / 2 - 4}
                y={blockHeight / 2 - 4}
                anchor={{ x: 1, y: 1 }}
                resolution={DPR}
                style={{ fontSize: 8, fill: 0x9ca3af }}
            />
        </container>
    );
});
