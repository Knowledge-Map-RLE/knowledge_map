/**
 * Shared компоненты для лингвистического графа.
 * Переиспользуются в GlobalLinguisticGraph и ArticleLinguisticGraph.
 */
import { useState, useEffect, useRef, useMemo } from 'react';
import { extend, useTick } from '@pixi/react';
import { Container, Graphics, Text, TextStyle } from 'pixi.js';
import { useViewportContainer } from '../../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../../widgets/KnowledgeMap';
import type { LinguisticGraphNode, LinguisticGraphEdge } from '../../../services/api';

extend({ Container, Graphics, Text });

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const ACTION_COLORS: Record<string, number> = {
    result: 0xFF5722,
    mechanism: 0x9C27B0,
    action: 0x2196F3,
};

export const ACTION_W = 525;   // 7 * 75
export const ACTION_H = 187.5; // 2.5 * 75
export const LU_RADIUS = 93.75; // 1.25 * 75

export const LOD_FULL = 0.35;
export const LOD_NODES = 0.12;

export const EDGE_COLORS: Record<string, number> = {
    LEADS_TO: 0x8a2be2,
    DEPENDS_ON: 0x4CAF50,
    PART_OF: 0xFF9800,
};

export const TEXT_RESOLUTION = 4;
export const SCALE_THROTTLE_MS = 100;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GraphNode {
    id: string;
    x: number;
    y: number;
    _nodeType: 'Action' | 'LexicalUnit';
    _data: LinguisticGraphNode;
}

