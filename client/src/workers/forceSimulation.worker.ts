/**
 * Web Worker для force-directed layout симуляции.
 * Выполняет вычисления в фоновом потоке, не блокируя UI.
 *
 * Vite worker: импортируется через `?worker`
 */

import { runForceSimulation } from '../hooks/useForceSimulation';
import type { SimulationNode, SimulationEdge } from '../hooks/useForceSimulation';

self.onmessage = (e: MessageEvent) => {
    const { nodes, edges, config } = e.data;
    
    try {
        const result = runForceSimulation(
            nodes as SimulationNode[],
            edges as SimulationEdge[],
            config || {},
        );
        
        self.postMessage({ 
            success: true, 
            nodes: result.map((n) => ({ id: n.id, x: n.x, y: n.y }))
        });
    } catch (error) {
        self.postMessage({ 
            success: false, 
            error: error instanceof Error ? error.message : String(error)
        });
    }
};

export {};
