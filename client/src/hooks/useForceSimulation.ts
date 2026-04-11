/**
 * useForceSimulation — force-directed layout с оптимизацией Barnes-Hut.
 *
 * Выполняет полную симуляцию в синхронном цикле и возвращает
 * финальные координаты {x, y} для каждого узла.
 *
 * Алгоритм аналогичен d3-force:
 *  - Repulsion (charge) между всеми парами узлов (Barnes-Hut: O(n log n))
 *  - Attraction (link) по рёбрам
 *  - Center gravity к центру холста
 *
 * Без промежуточной визуализации — сразу финальный результат.
 */

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
    /** Количество итераций (по умолчанию 300) */
    iterations?: number;
    /** Сила отталкивания (по умолчанию -30) */
    repulsionStrength?: number;
    /** Длина пружины рёбер (по умолчанию 120) */
    linkDistance?: number;
    /** Сила притяжения к центру (по умолчанию 0.01) */
    centerGravity?: number;
    /** Коэффициент затухания скорости (по умолчанию 0.6) */
    damping?: number;
    /** Начальная случайная область разброса (по умолчанию 200) */
    initialSpread?: number;
    /** Barnes-Hut theta параметр (по умолчанию 0.5). < 1 = точнее, > 1 = быстрее */
    theta?: number;
    /** Использовать ли Barnes-Hut (по умолчанию true для n > 500) */
    useBarnesHut?: boolean | 'auto';
}

const DEFAULT_CONFIG: Required<ForceSimulationConfig> = {
    iterations: 300,
    repulsionStrength: -30,
    linkDistance: 120,
    centerGravity: 0.01,
    damping: 0.6,
    initialSpread: 200,
    theta: 0.5,
    useBarnesHut: 'auto',
};

// ---------------------------------------------------------------------------
// Barnes-Hut Quadtree
// ---------------------------------------------------------------------------

interface BHNode {
    x: number;
    y: number;
    mass: number;
    index: number; // -1 если internal node
}

interface QuadTreeNode {
    center: BHNode | null;
    children: [QuadTreeNode | null, QuadTreeNode | null, QuadTreeNode | null, QuadTreeNode | null];
    mass: number;
    massCenterX: number;
    massCenterY: number;
    left: number;
    right: number;
    top: number;
    bottom: number;
}

function createQuadNode(left: number, right: number, top: number, bottom: number): QuadTreeNode {
    return {
        center: null,
        children: [null, null, null, null],
        mass: 0,
        massCenterX: 0,
        massCenterY: 0,
        left,
        right,
        top,
        bottom,
    };
}

function insert(node: QuadTreeNode, point: BHNode): void {
    // Leaf node
    if (node.center === null && node.children.every((c) => c === null)) {
        node.center = point;
        node.mass = point.mass;
        node.massCenterX = point.x;
        node.massCenterY = point.y;
        return;
    }

    // Subdivide if necessary
    if (node.center !== null) {
        const temp = node.center;
        node.center = null;
        const midX = (node.left + node.right) / 2;
        const midY = (node.top + node.bottom) / 2;
        
        // Insert the existing center point into appropriate child
        const quadrant = getQuadrant(temp.x, temp.y, midX, midY);
        node.children[quadrant] = createQuadNode(
            quadrant % 2 === 0 ? node.left : midX,
            quadrant % 2 === 0 ? midX : node.right,
            quadrant < 2 ? node.top : midY,
            quadrant < 2 ? midY : node.bottom,
        );
        insertIntoChild(node.children[quadrant]!, temp);
    }

    // Insert the new point
    insertIntoChild(node, point);
}