export interface GraphEdge {
    source_id: string;
    target_id: string;
    _edgeType: string;
    _data: LinguisticGraphEdge;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function computeVisibleSet(
    nodes: Array<{ id: string; x: number; y: number; _nodeType: string }>,
    vp: ViewportRef | null,
): Set<string> {
    if (!vp) return new Set(nodes.map((n) => n.id));
    const bounds = vp.getWorldBounds?.();
    if (!bounds) return new Set(nodes.map((n) => n.id));

    const screenSize = vp.getScreenSize?.();
    const scale = vp.getScale?.() ?? 1;
    const marginX = (screenSize?.width ?? 800) / scale;
    const marginY = (screenSize?.height ?? 600) / scale;

    const cl = bounds.left - marginX;
    const ct = bounds.top - marginY;
    const cr = bounds.right + marginX;
    const cb = bounds.bottom + marginY;

    const vis = new Set<string>();
    for (const n of nodes) {
        const hw = n._nodeType === 'Action' ? ACTION_W / 2 : LU_RADIUS;
        const hh = n._nodeType === 'Action' ? ACTION_H / 2 : LU_RADIUS;
        if (n.x + hw >= cl && n.x - hw <= cr && n.y + hh >= ct && n.y - hh <= cb) {
            vis.add(n.id);
        }
    }
    return vis;
}

export function getLinguisticNodeLabel(node: GraphNode): string {
    if (node._nodeType === 'Action') {
        return node._data.verb_text || node._data.verb || node._data.full_phrase || '';
    }
    return node._data.text || node._data.lemma || '';
}

export function linkEdgeNodes(edges: GraphEdge[], nodeMap: Map<string, GraphNode>) {
    for (const edge of edges) {
        (edge as any)._sourceNode = nodeMap.get(edge.source_id);
        (edge as any)._targetNode = nodeMap.get(edge.target_id);
    }
}

// ---------------------------------------------------------------------------
// Edges layer
// ---------------------------------------------------------------------------

export function EdgesLayer({ edges, visibleIds, scale, lod }: {
    edges: GraphEdge[];
    visibleIds: Set<string>;
    scale: number;
    lod: 'full' | 'nodes' | 'dots';
}) {
    const containerRef = useViewportContainer();
    const gfxRef = useRef<Graphics | null>(null);
    const edgeIndexRef = useRef<Map<string, GraphEdge[]>>(new Map());

    useEffect(() => {
        const index = new Map<string, GraphEdge[]>();
        for (const edge of edges) {
            if (!index.has(edge.source_id)) index.set(edge.source_id, []);
            index.get(edge.source_id)!.push(edge);
            if (edge.source_id !== edge.target_id) {
                if (!index.has(edge.target_id)) index.set(edge.target_id, []);
                index.get(edge.target_id)!.push(edge);
            }
        }
        edgeIndexRef.current = index;
    }, [edges]);

    const visibleEdges = useMemo(() => {
        const seen = new Set<string>();
        const result: GraphEdge[] = [];
        for (const nodeId of visibleIds) {
            const edgesForNode = edgeIndexRef.current.get(nodeId);
            if (edgesForNode) {
                for (const edge of edgesForNode) {
                    const key = `${edge.source_id}-${edge.target_id}`;
                    if (!seen.has(key)) { seen.add(key); result.push(edge); }
                }
            }
        }
        return result;
    }, [visibleIds, edges.length]);

    useEffect(() => {
        const gfx = new Graphics();
        const cnt = containerRef.current;
        if (cnt) cnt.addChild(gfx);
        gfxRef.current = gfx;
        return () => gfx.destroy();
    }, [containerRef]);

    useEffect(() => {
        const gfx = gfxRef.current;
        if (!gfx) return;
        gfx.clear();
        if (lod === 'dots') return;

        const lineWidth = lod === 'full' ? 1.5 / scale : 0.8 / scale;
        const alpha = lod === 'full' ? 0.7 : 0.3;

        for (const edge of visibleEdges) {
            const src = (edge as any)._sourceNode;
            const tgt = (edge as any)._targetNode;
            if (!src || !tgt) continue;
            if (!visibleIds.has(edge.source_id) && !visibleIds.has(edge.target_id)) continue;

            const color = EDGE_COLORS[edge._edgeType] ?? 0x888888;
            if (edge._edgeType === 'PART_OF' && lod === 'full') {
                drawDashedLine(gfx, src.x, src.y, tgt.x, tgt.y, color, lineWidth, alpha, 6 / scale);
            } else {
                gfx.moveTo(src.x, src.y);
                gfx.lineTo(tgt.x, tgt.y);
                gfx.stroke({ width: lineWidth, color, alpha });
            }
        }
    }, [visibleEdges, visibleIds, scale, lod]);

    return null;
}

function drawDashedLine(
    gfx: Graphics, x1: number, y1: number, x2: number, y2: number,
    color: number, width: number, alpha: number, dashLen: number,
) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1) return;
    const nx = dx / len;
    const ny = dy / len;
    let t = 0;
    let draw = true;
    while (t < len) {
        const segEnd = Math.min(t + dashLen, len);
        if (draw) {
            gfx.moveTo(x1 + nx * t, y1 + ny * t);
            gfx.lineTo(x1 + nx * segEnd, y1 + ny * segEnd);
            gfx.stroke({ width, color, alpha });
        }
        t = segEnd;
        draw = !draw;
    }
}

// ---------------------------------------------------------------------------
// Nodes layer
// ---------------------------------------------------------------------------

