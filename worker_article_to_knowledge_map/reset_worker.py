"""
CLI-скрипт для сброса всех статей обратно в pending.
Используется перед перезапуском воркера после улучшения модели.

Использование:
  # Показать, что будет сброшено (без изменений)
  poetry run python reset_worker.py --dry-run

  # Выполнить сброс
  poetry run python reset_worker.py

  # Сброс с конкретным run_id
  poetry run python reset_worker.py --run-id <run_id>
"""
import argparse
import asyncio
import sys

from config import load_config
from state_store import StateStore


async def main(dry_run: bool, run_id: str | None) -> None:
    config = load_config()
    store = StateStore(config)

    try:
        await store.init()

        # Если указан run_id — переключиться на него
        if run_id:
            store._run_id = run_id
            print(f"Using run_id: {run_id}")
        else:
            print(f"Using current run_id: {store.run_id}")

        summary = await store.get_summary()
        done = summary.get("done", 0)
        failed = summary.get("failed", 0)
        total = summary.get("total", 0)

        print(f"\nТекущее состояние:")
        print(f"  Всего статей:    {total}")
        print(f"  Done:            {done}")
        print(f"  Failed:          {failed}")
        print(f"  In progress:     {summary.get('in_progress', 0)}")
        print(f"  Pending:         {summary.get('pending', 0)}")
        print(f"\nБудет сброшено: {done + failed} статей (done + failed) → pending")

        if dry_run:
            print("\n[DRY RUN] Изменения не применены. Запустите без --dry-run для выполнения.")
            return

        if done + failed == 0:
            print("\nНечего сбрасывать.")
            return

        confirm = input(f"\nСброс {done + failed} статей и удаление их Action-нод? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Отменено.")
            return

        result = await store.reset_all_to_pending()
        print(f"\nГотово:")
        print(f"  Сброшено статей: {result['reset_count']}")
        print(f"  Удалено Action-нод: {result['deleted_actions']}")
        print(f"\nЗапустите воркер: .\\start.ps1")

    finally:
        await store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сбросить все статьи воркера в pending")
    parser.add_argument("--dry-run", action="store_true", help="Показать что будет сброшено без изменений")
    parser.add_argument("--run-id", help="run_id воркера (по умолчанию — текущий из Neo4j)")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run, run_id=args.run_id))
