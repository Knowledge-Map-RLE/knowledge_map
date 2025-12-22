#!/usr/bin/env python3
"""
Скрипт для исправления относительных импортов в сгенерированных protobuf файлах.
grpc_tools.protoc генерирует файлы с относительными импортами (from . import),
которые не работают при прямом импорте модулей.
"""
import os
import re
from pathlib import Path


def fix_proto_imports(directory: str):
    """Исправляет относительные импорты в proto файлах"""
    directory_path = Path(directory)

    if not directory_path.exists():
        print(f"Директория не найдена: {directory}")
        return

    # Находим все *_pb2_grpc.py файлы
    grpc_files = list(directory_path.glob("*_pb2_grpc.py"))

    if not grpc_files:
        print(f"Не найдено *_pb2_grpc.py файлов в {directory}")
        return

    fixed_count = 0
    for file_path in grpc_files:
        try:
            # Читаем файл
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Исправляем относительные импорты на абсолютные
            # from . import xxx_pb2 as xxx__pb2 -> import xxx_pb2 as xxx__pb2
            new_content = re.sub(
                r'^from \. import (\w+_pb2) as (\w+__pb2)',
                r'import \1 as \2',
                content,
                flags=re.MULTILINE
            )

            # Если файл изменился, записываем его
            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"✓ Исправлен: {file_path.name}")
                fixed_count += 1
            else:
                print(f"  Без изменений: {file_path.name}")

        except Exception as e:
            print(f"✗ Ошибка при обработке {file_path.name}: {e}")

    print(f"\nИсправлено файлов: {fixed_count}/{len(grpc_files)}")


if __name__ == "__main__":
    # Путь к директории с сгенерированными файлами
    generated_dir = Path(__file__).parent / "utils" / "generated"

    print(f"Исправление proto импортов в: {generated_dir}\n")
    fix_proto_imports(str(generated_dir))
