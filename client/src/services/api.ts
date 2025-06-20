/**
 * API клиент для взаимодействия с бэкендом
 */

const API_URL = 'http://localhost:8000';

export interface Block {
    id: string;
    content: string;
    x?: number;
    y?: number;
    level: number;
    layer?: number;
    sublevel_id: number;
}

export interface Link {
    id: string;
    source_id: string;
    target_id: string;
}

export interface Level {
    id: number;
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    color?: number;
    name?: string;
}

export interface Sublevel {
    id: number;
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    color?: number;
    block_ids: string[];
    level: number;
}

export interface LayoutStatistics {
    total_blocks: number;
    total_links: number;
    total_levels: number;
    total_sublevels: number;
    max_layer: number;
    total_width: number;
    total_height: number;
    processing_time_ms: number;
    is_acyclic: boolean;
    isolated_blocks: number;
}

export interface LayoutResponse {
    blocks: Block[];
    links: Link[];
    levels: Level[];
    sublevels: Sublevel[];
}

/**
 * Проверяет здоровье основного API
 */
export async function checkHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_URL}/health`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
            mode: 'cors',
            credentials: 'omit'
        });
        
        if (!response.ok) {
            console.error('Health check failed:', response.status, response.statusText);
            return false;
        }
        
        const data = await response.json();
        return data.status === 'ok';
    } catch (error) {
        console.error('Health check error:', error);
        return false;
    }
}

/**
 * Проверяет здоровье сервиса укладки
 */
export async function checkLayoutHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_URL}/layout/health`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
            mode: 'cors',
            credentials: 'omit'
        });
        
        if (!response.ok) {
            console.error('Layout health check failed:', response.status, response.statusText);
            return false;
        }
        
        const data = await response.json();
        return data.status === 'ok';
    } catch (error) {
        console.error('Layout health check error:', error);
        return false;
    }
}

/**
 * Получает укладку графа
 */
export async function getLayout(): Promise<LayoutResponse> {
    const response = await fetch(`${API_URL}/layout/neo4j`, {
        method: 'GET',
        headers: {
            'Accept': 'application/json; charset=utf-8',
        },
        mode: 'cors',
        credentials: 'omit'
    });
    
    if (!response.ok) {
        throw new Error('Failed to fetch layout');
    }

    const text = await response.text();
    const data = JSON.parse(text);
    
    return data;
}

/**
 * Создает новый блок
 */
export async function createBlock(content: string): Promise<{success: boolean, block?: Block}> {
    const response = await fetch(`${API_URL}/api/blocks`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        body: JSON.stringify({ content }),
    });

    if (!response.ok) {
        console.error('Failed to create block:', response.statusText);
        return { success: false };
    }
    return response.json();
}

/**
 * Создает новую связь
 */
export async function createLink(source: string, target: string): Promise<{success: boolean, link?: Link}> {
    const response = await fetch(`${API_URL}/api/links`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        body: JSON.stringify({ source, target }),
    });

    if (!response.ok) {
        console.error('Failed to create link:', response.statusText);
        return { success: false };
    }
    return response.json();
}

/**
 * Атомарно создает новый блок и связь с существующим
 */
export async function createBlockAndLink(
  source_block_id: string, 
  link_direction: 'from_source' | 'to_source',
  new_block_content: string = "Новый блок", 
): Promise<{success: boolean, new_block_id?: string, link_id?: string}> {
    const response = await fetch(`${API_URL}/api/blocks/create_and_link`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        body: JSON.stringify({ source_block_id, new_block_content, link_direction }),
    });

    if (!response.ok) {
        console.error('Failed to create block and link:', response.statusText);
        return { success: false };
    }
    return response.json();
}