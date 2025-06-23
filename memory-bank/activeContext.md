# Активный контекст

## Текущая задача
Интеграция клиентских операций с серверным API для сохранения изменений в базе данных.

## Обнаруженные проблемы

### 1. Создание связей (handleCreateLink)
**Файл**: `client/src/components/Knowledge_map/hooks/useActions.ts:84-99`
- Текущее состояние: создает только mock объект локально
- Требуется: вызов API `/api/links` с сохранением в Neo4j

### 2. Удаление блоков (handleDeleteBlock)
**Файл**: `client/src/components/Knowledge_map/hooks/useActions.ts:101-130`
- Текущее состояние: удаляет только из локального стейта
- Требуется: вызов API для удаления из Neo4j

### 3. Удаление связей (handleDeleteLink)
**Файл**: `client/src/components/Knowledge_map/hooks/useActions.ts:132-148`
- Текущее состояние: удаляет только из локального стейта
- Требуется: вызов API для удаления из Neo4j

### 4. Создание блоков
**Файл**: `client/src/components/Knowledge_map/hooks/useActions.ts:50-82`
- Текущее состояние: создает только mock объект локально
- Требуется: вызов API `/api/blocks` с сохранением в Neo4j

## Существующие API эндпоинты
- ✅ `POST /api/blocks` - создание блока
- ✅ `POST /api/links` - создание связи
- ✅ `POST /api/blocks/create_and_link` - атомарное создание блока с связью
- ❌ `DELETE /api/blocks/{id}` - удаление блока (отсутствует)
- ❌ `DELETE /api/links/{id}` - удаление связи (отсутствует)

## План действий
1. Добавить отсутствующие DELETE эндпоинты в API
2. Создать функции в `client/src/services/api.ts` для удаления
3. Модифицировать хуки для вызова реальных API
4. Добавить обработку ошибок и loading состояний 