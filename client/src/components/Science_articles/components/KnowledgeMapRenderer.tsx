import { useRef, useEffect, useCallback } from 'react';
import { Graphics, Text, Container, TextStyle } from 'pixi.js';
import type { ActionNode as ActionNodeData, ActionEdge } from '../hooks/useKnowledgeMapLoader';
import type { ViewportRef } from '../../Knowledge_map/Viewport';

interface KnowledgeMapRendererProps {
  nodes: ActionNodeData[];
  edges: ActionEdge[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  viewportRef: React.RefObject<ViewportRef>;
}

const NODE_W = 160;
const NODE_H = 60;
const RADIUS = 8;
const PADDING = 8; // text padding inside node

const ACTION_COLORS: Record<string, number> = {
  result:    0xFF5722,
  mechanism: 0x9C27B0,
  action:    0x2196F3,
};

// LOD thresholds (viewport scale)
const LOD_FULL  = 0.35;  // rects + text labels
const LOD_NODES = 0.12;  // rects, no labels, dim edges
// below LOD_NODES: dots only, no edges

// Arrow head size in screen pixels (independent of zoom)
const ARROW_PX = 10;

// Line width in screen pixels
const LINE_PX = 2;

function makeTextStyle(wordWrapWidth: number): TextStyle {
  return new TextStyle({
    fontSize: 11,
    fill: 0xffffff,
    fontWeight: 'bold',
    wordWrap: true,
    wordWrapWidth,
    align: 'center',
    lineHeight: 14,
    trim: true,
  });
}

export function KnowledgeMapRenderer({
  nodes,
  edges,
  selectedNodeId,
  onNodeClick,
  viewportRef,
}: KnowledgeMapRendererProps) {
  const edgesGfxRef  = useRef<Graphics | null>(null);
  const arrowsGfxRef = useRef<Graphics | null>(null);
  const nodesGfxRef  = useRef<Graphics | null>(null);
  const labelsRef    = useRef<Container | null>(null);
  const hitRef       = useRef<Container | null>(null);

  const nodesRef         = useRef(nodes);
  const edgesRef         = useRef(edges);
  const lastScaleRef     = useRef(-1);
  const lastSelectedRef  = useRef<string | null>(null);
  const lastNodeCountRef = useRef(0);
  nodesRef.current = nodes;
  edgesRef.current = edges;

  const nodeMapRef = useRef<Map<string, ActionNodeData>>(new Map());
  useEffect(() => {
    nodeMapRef.current = new Map(nodes.map(n => [n.id, n]));
  }, [nodes]);

  // ── Init Pixi layers ──────────────────────────────────────────────────────
  useEffect(() => {
    const vp = viewportRef.current;
    const container = vp?.containerRef;
    if (!container) return;

    const edgesGfx  = new Graphics();
    const arrowsGfx = new Graphics();
    const nodesGfx  = new Graphics();
    const labels    = new Container();
    const hit       = new Container();

    container.addChild(edgesGfx);
    container.addChild(arrowsGfx);
    container.addChild(nodesGfx);
    container.addChild(labels);
    container.addChild(hit);

    edgesGfxRef.current  = edgesGfx;
    arrowsGfxRef.current = arrowsGfx;
    nodesGfxRef.current  = nodesGfx;
    labelsRef.current    = labels;
    hitRef.current       = hit;

    return () => {
      edgesGfx.destroy();
      arrowsGfx.destroy();
      nodesGfx.destroy();
      labels.destroy({ children: true });
      hit.destroy({ children: true });
      edgesGfxRef.current  = null;
      arrowsGfxRef.current = null;
      nodesGfxRef.current  = null;
      labelsRef.current    = null;
      hitRef.current       = null;
    };
  }, [viewportRef]);

  // ── Draw edges + arrows ───────────────────────────────────────────────────
  const drawEdges = useCallback((scale: number) => {
    const gLines  = edgesGfxRef.current;
    const gArrows = arrowsGfxRef.current;
    if (!gLines || !gArrows) return;

    gLines.clear();
    gArrows.clear();

    if (scale < LOD_NODES) return;

    const nm        = nodeMapRef.current;
    const alpha     = scale < LOD_FULL ? 0.35 : 0.6;
    // World-space line width: LINE_PX screen pixels / scale
    const lw        = LINE_PX / scale;
    // World-space arrow size: ARROW_PX screen pixels / scale
    const arrowSize = ARROW_PX / scale;

    gLines.setStrokeStyle({ width: lw, color: 0x8a2be2, alpha, cap: 'round' });
    gLines.beginPath();

    for (const e of edgesRef.current) {
      const src = nm.get(e.source_id);
      const tgt = nm.get(e.target_id);
      if (!src || !tgt) continue;

      // Edge endpoints: right side of source, left side of target
      const x1 = src.x + NODE_W / 2;
      const y1 = src.y;
      const x2 = tgt.x - NODE_W / 2;
      const y2 = tgt.y;

      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len < 1) continue;

      const nx = dx / len;
      const ny = dy / len;

      // Line ends slightly before arrowhead base
      const lineEndX = x2 - nx * arrowSize;
      const lineEndY = y2 - ny * arrowSize;

      gLines.moveTo(x1, y1);
      gLines.lineTo(lineEndX, lineEndY);

      // Arrow triangle: tip at (x2,y2), base perpendicular
      const perpX = -ny * arrowSize * 0.5;
      const perpY =  nx * arrowSize * 0.5;

      gArrows.poly([
        x2, y2,                                       // tip
        lineEndX + perpX, lineEndY + perpY,           // base left
        lineEndX - perpX, lineEndY - perpY,           // base right
      ]);
      gArrows.fill({ color: 0x8a2be2, alpha });
    }

    gLines.stroke();
  }, []);