function insertIntoChild(node: QuadTreeNode, point: BHNode): void {
    const midX = (node.left + node.right) / 2;
    const midY = (node.top + node.bottom) / 2;
    const quadrant = getQuadrant(point.x, point.y, midX, midY);
    
    if (node.children[quadrant] === null) {
        node.children[quadrant] = createQuadNode(
            quadrant % 2 === 0 ? node.left : midX,
            quadrant % 2 === 0 ? midX : node.right,
            quadrant < 2 ? node.top : midY,
            quadrant < 2 ? midY : node.bottom,
        );
    }
    
    insert(node.children[quadrant]!, point);
    
    // Update mass center
    const totalMass = node.mass + point.mass;
    node.massCenterX = (node.mass * node.massCenterX + point.mass * point.x) / totalMass;
    node.massCenterY = (node.mass * node.massCenterY + point.mass * point.y) / totalMass;
    node.mass += point.mass;
}

function getQuadrant(x: number, y: number, midX: number, midY: number): number {
    if (x < midX) {
        return y < midY ? 0 : 2; // NW or SW
    } else {
        return y < midY ? 1 : 3; // NE or SE
    }
}

function calculateForce(node: QuadTreeNode, target: BHNode, theta: number, repulsionStrength: number, fx: { val: number }, fy: { val: number }): void {
    if (node.mass === 0) return;

    const dx = node.massCenterX - target.x;
    const dy = node.massCenterY - target.y;
    const distSq = dx * dx + dy * dy + 1; // +1 для стабильности
    const dist = Math.sqrt(distSq);

    // Check if we can approximate
    const size = node.right - node.left;
    if (node.center !== null || size / dist < theta) {
        // Use multipole approximation
        const force = repulsionStrength / distSq;
        fx.val += (dx / dist) * force;
        fy.val += (dy / dist) * force;
    } else {
        // Recurse into children
        for (const child of node.children) {
            if (child !== null) {
                calculateForce(child, target, theta, repulsionStrength, fx, fy);
            }
        }
    }
}

function buildBarnesHutTree(
    nodes: SimulationNode[],
): QuadTreeNode {
    // Find bounds
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of nodes) {
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
    }
    
    // Make square bounds
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const halfSize = Math.max(maxX - minX, maxY - minY) / 2 + 1;
    
    const root = createQuadNode(
        centerX - halfSize,
        centerX + halfSize,
        centerY - halfSize,
        centerY + halfSize,
    );
    
    for (let i = 0; i < nodes.length; i++) {
        insert(root, {
            x: nodes[i].x,
            y: nodes[i].y,
            mass: 1,
            index: i,
        });
    }
    
    return root;
}

// ---------------------------------------------------------------------------
// Simulation
// ---------------------------------------------------------------------------

/**
 * Запускает force-simulation синхронно и возвращает узлы с координатами.
 */