export function NodesLayer({ nodes, visibleIds, scale, lod }: {
    nodes: GraphNode[];
    visibleIds: Set<string>;
    scale: number;
    lod: 'full' | 'nodes' | 'dots';
}) {
    const containerRef = useViewportContainer();
    const nodesGfxRef = useRef<Graphics | null>(null);
    const labelsRef = useRef<Container | null>(null);
    const labelCacheRef = useRef<Map<string, Text>>(new Map());
    const lastLodRef = useRef<string>('full');

    useEffect(() => {
        const nodesGfx = new Graphics();
        const labels = new Container();
        const cnt = containerRef.current;
        if (cnt) {
            cnt.addChild(nodesGfx);
            cnt.addChild(labels);
        }
        nodesGfxRef.current = nodesGfx;
        labelsRef.current = labels;
        return () => {
            try {
                nodesGfx.destroy();
                labels.destroy({ children: true, baseTexture: true });
            } catch {
                // Ignore cleanup errors
            }
            try {
                labelCacheRef.current?.clear();
            } catch {
                // Ignore cache clear errors
            }
        };
    }, [containerRef]);

    useEffect(() => {
        const gfx = nodesGfxRef.current;
        const labels = labelsRef.current;
        if (!gfx || !labels) return;

        gfx.clear();
        const lodChanged = lod !== lastLodRef.current;
        lastLodRef.current = lod;

        if (lod === 'dots') {
            const r = Math.max(2, 4 / scale);
            for (const node of nodes) {
                if (!visibleIds.has(node.id)) continue;
                const color = node._nodeType === 'Action'
                    ? (ACTION_COLORS[node._data.action_class ?? 'action'] ?? ACTION_COLORS.action)
                    : 0x607D8B;
                gfx.circle(node.x, node.y, r);
                gfx.fill({ color, alpha: 1.0 });
            }
            if (lodChanged) {
                labels.removeChildren().forEach((c: any) => c.destroy());
                labelCacheRef.current.clear();
            }
            return;
        }

        for (const node of nodes) {
            if (!visibleIds.has(node.id)) continue;
            const color = node._nodeType === 'Action'
                ? (ACTION_COLORS[node._data.action_class ?? 'action'] ?? ACTION_COLORS.action)
                : 0x607D8B;

            if (node._nodeType === 'Action') {
                gfx.roundRect(node.x - ACTION_W / 2, node.y - ACTION_H / 2, ACTION_W, ACTION_H, 8);
                gfx.fill({ color, alpha: 1.0 });
            } else {
                gfx.circle(node.x, node.y, LU_RADIUS);
                gfx.fill({ color, alpha: 0.85 });
            }
        }

        if (lod !== 'full') {
            if (lodChanged) {
                labels.removeChildren().forEach((c: any) => c.destroy());
                labelCacheRef.current.clear();
            }
            return;
        }

        if (lodChanged) {
            labels.removeChildren().forEach((c: any) => c.destroy());
            labelCacheRef.current.clear();
        }

        // Чёткий текст: рендер в крупном размере, scale down
        const desiredWorldFontSize = 56.25;  // 0.75 * 75
        const renderFontSize = 12;
        const textScale = desiredWorldFontSize / renderFontSize;
        const labelMaxChars = 8;

        for (const node of nodes) {
            if (!visibleIds.has(node.id)) continue;

            let labelText = getLinguisticNodeLabel(node);
            if (!labelText) continue;
            if (labelText.length > labelMaxChars) {
                labelText = labelText.substring(0, labelMaxChars) + '…';
            }

            let t = labelCacheRef.current.get(node.id);
            if (!t) {
                const textStyle = new TextStyle({
                    fontSize: renderFontSize,
                    fill: 0xffffff,
                    fontWeight: 'bold',
                    align: 'center',
                    lineHeight: renderFontSize * 1.4,
                    trim: true,
                    padding: 0,
                });
                t = new Text({ text: labelText, style: textStyle, resolution: 2 });
                t.anchor.set(0.5, 0.5);
                t.scale.set(textScale);
                labels.addChild(t);
                labelCacheRef.current.set(node.id, t);
                t.x = node.x;
                t.y = node.y;
            } else {
                if (t.text !== labelText) t.text = labelText;
            }
            t.x = node.x;
            t.y = node.y;
        }
    }, [nodes, visibleIds, lod]);

    return null;
}

// ---------------------------------------------------------------------------
// Scale tracker
// ---------------------------------------------------------------------------

export function ScaleTracker({ scale, setScale, viewportRef }: {
    scale: number;
    setScale: (s: number) => void;
    viewportRef: React.RefObject<ViewportRef | null>;
}) {
    const lastUpdateRef = useRef<number>(0);

    useTick(() => {
        if (viewportRef.current) {
            const now = performance.now();
            if (now - lastUpdateRef.current < SCALE_THROTTLE_MS) return;
            const s = viewportRef.current.getScale?.() ?? 1;
            if (Math.abs(s - scale) > 0.001) {
                lastUpdateRef.current = now;
                setScale(s);
            }
        }
    });
    return null;
}
