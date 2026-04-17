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

export function runForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config: ForceSimulationConfig = {},
): SimulationNode[];

export function useForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config?: ForceSimulationConfig,
): { positions: Map<string, { x: number; y: number }>; ready: boolean };
