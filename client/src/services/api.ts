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
    is_pinned?: boolean;
    metadata?: Record<string, any>;
    physical_scale?: number; // степень 10 в метрах для физического масштаба уровня
}

export interface Link {
    id: string;
    source_id: string;
    target_id: string;
    metadata?: Record<string, any>;
}

export interface Level {
    id: number;
    sublevel_ids: number[];
    name?: string;
    color?: string;
}

export interface Sublevel {
    id: number;
    block_ids: string[];
    level_id: number;
    color?: string;
}

export interface LayoutStatistics {
    total_blocks: number;
    total_links: number;
    total_levels: number;
    total_sublevels: number;
    max_layer: number;
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

export interface S3FileResponse {
    content?: string;
    content_type?: string;
    size?: number;
    last_modified?: string;
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

/**
 * Удаляет блок
 */
export async function deleteBlock(blockId: string): Promise<{success: boolean, error?: string}> {
    const response = await fetch(`${API_URL}/api/blocks/${blockId}`, {
        method: 'DELETE',
        headers: {
            'Accept': 'application/json',
        },
    });

    if (!response.ok) {
        console.error('Failed to delete block:', response.statusText);
        const errorData = await response.json().catch(() => ({}));
        return { success: false, error: errorData.detail || 'Ошибка при удалении блока' };
    }
    return response.json();
}

/**
 * Удаляет связь
 */
export async function deleteLink(linkId: string): Promise<{success: boolean, error?: string}> {
    const response = await fetch(`${API_URL}/api/links/${linkId}`, {
        method: 'DELETE',
        headers: {
            'Accept': 'application/json',
        },
    });

    if (!response.ok) {
        console.error('Failed to delete link:', response.statusText);
        const errorData = await response.json().catch(() => ({}));
        return { success: false, error: errorData.detail || 'Ошибка при удалении связи' };
    }
    return response.json();
}

/**
 * Закрепляет блок за уровнем
 */
export async function pinBlock(blockId: string): Promise<{success: boolean, error?: string}> {
    try {
        const response = await fetch(`${API_URL}/api/blocks/${blockId}/pin`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to pin block:', response.statusText, errorText);
            return { success: false, error: `Failed to pin block: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error pinning block:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Закрепляет блок за уровнем с указанным физическим масштабом
 */
export async function pinBlockWithScale(blockId: string, physicalScale: number): Promise<{success: boolean, error?: string}> {
    try {
        const response = await fetch(`${API_URL}/api/blocks/${blockId}/pin_with_scale`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({ physical_scale: physicalScale }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to pin block with scale:', response.statusText, errorText);
            return { success: false, error: `Failed to pin block with scale: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error pinning block with scale:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Открепляет блок от уровня
 */
export async function unpinBlock(blockId: string): Promise<{success: boolean, error?: string}> {
    try {
        const response = await fetch(`${API_URL}/api/blocks/${blockId}/unpin`, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
            },
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to unpin block:', response.statusText, errorText);
            return { success: false, error: `Failed to unpin block: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error unpinning block:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Перемещает закрепленный блок на указанный уровень
 */
export async function moveBlockToLevel(blockId: string, targetLevel: number): Promise<{success: boolean, error?: string}> {
    try {
        const response = await fetch(`${API_URL}/api/blocks/${blockId}/move_to_level`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({ target_level: targetLevel }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Failed to move block to level:', response.statusText, errorText);
            return { success: false, error: `Failed to move block: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error moving block to level:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Получает markdown файл из S3 для NLP компонента
 */
export async function getNLPMarkdown(filename: string): Promise<S3FileResponse> {
    try {
        const response = await fetch(`${API_URL}/api/nlp/markdown/${encodeURIComponent(filename)}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
            mode: 'cors',
            credentials: 'omit'
        });

        if (!response.ok) {
            console.error('Failed to get NLP markdown:', response.statusText);
            return { error: `Failed to get markdown file: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error getting NLP markdown:', error);
        return { error: 'Network error' };
    }
}

/**
 * Получает объект из S3
 */
export async function getS3Object(bucketName: string, objectKey: string): Promise<S3FileResponse> {
    try {
        const response = await fetch(`${API_URL}/api/s3/buckets/${bucketName}/objects/${encodeURIComponent(objectKey)}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
            mode: 'cors',
            credentials: 'omit'
        });

        if (!response.ok) {
            console.error('Failed to get S3 object:', response.statusText);
            return { error: `Failed to get object: ${response.statusText}` };
        }

        return await response.json();
    } catch (error) {
        console.error('Error getting S3 object:', error);
        return { error: 'Network error' };
    }
}

/**
 * HTTP клиент для использования в других сервисах
 */
export const api = {
    get: async (url: string) => {
        const response = await fetch(`${API_URL}${url}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
            mode: 'cors',
            credentials: 'omit'
        });
        return response;
    },
    
    post: async (url: string, data?: any) => {
        const response = await fetch(`${API_URL}${url}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: data ? JSON.stringify(data) : undefined,
            mode: 'cors',
            credentials: 'omit'
        });
        return response;
    }
};