  // ── Draw nodes ────────────────────────────────────────────────────────────
  const drawNodes = useCallback((scale: number, selected: string | null) => {
    const nodesGfx = nodesGfxRef.current;
    const labels   = labelsRef.current;
    const hit      = hitRef.current;
    if (!nodesGfx || !labels || !hit) return;

    const ns  = nodesRef.current;
    const lod = scale >= LOD_FULL ? 'full' : scale >= LOD_NODES ? 'nodes' : 'dots';

    nodesGfx.clear();

    if (lod === 'dots') {
      const r = Math.max(2, 3 / scale);
      for (const n of ns) {
        const color = ACTION_COLORS[n.action_class] ?? ACTION_COLORS.action;
        nodesGfx.circle(n.x, n.y, r);
        nodesGfx.fill({ color, alpha: 0.9 });
      }
    } else {
      for (const n of ns) {
        const color = ACTION_COLORS[n.action_class] ?? ACTION_COLORS.action;
        const isSel = n.id === selected;

        nodesGfx.roundRect(n.x - NODE_W / 2, n.y - NODE_H / 2, NODE_W, NODE_H, RADIUS);
        nodesGfx.fill({ color, alpha: isSel ? 1.0 : 0.85 });

        if (isSel) {
          nodesGfx.roundRect(n.x - NODE_W / 2, n.y - NODE_H / 2, NODE_W, NODE_H, RADIUS);
          nodesGfx.stroke({ width: 2.5 / scale, color: 0xffffff, alpha: 0.95 });
        }
      }
    }

    // ── Text labels (full LOD only) ───────────────────────────────────────
    const old = labels.removeChildren();
    for (const c of old) c.destroy();

    if (lod === 'full') {
      const wrapWidth = NODE_W - PADDING * 2;
      const style = makeTextStyle(wrapWidth);
      const maxH  = NODE_H - PADDING * 2;

      for (const n of ns) {
        const raw = n.verb_text
          ? `${n.verb_text}${n.object ? ' ' + n.object : ''}`
          : n.content;

        const t = new Text({ text: raw, style });

        // Scale down if text overflows node height
        if (t.height > maxH) {
          t.scale.set(maxH / t.height);
        }

        t.anchor.set(0.5, 0.5);
        t.x = n.x;
        t.y = n.y;
        labels.addChild(t);
      }
    }

    // ── Hit zones (rebuild only on node set change) ───────────────────────
    if (lastNodeCountRef.current !== ns.length) {
      const oldHit = hit.removeChildren();
      for (const c of oldHit) c.destroy();

      for (const n of ns) {
        const z = new Graphics();
        z.rect(-NODE_W / 2, -NODE_H / 2, NODE_W, NODE_H);
        z.fill({ color: 0x000000, alpha: 0.001 });
        z.x = n.x;
        z.y = n.y;
        z.eventMode = 'static';
        z.cursor = 'pointer';
        const nId = n.id;
        z.onpointerdown = () => onNodeClick(nId);
        hit.addChild(z);
      }
      lastNodeCountRef.current = ns.length;
    }
  }, [onNodeClick]);

  // ── Master redraw ─────────────────────────────────────────────────────────
  const redraw = useCallback((scale: number, selected: string | null) => {
    drawEdges(scale);
    drawNodes(scale, selected);
    lastScaleRef.current    = scale;
    lastSelectedRef.current = selected;
  }, [drawEdges, drawNodes]);

  // ── Redraw on data change ─────────────────────────────────────────────────
  useEffect(() => {
    if (!edgesGfxRef.current) return;
    const scale = viewportRef.current?.getScale?.() ?? 1;
    redraw(scale, selectedNodeId);
  }, [nodes, edges, selectedNodeId, redraw, viewportRef]);

  // ── LOD on viewport move/zoom ─────────────────────────────────────────────
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp?.on) return;

    const onMoved = () => {
      const scale = vp.getScale?.() ?? 1;
      const prev  = lastScaleRef.current;

      const lodOf = (s: number) => s >= LOD_FULL ? 2 : s >= LOD_NODES ? 1 : 0;
      const sameLod      = lodOf(prev) === lodOf(scale);
      const sameSelected = lastSelectedRef.current === selectedNodeId;

      if (!sameLod || !sameSelected) {
        redraw(scale, selectedNodeId);
      } else {
        // Same LOD bucket — redraw edges only to update line width with zoom
        drawEdges(scale);
        lastScaleRef.current = scale;
      }
    };

    vp.on('moved', onMoved);
    vp.on('zoomed', onMoved);
    return () => {
      vp.off?.('moved', onMoved);
      vp.off?.('zoomed', onMoved);
    };
  }, [viewportRef, selectedNodeId, redraw, drawEdges]);

  return null;
}