export function runForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config: ForceSimulationConfig = {},
): SimulationNode[] {
    const cfg: Required<ForceSimulationConfig> = { ...DEFAULT_CONFIG, ...config };

    if (nodes.length === 0) return [];

    const useBarnesHut = cfg.useBarnesHut === 'auto' 
        ? nodes.length > 500 
        : cfg.useBarnesHut;

    // Инициализация позиций — случайный разброс вокруг центра
    const centerX = 0;
    const centerY = 0;
    const simulatedNodes: SimulationNode[] = nodes.map((n) => ({
        ...n,
        x: centerX + (Math.random() - 0.5) * cfg.initialSpread,
        y: centerY + (Math.random() - 0.5) * cfg.initialSpread,
        vx: 0,
        vy: 0,
    }));

    const nodeIndex = new Map<string, number>();
    simulatedNodes.forEach((n, i) => nodeIndex.set(n.id, i));

    // Edge map: source -> targets[]
    const edgeList: Array<{ source: number; target: number }> = [];
    for (const e of edges) {
        const si = nodeIndex.get(e.source_id);
        const ti = nodeIndex.get(e.target_id);
        if (si !== undefined && ti !== undefined) {
            edgeList.push({ source: si, target: ti });
        }
    }

    const n = simulatedNodes.length;

    for (let iter = 0; iter < cfg.iterations; iter++) {
        // Температура — уменьшается с каждой итерацией
        const temperature = 1.0 - iter / cfg.iterations;

        // --- Repulsion (charge) ---
        if (useBarnesHut) {
            // Barnes-Hut оптимизация: O(n log n)
            const tree = buildBarnesHutTree(simulatedNodes);
            
            for (let i = 0; i < n; i++) {
                const node = simulatedNodes[i];
                const fx = { val: 0 };
                const fy = { val: 0 };
                calculateForce(tree, { x: node.x, y: node.y, mass: 1, index: i }, cfg.theta, cfg.repulsionStrength, fx, fy);
                node.vx = (node.vx ?? 0) + fx.val;
                node.vy = (node.vy ?? 0) + fy.val;
            }
        } else {
            // Naive O(n^2) для маленьких графов
            for (let i = 0; i < n; i++) {
                const nodeA = simulatedNodes[i];
                for (let j = i + 1; j < n; j++) {
                    const nodeB = simulatedNodes[j];
                    let dx = nodeA.x - nodeB.x;
                    let dy = nodeA.y - nodeB.y;
                    let distSq = dx * dx + dy * dy;
                    if (distSq < 1) distSq = 1;

                    const dist = Math.sqrt(distSq);
                    const force = cfg.repulsionStrength / distSq;

                    const fx = (dx / dist) * force;
                    const fy = (dy / dist) * force;

                    nodeA.vx = (nodeA.vx ?? 0) + fx;
                    nodeA.vy = (nodeA.vy ?? 0) + fy;
                    nodeB.vx = (nodeB.vx ?? 0) - fx;
                    nodeB.vy = (nodeB.vy ?? 0) - fy;
                }
            }
        }

        // --- Attraction (link) по рёбрам ---
        for (const edge of edgeList) {
            const source = simulatedNodes[edge.source];
            const target = simulatedNodes[edge.target];
            let dx = target.x - source.x;
            let dy = target.y - source.y;
            let dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 1) dist = 1;

            const force = (dist - cfg.linkDistance) * 0.06;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            source.vx = (source.vx ?? 0) + fx;
            source.vy = (source.vy ?? 0) + fy;
            target.vx = (target.vx ?? 0) - fx;
            target.vy = (target.vy ?? 0) - fy;
        }

        // --- Center gravity ---
        for (const node of simulatedNodes) {
            node.vx = (node.vx ?? 0) + (centerX - node.x) * cfg.centerGravity;
            node.vy = (node.vy ?? 0) + (centerY - node.y) * cfg.centerGravity;
        }

        // --- Apply velocities with damping & temperature ---
        for (const node of simulatedNodes) {
            const vx = (node.vx ?? 0) * cfg.damping * temperature;
            const vy = (node.vy ?? 0) * cfg.damping * temperature;

            // Clamp velocity
            const maxV = 10;
            node.vx = Math.max(-maxV, Math.min(maxV, vx));
            node.vy = Math.max(-maxV, Math.min(maxV, vy));

            node.x += node.vx;
            node.y += node.vy;

            // Reset velocity
            node.vx = 0;
            node.vy = 0;
        }
    }

    // Центрируем результат вокруг (0, 0)
    let avgX = 0;
    let avgY = 0;
    for (const node of simulatedNodes) {
        avgX += node.x;
        avgY += node.y;
    }
    avgX /= n;
    avgY /= n;

    for (const node of simulatedNodes) {
        node.x -= avgX;
        node.y -= avgY;
    }

    return simulatedNodes;
}

/**
 * React-хук для использования force-симуляции.
 * Возвращает Map<node_id, {x, y}> и флаг готовности.
 */
export function useForceSimulation(
    nodes: SimulationNode[],
    edges: SimulationEdge[],
    config: ForceSimulationConfig = {},
): { positions: Map<string, { x: number; y: number }>; ready: boolean } {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const positions = new Map<string, { x: number; y: number }>();

    if (nodes.length > 0) {
        const simulated = runForceSimulation(nodes, edges, config);
        for (const node of simulated) {
            positions.set(node.id, { x: node.x, y: node.y });
        }
    }

    return { positions, ready: nodes.length > 0 };
}
