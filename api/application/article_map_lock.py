"""Захват межпроцессной блокировки с корректной очисткой при отмене await."""
import asyncio


async def acquire_map_lock(repository, article_id, pipeline_id, user_uid, token):
    operation = asyncio.create_task(asyncio.to_thread(
        repository.acquire, article_id, pipeline_id, user_uid, token,
    ))
    try:
        await asyncio.shield(operation)
    except asyncio.CancelledError:
        # Поток драйвера нельзя отменить: дожидаемся транзакции и освобождаем свой token.
        try:
            await asyncio.shield(operation)
        finally:
            await asyncio.shield(asyncio.to_thread(
                repository.release, article_id, pipeline_id, user_uid, token,
            ))
        raise
