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

// Badge and edge label sizes in screen pixels
const BADGE_R_PX   = 9;   // radius of doc_count badge circle
const EDGE_LABEL_W = 20;  // half-width of edge count label background

// Resolution multiplier for text textures — higher = sharper at zoom, more GPU memory.
// 4× covers up to 4× zoom before blurring; matches typical max useful zoom level.
const TEXT_RESOLUTION = 4;

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

// ── Viewport culling ──────────────────────────────────────────────────────────
// Returns the set of node IDs that are within the viewport + 1-screen prefetch margin.
// O(N) per call — at N=15,000 this is <1ms (simple arithmetic comparisons).
function computeVisibleSet(nodes: ActionNodeData[], vp: ViewportRef): Set<string> {
  const bounds = vp.getWorldBounds?.();
  if (!bounds) return new Set(nodes.map(n => n.id)); // fallback: show all

  const screenSize = vp.getScreenSize?.();
  // getScale() is a getter that reads containerRef.current.scale.x — always fresh
  const scale = vp.getScale?.() ?? 1;
  const marginX = (screenSize?.width  ?? 800) / scale;  // 1 screen width in world units
  const marginY = (screenSize?.height ?? 600) / scale;  // 1 screen height in world units

  const cl = bounds.left   - marginX;
  const ct = bounds.top    - marginY;
  const cr = bounds.right  + marginX;
  const cb = bounds.bottom + marginY;

  const vis = new Set<string>();
  for (const n of nodes) {
    if (
      n.x + NODE_W / 2 >= cl &&
      n.x - NODE_W / 2 <= cr &&
      n.y + NODE_H / 2 >= ct &&
      n.y - NODE_H / 2 <= cb
    ) vis.add(n.id);
  }
  return vis;
}

