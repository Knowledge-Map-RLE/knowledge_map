import os

def print_tree_filtered(start_path, ignore_list):
    print(f"Структура проекта: {os.path.abspath(start_path)}")
    
    for root, dirs, files in os.walk(start_path):
        # 1. Фильтруем список директорий "на месте"
        # Это предотвратит рекурсивный обход исключенных папок
        dirs[:] = [d for d in dirs if d not in ignore_list]
        
        # 2. Вычисляем уровень вложенности для отступов
        relative_path = os.path.relpath(root, start_path)
        if relative_path == ".":
            level = 0
        else:
            level = relative_path.count(os.sep) + 1
            
        indent = '│   ' * (level - 1) + ('├── ' if level > 0 else '')
        
        # Печатаем текущую папку
        print(f"{indent}{os.path.basename(root)}/")
        
        # 3. Печатаем файлы в текущей папке
        sub_indent = '│   ' * level + '└── '
        for f in files:
            print(f"{sub_indent}{f}")



if __name__ == '__main__':
    # Настройки исключений
    ignore = {"node_modules", ".pytest_cache", ".venv", "logs", "models", ".git", "__pycache__"}

    # Запуск
    print_tree_filtered("./nlp", ignore)