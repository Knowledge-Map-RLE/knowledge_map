import React, { useEffect, useRef, useState } from 'react';
import * as PIXI from 'pixi.js';
import './PatternVisualization.css';

interface GraphNode {
  id: number;
  label: string;
  type: 'token' | 'entity';
  pos?: string;
  entity_type?: string;
  confidence: number;
  sources: string[];
  sentence_idx: number;
}

interface GraphEdge {
  source: number;
  target: number;
  relation: string;
  confidence: number;
  sources?: string[];
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata: {
    total_nodes: number;
    total_edges: number;
    sentences: number;
  };
}

interface PatternVisualizationProps {
  graphData: GraphData | null;
}

interface LayoutNode {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  node: GraphNode;
}

const PatternVisualization: React.FC<PatternVisualizationProps> = ({ graphData }) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!canvasRef.current || !graphData) return;

    // Clean up previous instance
    if (appRef.current) {
      appRef.current.destroy(true, { children: true, texture: true, baseTexture: true });
      appRef.current = null;
    }

    setIsLoading(true);

    // Initialize Pixi application (PixiJS v8)
    const app = new PIXI.Application();

    app.init({
      width: canvasRef.current.clientWidth,
      height: 600,
      backgroundColor: 0xffffff,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    }).then(() => {
      if (canvasRef.current && appRef.current === null) {
        canvasRef.current.appendChild(app.canvas);
        appRef.current = app;

        // Build graph layout
        const layout = buildForceDirectedLayout(graphData);

        // Render graph
        renderGraph(app, graphData, layout);

        setIsLoading(false);
      }
    }).catch((error) => {
      console.error('Failed to initialize PixiJS application:', error);
      setIsLoading(false);
    });

    // Cleanup
    return () => {
      if (appRef.current) {
        appRef.current.destroy(true, { children: true, texture: true, baseTexture: true });
        appRef.current = null;
      }
    };
  }, [graphData]);

  const buildForceDirectedLayout = (data: GraphData): Map<number, LayoutNode> => {
    const width = canvasRef.current?.clientWidth || 1200;
    const height = 600;
    const nodes = new Map<number, LayoutNode>();

    // Initialize node positions randomly
    data.nodes.forEach(node => {
      nodes.set(node.id, {
        id: node.id,
        x: Math.random() * width,
        y: Math.random() * height,
        vx: 0,
        vy: 0,
        node,
      });
    });

    // Build adjacency map for edges
    const adjacency = new Map<number, number[]>();
    data.edges.forEach(edge => {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
      adjacency.get(edge.source)!.push(edge.target);
      adjacency.get(edge.target)!.push(edge.source);
    });

    // Force-directed layout simulation (simple version)
    const iterations = 100;
    const k = Math.sqrt((width * height) / data.nodes.length); // Optimal distance
    const c = 0.5; // Damping factor

    for (let iter = 0; iter < iterations; iter++) {
      // Repulsive forces between all nodes
      nodes.forEach((n1, id1) => {
        nodes.forEach((n2, id2) => {
          if (id1 !== id2) {
            const dx = n1.x - n2.x;
            const dy = n1.y - n2.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = (k * k) / dist;
            n1.vx += (dx / dist) * force;
            n1.vy += (dy / dist) * force;
          }
        });
      });

      // Attractive forces along edges
      data.edges.forEach(edge => {
        const source = nodes.get(edge.source);
        const target = nodes.get(edge.target);
        if (source && target) {
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist * dist) / k;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          source.vx += fx * 0.5;
          source.vy += fy * 0.5;
          target.vx -= fx * 0.5;
          target.vy -= fy * 0.5;
        }
      });

      // Update positions and apply damping
      nodes.forEach(node => {
        node.x += node.vx * c;
        node.y += node.vy * c;
        node.vx *= 0.8;
        node.vy *= 0.8;

        // Keep within bounds
        node.x = Math.max(50, Math.min(width - 50, node.x));
        node.y = Math.max(50, Math.min(height - 50, node.y));
      });
    }

    return nodes;
  };

  const renderGraph = (app: PIXI.Application, data: GraphData, layout: Map<number, LayoutNode>) => {
    const container = new PIXI.Container();
    app.stage.addChild(container);

    // Draw edges
    data.edges.forEach(edge => {
      const source = layout.get(edge.source);
      const target = layout.get(edge.target);
      if (!source || !target) return;

      const line = new PIXI.Graphics();
      line.lineStyle(2, 0xcccccc, edge.confidence);
      line.moveTo(source.x, source.y);
      line.lineTo(target.x, target.y);
      container.addChild(line);

      // Add relation label
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      const label = new PIXI.Text(edge.relation, {
        fontSize: 10,
        fill: 0x666666,
      });
      label.x = midX;
      label.y = midY;
      label.anchor.set(0.5);
      container.addChild(label);
    });

    // Draw nodes
    layout.forEach(({ x, y, node }) => {
      // Node circle
      const circle = new PIXI.Graphics();
      const color = node.type === 'entity' ? 0xff6b6b : 0x4ecdc4;
      circle.beginFill(color, 0.8);
      circle.drawCircle(0, 0, 20);
      circle.endFill();
      circle.x = x;
      circle.y = y;

      // Make interactive
      circle.interactive = true;
      circle.buttonMode = true;

      // Tooltip on hover
      circle.on('pointerover', () => {
        circle.scale.set(1.2);
        const tooltip = `${node.label}\nType: ${node.type}\nConfidence: ${node.confidence.toFixed(2)}\nSources: ${node.sources.join(', ')}`;
        console.log(tooltip);
      });

      circle.on('pointerout', () => {
        circle.scale.set(1);
      });

      container.addChild(circle);

      // Node label
      const label = new PIXI.Text(node.label, {
        fontSize: 12,
        fill: 0x000000,
        fontWeight: 'bold',
      });
      label.x = x;
      label.y = y + 25;
      label.anchor.set(0.5, 0);
      container.addChild(label);

      // Confidence indicator
      const conf = new PIXI.Text(`${(node.confidence * 100).toFixed(0)}%`, {
        fontSize: 9,
        fill: 0x666666,
      });
      conf.x = x;
      conf.y = y - 25;
      conf.anchor.set(0.5, 1);
      container.addChild(conf);
    });
  };

  if (!graphData) {
    return (
      <div className="pattern-visualization-empty">
        <p>Запустите Multi-Level анализ для визуализации графа связей</p>
      </div>
    );
  }

  return (
    <div className="pattern-visualization">
      <div className="pattern-visualization-header">
        <h3>📊 Граф лингвистических связей</h3>
        <div className="graph-stats">
          <span>Узлов: {graphData.metadata.total_nodes}</span>
          <span>Связей: {graphData.metadata.total_edges}</span>
          <span>Предложений: {graphData.metadata.sentences}</span>
        </div>
      </div>
      {isLoading && <div className="loading">Построение графа...</div>}
      <div ref={canvasRef} className="pattern-visualization-canvas" />
      <div className="pattern-visualization-legend">
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#4ecdc4' }}></div>
          <span>Токены (слова)</span>
        </div>
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#ff6b6b' }}></div>
          <span>Именованные сущности</span>
        </div>
      </div>
    </div>
  );
};

export default PatternVisualization;