export function KnowledgeMapRenderer({
  nodes,
  edges,
  selectedNodeId,
  onNodeClick,
  viewportRef,
}: KnowledgeMapRendererProps) {
  const edgesGfxRef     = useRef<Graphics | null>(null);
  const arrowsGfxRef    = useRef<Graphics | null>(null);
  const nodesGfxRef     = useRef<Graphics | null>(null);
  const labelsRef       = useRef<Container | null>(null);
  const hitRef          = useRef<Container | null>(null);
  const badgesGfxRef    = useRef<Graphics | null>(null);  // doc_count circles on nodes
  const badgeLabelsRef  = useRef<Container | null>(null); // doc_count text on nodes
  const edgeLabelsRef   = useRef<Container | null>(null); // edge count labels

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

  // Viewport culling refs — updated on every redraw
  const visibleNodeIdsRef = useRef<Set<string>>(new Set());
  const lastVisibleSizeRef = useRef(0);

  // Text label cache — keyed by nodeId, avoids recreating Text objects on every pan
  const labelCacheRef = useRef<Map<string, Text>>(new Map());
  // Track LOD to flush cache on LOD change
  const lastLodRef = useRef<'full' | 'nodes' | 'dots'>('full');

  // Badge and edge label caches — keyed by node/edge id
  const badgeLabelCacheRef = useRef<Map<string, Text>>(new Map());
  const edgeLabelCacheRef  = useRef<Map<string, Text>>(new Map());

  // ── Init Pixi layers ──────────────────────────────────────────────────────
  useEffect(() => {
    const vp = viewportRef.current;
    const container = vp?.containerRef;
    if (!container) return;

    const edgesGfx    = new Graphics();
    const arrowsGfx   = new Graphics();
    const nodesGfx    = new Graphics();
    const labels      = new Container();
    const hit         = new Container();
    const badgesGfx   = new Graphics();
    const badgeLabels = new Container();
    const edgeLabels  = new Container();

    container.addChild(edgesGfx);
    container.addChild(arrowsGfx);
    container.addChild(nodesGfx);
    container.addChild(labels);
    container.addChild(badgesGfx);
    container.addChild(badgeLabels);
    container.addChild(edgeLabels);
    container.addChild(hit);

    edgesGfxRef.current    = edgesGfx;
    arrowsGfxRef.current   = arrowsGfx;
    nodesGfxRef.current    = nodesGfx;
    labelsRef.current      = labels;
    hitRef.current         = hit;
    badgesGfxRef.current   = badgesGfx;
    badgeLabelsRef.current = badgeLabels;
    edgeLabelsRef.current  = edgeLabels;

    return () => {
      edgesGfx.destroy();
      arrowsGfx.destroy();
      nodesGfx.destroy();
      labels.destroy({ children: true });
      hit.destroy({ children: true });
      badgesGfx.destroy();
      badgeLabels.destroy({ children: true });
      edgeLabels.destroy({ children: true });
      edgesGfxRef.current    = null;
      arrowsGfxRef.current   = null;
      nodesGfxRef.current    = null;
      labelsRef.current      = null;
      hitRef.current         = null;
      badgesGfxRef.current   = null;
      badgeLabelsRef.current = null;
      edgeLabelsRef.current  = null;
      labelCacheRef.current.clear();
      badgeLabelCacheRef.current.clear();
      edgeLabelCacheRef.current.clear();
    };
  }, [viewportRef]);

  // ── Draw edges + arrows ───────────────────────────────────────────────────
  // O(E) iterations, O(V/N * E) actual draw calls (culled by visible set)
  const drawEdges = useCallback((scale: number) => {
    const gLines  = edgesGfxRef.current;
    const gArrows = arrowsGfxRef.current;
    if (!gLines || !gArrows) return;

    gLines.clear();
    gArrows.clear();

    if (scale < LOD_NODES) return;

    const nm  = nodeMapRef.current;
    const vis = visibleNodeIdsRef.current;
    // World-space line width: LINE_PX screen pixels / scale
    const lw        = LINE_PX / scale;
    // World-space arrow size: ARROW_PX screen pixels / scale
    const arrowSize = ARROW_PX / scale;

    gLines.setStrokeStyle({ width: lw, color: 0x8a2be2, alpha: 1.0, cap: 'round' });
    gLines.beginPath();

    for (const e of edgesRef.current) {
      // Cull edges where neither endpoint is in the visible+margin area — O(1) per edge
      if (!vis.has(e.source_id) && !vis.has(e.target_id)) continue;

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
      gArrows.fill({ color: 0x8a2be2, alpha: 1.0 });
    }

    gLines.stroke();
  }, []);

  // ── Draw edge count labels (centre of each visible edge) ─────────────────
  // Shows edge.count when > 1. Cleared and rebuilt on each redraw.
  const drawEdgeLabels = useCallback((scale: number) => {
    const container = edgeLabelsRef.current;
    if (!container) return;

    if (scale < LOD_FULL) {
      // Hide edge labels when zoomed out — too small to read
      container.removeChildren().forEach((c: any) => c.destroy());
      edgeLabelCacheRef.current.clear();
      return;
    }

    const nm  = nodeMapRef.current;
    const vis = visibleNodeIdsRef.current;
    const edges = edgesRef.current;

    const style = new TextStyle({ fontSize: 9, fill: 0x555555, fontWeight: 'bold' });

    // Determine which edges are currently needed
    const neededKeys = new Set<string>();
    for (const e of edges) {
      if (e.count <= 1) continue;
      if (!vis.has(e.source_id) && !vis.has(e.target_id)) continue;
      neededKeys.add(e.id);
    }

    // Remove labels that are no longer needed
    const cache = edgeLabelCacheRef.current;
    for (const [id, t] of cache) {
      if (!neededKeys.has(id)) {
        t.destroy();
        cache.delete(id);
        container.removeChild(t);
      }
    }

    // Add or update labels for visible edges
    for (const e of edges) {
      if (e.count <= 1) continue;
      if (!vis.has(e.source_id) && !vis.has(e.target_id)) continue;

      const src = nm.get(e.source_id);
      const tgt = nm.get(e.target_id);
      if (!src || !tgt) continue;

      const mx = (src.x + NODE_W / 2 + tgt.x - NODE_W / 2) / 2;
      const my = (src.y + tgt.y) / 2;

      let t = cache.get(e.id);
      if (!t) {
        t = new Text({ text: String(e.count), style, resolution: TEXT_RESOLUTION });
        t.anchor.set(0.5, 0.5);
        container.addChild(t);
        cache.set(e.id, t);
      }
      t.scale.set(1 / scale);  // keep label size constant in screen pixels
      t.x = mx;
      t.y = my;
    }
  }, []);

  // ── Draw doc_count badges on nodes ────────────────────────────────────────
  // Badge: white circle in top-right corner with doc_count number (only when > 1).
  const drawBadges = useCallback((scale: number) => {
    const gfx       = badgesGfxRef.current;
    const container = badgeLabelsRef.current;
    if (!gfx || !container) return;

    gfx.clear();

    if (scale < LOD_NODES) {
      container.removeChildren().forEach((c: any) => c.destroy());
      badgeLabelCacheRef.current.clear();
      return;
    }

    const ns  = nodesRef.current;
    const vis = visibleNodeIdsRef.current;

    const r = BADGE_R_PX / scale;
    // Fixed style — scale is handled by world-space r and position
    const style = new TextStyle({ fontSize: 9, fill: 0x333333, fontWeight: 'bold' });

    const neededIds = new Set<string>();
    for (const n of ns) {
      if (n.doc_count <= 1) continue;
      if (!vis.has(n.id)) continue;
      neededIds.add(n.id);
    }

    // Remove stale badge labels
    const cache = badgeLabelCacheRef.current;
    for (const [id, t] of cache) {
      if (!neededIds.has(id)) {
        t.destroy();
        cache.delete(id);
        container.removeChild(t);
      }
    }

    for (const n of ns) {
      if (n.doc_count <= 1) continue;
      if (!vis.has(n.id)) continue;

      const bx = n.x + NODE_W / 2 - r;
      const by = n.y - NODE_H / 2 + r;

      // White circle background
      gfx.circle(bx, by, r);
      gfx.fill({ color: 0xffffff, alpha: 0.92 });
      gfx.circle(bx, by, r);
      gfx.stroke({ width: 0.8 / scale, color: 0xaaaaaa });

      // Number label (cached per node id)
      let t = cache.get(n.id);
      if (!t) {
        t = new Text({ text: String(n.doc_count), style, resolution: TEXT_RESOLUTION });
        t.anchor.set(0.5, 0.5);
        t.scale.set(1 / scale);  // keep label size constant in screen pixels
        container.addChild(t);
        cache.set(n.id, t);
      } else {
        t.scale.set(1 / scale);
      }
      t.x = bx;
      t.y = by;
    }
  }, []);

  // ── Draw nodes ────────────────────────────────────────────────────────────
  // O(V) draw calls where V = visible nodes in viewport + 1-screen margin
  const drawNodes = useCallback((scale: number, selected: string | null) => {
    const nodesGfx = nodesGfxRef.current;
    const labels   = labelsRef.current;
    const hit      = hitRef.current;
    if (!nodesGfx || !labels || !hit) return;

    const ns  = nodesRef.current;
    const vis = visibleNodeIdsRef.current;
    const lod = scale >= LOD_FULL ? 'full' : scale >= LOD_NODES ? 'nodes' : 'dots';

    // O(V): only process nodes within viewport + prefetch margin
    const visibleNodes = ns.filter(n => vis.has(n.id));

    nodesGfx.clear();

    if (lod === 'dots') {
      const r = Math.max(2, 3 / scale);
      for (const n of visibleNodes) {
        const color = ACTION_COLORS[n.action_class] ?? ACTION_COLORS.action;
        nodesGfx.circle(n.x, n.y, r);
        nodesGfx.fill({ color, alpha: 1.0 });
      }
    } else {
      for (const n of visibleNodes) {
        const color = ACTION_COLORS[n.action_class] ?? ACTION_COLORS.action;
        const isSel = n.id === selected;

        nodesGfx.roundRect(n.x - NODE_W / 2, n.y - NODE_H / 2, NODE_W, NODE_H, RADIUS);
        nodesGfx.fill({ color, alpha: 1.0 });

        if (isSel) {
          nodesGfx.roundRect(n.x - NODE_W / 2, n.y - NODE_H / 2, NODE_W, NODE_H, RADIUS);
          nodesGfx.stroke({ width: 2.5 / scale, color: 0xffffff, alpha: 0.95 });
        }
      }
    }

    // ── Text labels (full LOD only) ───────────────────────────────────────
    // Cache Text objects by nodeId — O(V_new) creates, O(V_old - V_new) destroys per pan.
    // On LOD change flush entire cache.
    const lodChanged = lod !== lastLodRef.current;
    lastLodRef.current = lod;

    if (lod !== 'full') {
      // Clear labels container and destroy all cached texts
      if (lodChanged) {
        labels.removeChildren();
        for (const t of labelCacheRef.current.values()) t.destroy();
        labelCacheRef.current.clear();
      }
    } else {
      if (lodChanged) {
        // Flush cache on transition into full LOD
        labels.removeChildren();
        for (const t of labelCacheRef.current.values()) t.destroy();
        labelCacheRef.current.clear();
      }

      const wrapWidth = NODE_W - PADDING * 2;
      const style     = makeTextStyle(wrapWidth);
      const maxH      = NODE_H - PADDING * 2;
      const cache     = labelCacheRef.current;
      const visSet    = new Set(visibleNodes.map(n => n.id));

      // Destroy labels that scrolled out of view
      for (const [id, t] of cache) {
        if (!visSet.has(id)) {
          t.destroy();
          cache.delete(id);
          labels.removeChild(t);
        }
      }

      // Create labels for newly visible nodes
      for (const n of visibleNodes) {
        if (cache.has(n.id)) continue;

        const raw = n.verb_text
          ? `${n.verb_text}${n.object ? ' ' + n.object : ''}`
          : n.content;

        const t = new Text({ text: raw, style, resolution: TEXT_RESOLUTION });

        if (t.height > maxH) t.scale.set(maxH / t.height);

        t.anchor.set(0.5, 0.5);
        t.x = n.x;
        t.y = n.y;
        labels.addChild(t);
        cache.set(n.id, t);
      }
    }

    // ── Hit zones — rebuild when node count OR visible set size changes ────
    const visChanged = vis.size !== lastVisibleSizeRef.current;
    if (lastNodeCountRef.current !== ns.length || visChanged) {
      const oldHit = hit.removeChildren();
      for (const c of oldHit) c.destroy();

      for (const n of visibleNodes) {
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
      lastVisibleSizeRef.current = vis.size;
    }
  }, [onNodeClick]);

  // ── Master redraw ─────────────────────────────────────────────────────────
  const redraw = useCallback((scale: number, selected: string | null) => {
    // Update visible set — O(N) pass, then all drawing is O(V)
    const vp = viewportRef.current;
    if (vp) {
      visibleNodeIdsRef.current = computeVisibleSet(nodesRef.current, vp);
    }

    drawEdges(scale);
    drawEdgeLabels(scale);
    drawNodes(scale, selected);
    drawBadges(scale);
    lastScaleRef.current    = scale;
    lastSelectedRef.current = selected;
  }, [drawEdges, drawEdgeLabels, drawNodes, drawBadges, viewportRef]);

  // ── Redraw on data change ─────────────────────────────────────────────────
  useEffect(() => {
    if (!edgesGfxRef.current) return;
    const vp = viewportRef.current;
    const scale = vp?.getScale?.() ?? vp?.scale ?? 1;
    redraw(scale, selectedNodeId);
  }, [nodes, edges, selectedNodeId, redraw, viewportRef]);

  // ── LOD on viewport move/zoom ─────────────────────────────────────────────
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp?.on) return;

    // Always do a full redraw on move/zoom — culling makes drawNodes O(V) so it's cheap.
    // The old "same LOD → edges only" optimization is no longer needed.
    const onMoved = () => {
      // getScale() reads containerRef.current.scale.x — always fresh, unlike vp.scale (snapshot)
      const scale = vp.getScale?.() ?? 1;
      redraw(scale, selectedNodeId);
    };

    vp.on('moved', onMoved);
    vp.on('zoomed', onMoved);
    return () => {
      vp.off?.('moved', onMoved);
      vp.off?.('zoomed', onMoved);
    };
  }, [viewportRef, selectedNodeId, redraw]);

  return null;
}
