/**
 * API клиент для взаимодействия с бэкендом
 */

const API_URL = 'http://localhost:8000';

export interface Block {
    id: string;
    content: string;
    x?: number;
    y?: number;
    layer?: number;
    level?: number;
    sublevel_id?: number;
    metadata: Record<string, string>;
}

export interface Link {
    id: string;
    source_id: string;
    target_id: string;
    metadata: Record<string, string>;
}

export interface Level {
    id: number;
    sublevel_ids: number[];
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    color: number;
    name: string;
}

export interface Sublevel {
    id: number;
    y: number;
    block_ids: string[];
    min_x: number;
    max_x: number;
    color: number;
    level_id: number;
    height: number;
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
    success: boolean;
    blocks: Block[];
    levels: Level[];
    sublevels: Sublevel[];
    statistics: LayoutStatistics;
    error?: string;
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
export async function getLayout(blocks: any[] = [], links: any[] = [], options: any = {}) {
    try {
        // Используем endpoint /layout/neo4j для получения данных из базы
        const response = await fetch(`${API_URL}/layout/neo4j`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Проверяем наличие данных
        if (!data.blocks || data.blocks.length === 0) {
            return {
                success: false,
                error: 'В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.',
                blocks: [],
                links: [],
                levels: [],
                sublevels: []
            };
        }

        // Фильтруем невалидные блоки
        const validBlocks = data.blocks.filter((block: Block) => block && block.id);
        
        // Если после фильтрации блоков не осталось, возвращаем ошибку
        if (validBlocks.length === 0) {
            return {
                success: false,
                error: 'В базе данных нет валидных блоков (все блоки не имеют id).',
                blocks: [],
                links: [],
                levels: [],
                sublevels: []
            };
        }

        // Фильтруем связи, оставляя только те, которые ссылаются на валидные блоки
        const validBlockIds = new Set(validBlocks.map((block: Block) => block.id));
        const validLinks = (data.links || []).filter((link: Link) => 
            link && link.source_id && link.target_id && 
            validBlockIds.has(link.source_id) && validBlockIds.has(link.target_id)
        );

        return {
            success: true,
            ...data,
            blocks: validBlocks,
            links: validLinks
        };

    } catch (error) {
        console.error('Error getting layout:', error);
        return {
            success: false,
            error: error instanceof Error ? error.message : 'Неизвестная ошибка',
            blocks: [],
            links: [],
            levels: [],
            sublevels: []
        };
    }
}