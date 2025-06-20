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
    metadata?: Record<string, any>;
}

export interface Link {
    id: string;
    source_id: string;
    target_id: string;
    metadata?: Record<string, any>;
}

export interface Level {
    id: number;
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    color?: number;
    name?: string;
    block_ids: string[];
    level: number;
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

export interface CreateAndLinkResponse {
    success: boolean;
    new_block?: Block;
    new_link?: Link;
    error?: string;
}

export interface LayoutData {
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
  sourceBlockId: string,
  linkDirection: 'from_source' | 'to_source'
): Promise<CreateAndLinkResponse> {
  try {
    const response = await fetch(`${API_URL}/api/blocks/create_and_link`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        body: JSON.stringify({
            source_block_id: sourceBlockId,
            link_direction: linkDirection
        })
    });

    if (!response.ok) {
        const errorData = await response.json();
        console.error('Ошибка при создании блока и связи:', errorData);
        return { success: false, error: errorData.detail || 'Неизвестная ошибка сервера' };
    }
    return await response.json();
  } catch (error) {
    console.error('Сетевая ошибка или ошибка парсинга JSON:', error);
    return { success: false, error: 'Сетевая ошибка или невалидный JSON' };
  }
}