import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface SimulationNode {
    id: string;
    x: number;
    y: number;
    vx?: number;
    vy?: number;
}

export interface SimulationEdge {
    source_id: string;
    target_id: string;
}

export interface ForceSimulationConfig {
    iterations?: number;
    repulsionStrength?: number;
    linkDistance?: number;
    centerGravity?: number;
    damping?: number;
    initialSpread?: number;
    theta?: number;
    useBarnesHut?: boolean | 'auto';
}

const DEFAULT_CONFIG: Required<ForceSimulationConfig> = {
    iterations: 100,
    repulsionStrength: 400,
    linkDistance: 80,
    centerGravity: 0.1,
    damping: 0.9,
    initialSpread: 300,
    theta: 0.8,
    useBarnesHut: 'auto',
};

export function runForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config: ForceSimulationConfig = {},
): SimulationNode[] {
    const cfg = { ...DEFAULT_CONFIG, ...config };
    const positions = new Map<string, { x: number; y: number }>();
    
    for (const node of nodes) {
        const angle = Math.random() * 2 * Math.PI;
        const spread = cfg.initialSpread || 300;
        node.x = Math.cos(angle) * spread * Math.random();
        node.y = Math.sin(angle) * spread * Math.random();
        positions.set(node.id, { x: node.x, y: node.y });
    }

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const edgeList = edges
        .map(e => ({
            source: nodeMap.get(e.source_id),
            target: nodeMap.get(e.target_id),
        }))
        .filter(e => e.source && e.target);

    for (let i = 0; i < (cfg.iterations || 100); i++) {
        for (const node of nodes) {
            node.vx = (node.vx || 0) * cfg.damping;
            node.vy = (node.vy || 0) * cfg.damping;
        }

        for (const a of nodes) {
            for (const b of nodes) {
                if (a.id === b.id) continue;
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const force = (cfg.repulsionStrength || 400) / (dist * dist);
                const fx = (dx / dist) * force;
                const fy = (dy / dist) * force;
                (a as any).vx = (a as any).vx || 0 - fx;
                (a as any).vy = (a as any).vy || 0 - fy;
            }
        }

        for (const edge of edgeList) {
            if (!edge.source || !edge.target) continue;
            const dx = edge.target.x - edge.source.x;
            const dy = edge.target.y - edge.source.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = (dist - (cfg.linkDistance || 80)) * 0.1;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            if (edge.source) {
                (edge.source as any).vx = (edge.source as any).vx || 0 + fx;
                (edge.source as any).vy = (edge.source as any).vy || 0 + fy;
            }
            if (edge.target) {
                (edge.target as any).vx = (edge.target as any).vx || 0 - fx;
                (edge.target as any).vy = (edge.target as any).vy || 0 - fy;
            }
        }

        const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length;
        const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length;
        for (const node of nodes) {
            node.x += (node.vx || 0) + (cx - node.x) * (cfg.centerGravity || 0.1);
            node.y += (node.vy || 0) + (cy - node.y) * (cfg.centerGravity || 0.1);
        }
    }

    return nodes;
}

export function useForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config?: ForceSimulationConfig,
): { positions: Map<string, { x: number; y: number }>; ready: boolean } {
    const [ready, setReady] = useState(false);
    const positionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
    const configRef = useRef(config);
    configRef.current = config;

    useEffect(() => {
        if (!nodes.length) {
            setReady(true);
            return;
        }

        const result = runForceSimulation([...nodes], [...edges], configRef.current);
        const posMap = new Map<string, { x: number; y: number }>();
        for (const n of result) {
            posMap.set(n.id, { x: n.x, y: n.y });
        }
        positionsRef.current = posMap;
        setReady(true);
    }, [nodes, edges, config?.iterations, config?.repulsionStrength, config?.linkDistance, config?.centerGravity, config?.damping]);

    return { positions: positionsRef.current, ready };
}