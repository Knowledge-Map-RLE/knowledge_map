# Функциональность перемещения закрепленных блоков

## Описание
Реализована возможность перемещения закрепленных блоков между уровнями с помощью горячих клавиш `Ctrl+Up` и `Ctrl+Down`.

## Как использовать
1. Выделите закрепленный блок (блок должен быть закреплен за уровнем)
2. Нажмите `Ctrl+Up` для перемещения на уровень выше
3. Нажмите `Ctrl+Down` для перемещения на уровень ниже

## Логика работы

### Поиск целевого уровня
- При нажатии `Ctrl+Up`: ищется ближайший уровень выше текущего (максимальный из уровней меньше текущего)
- При нажатии `Ctrl+Down`: ищется ближайший уровень ниже текущего (минимальный из уровней больше текущего)
- Если подходящий уровень не найден:
  - `Ctrl+Up`: создается новый уровень **выше всех** существующих закрепленных блоков
  - `Ctrl+Down`: создается новый уровень **ниже всех** существующих закрепленных блоков
- После успешного перемещения выделение автоматически снимается

### Примеры
Если есть закрепленные блоки на уровнях 1, 3, 5, 7 и выделен блок на уровне 5:
- `Ctrl+Up` → переместит на уровень 3 (ближайший выше)
- `Ctrl+Down` → переместит на уровень 7 (ближайший ниже)

Если выделен блок на уровне 1 (самый верхний):
- `Ctrl+Up` → переместит на новый уровень 0 (выше всех закрепленных)
- `Ctrl+Down` → переместит на уровень 3 (ближайший ниже)

Если выделен блок на уровне 7 (самый нижний):
- `Ctrl+Up` → переместит на уровень 5 (ближайший выше)  
- `Ctrl+Down` → переместит на новый уровень 8 (ниже всех закрепленных)

**Ключевое отличие:** Новые уровни создаются на границах всех закрепленных блоков, а не относительно текущего блока.

## Технические детали

### Frontend изменения

#### 1. `useKeyboardControls.ts`
```typescript
interface UseKeyboardControlsProps {
  // ... существующие параметры
  selectedBlocks?: string[];
  blocks?: BlockData[];
  levels?: any[];
  onMovePinnedBlock?: (blockId: string, direction: 'up' | 'down') => void;
}

// Добавлена обработка клавиш:
case 'ArrowUp':
  if (e.ctrlKey && selectedBlocks.length === 1 && onMovePinnedBlock) {
    e.preventDefault();
    const selectedBlockId = selectedBlocks[0];
    const selectedBlock = blocks.find(b => b.id === selectedBlockId);
    if (selectedBlock?.is_pinned) {
      onMovePinnedBlock(selectedBlockId, 'up');
    }
  }
  break;
```

#### 2. `Knowledge_map/index.tsx`
```typescript
// Функция поиска целевого уровня
const findTargetLevel = useCallback((currentLevel: number, direction: 'up' | 'down') => {
  const pinnedBlocksMap = new Map<number, string[]>();
  
  // Группируем закрепленные блоки по уровням
  blocks.forEach(block => {
    if (block.is_pinned) {
      const level = block.level;
      if (!pinnedBlocksMap.has(level)) {
        pinnedBlocksMap.set(level, []);
      }
      pinnedBlocksMap.get(level)!.push(block.id);
    }
  });
  
  // Логика поиска...
}, [blocks]);

// Обработчик перемещения
const handleMovePinnedBlock = useCallback(async (blockId: string, direction: 'up' | 'down') => {
  const block = blocks.find(b => b.id === blockId);
  if (!block || !block.is_pinned) return;

  const targetLevel = findTargetLevel(block.level, direction);
  const result = await moveBlockToLevel(blockId, targetLevel);
  if (result.success) {
    clearSelection(); // Снимаем выделение после перемещения
    loadLayoutData(); // Перезагружаем для новой укладки
  }
}, [blocks, findTargetLevel, loadLayoutData, clearSelection]);
```

#### 3. `api.ts`
```typescript
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
      return { success: false, error: `Failed to move block: ${response.statusText}` };
    }
    
    return await response.json();
  } catch (error) {
    return { success: false, error: 'Network error' };
  }
}
```

### Backend изменения

#### 1. `main.py` - Новая модель
```python
class MoveToLevelInput(BaseModel):
    target_level: int
```

#### 2. `main.py` - Новый endpoint
```python
@app.post("/api/blocks/{block_id}/move_to_level", response_model=Dict[str, Any])
async def move_block_to_level(block_id: str, data: MoveToLevelInput):
    """Перемещает закрепленный блок на указанный уровень."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            
            # Проверяем, что блок закреплен
            if not block.is_pinned:
                raise HTTPException(status_code=400, detail="Block must be pinned to move between levels")
            
            # Обновляем уровень блока
            block.level = data.target_level
            block.save()
            
        return {"success": True, "message": f"Block {block_id} moved to level {data.target_level} successfully"}
        
    except Block.DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error moving block to level: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

## Интеграция с алгоритмом укладки

Алгоритм укладки уже поддерживает закрепленные блоки и корректно сохраняет их новые позиции в базу данных через существующий механизм в `/layout/neo4j` endpoint.

## Тестирование

Создан тестовый файл `test_move_block.py` для проверки функциональности:
- Автоматически находит незакрепленный блок
- Закрепляет его
- Тестирует перемещение вверх и вниз
- Проверяет финальное состояние

## Использование

После запуска сервисов:
1. Откройте frontend приложение
2. Найдите блок и закрепите его (ПКМ → "📌 Закрепить за уровнем")
3. Выделите закрепленный блок
4. Используйте `Ctrl+Up`/`Ctrl+Down` для перемещения между уровнями 