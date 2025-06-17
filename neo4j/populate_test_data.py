#!/usr/bin/env python3
"""
Скрипт для заполнения Neo4j тестовыми данными
Создает 100 блоков и 100 связей для тестирования карты знаний
"""

import sys
import os
from typing import List, Dict, Any
import random
import string
from datetime import datetime

# Добавляем путь к api папке для импорта моделей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from neomodel import config, db, clear_neo4j_database
from models import User, Block, Tag, LinkMetadata

# Настройка подключения к Neo4j
NEO4J_URL = os.getenv('NEO4J_URL', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

config.DATABASE_URL = f'bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{NEO4J_URL.replace("bolt://", "")}'

def generate_random_content(length: int = None) -> str:
    """Генерирует случайный контент для блока"""
    topics = [
        'Программирование', 'Python', 'JavaScript', 'React', 'Vue.js', 'Angular',
        'Базы данных', 'SQL', 'NoSQL', 'MongoDB', 'PostgreSQL', 'MySQL',
        'Веб-разработка', 'Frontend', 'Backend', 'Fullstack', 'DevOps',
        'Алгоритмы', 'Структуры данных', 'Сортировка', 'Поиск', 'Графы',
        'Машинное обучение', 'Нейронные сети', 'Deep Learning', 'TensorFlow',
        'Облачные технологии', 'AWS', 'Docker', 'Kubernetes', 'CI/CD',
        'Тестирование', 'Unit тесты', 'Integration тесты', 'E2E тесты',
        'Архитектура', 'Микросервисы', 'Монолит', 'REST API', 'GraphQL',
        'Безопасность', 'Аутентификация', 'Авторизация', 'HTTPS', 'OAuth',
        'Мобильная разработка', 'iOS', 'Android', 'React Native', 'Flutter',
        'Data Science', 'Pandas', 'NumPy', 'Matplotlib', 'Jupyter',
        'Операционные системы', 'Linux', 'Windows', 'macOS', 'Bash',
        'Сетевые технологии', 'TCP/IP', 'HTTP', 'WebSocket', 'gRPC',
        'Версионный контроль', 'Git', 'GitHub', 'GitLab', 'Branching',
        'Математика', 'Статистика', 'Линейная алгебра', 'Дискретная математика'
    ]
    
    # Выбираем случайную тему
    topic = random.choice(topics)
    
    # Добавляем дополнительное описание
    descriptions = [
        'Основы и принципы',
        'Продвинутые техники',
        'Лучшие практики',
        'Паттерны проектирования',
        'Производительность и оптимизация',
        'Инструменты и библиотеки',
        'Современные подходы',
        'Архитектурные решения',
        'Практические примеры',
        'Интеграция и взаимодействие'
    ]
    
    description = random.choice(descriptions)
    
    if length:
        content = f"{topic}: {description}"
        if len(content) > length:
            content = content[:length-3] + "..."
        return content
    
    return f"{topic}: {description}"

def generate_user_data() -> Dict[str, Any]:
    """Генерирует данные тестового пользователя"""
    
    names = ['Алексей', 'Мария', 'Дмитрий', 'Анна', 'Сергей', 'Елена', 'Андрей', 'Ольга']
    surnames = ['Иванов', 'Петров', 'Сидоров', 'Козлов', 'Новиков', 'Морозов', 'Волков', 'Соколов']
    
    name = random.choice(names)
    surname = random.choice(surnames)
    
    return {
        'login': f"user_{name.lower()}_{random.randint(1, 999)}",
        'password': 'password123',  # В реальности должно быть захешировано
        'nickname': f"{name}_{random.randint(1, 99)}",
        'surname': surname,
        'given_names': name
    }

def create_test_user() -> User:
    """Создает тестового пользователя"""
    user_data = generate_user_data()
    
    print(f"Создаю тестового пользователя: {user_data['nickname']}")
    
    user = User(
        login=user_data['login'],
        password=user_data['password'],
        nickname=user_data['nickname'],
        surname=user_data['surname'],
        given_names=user_data['given_names']
    ).save()
    
    return user

def create_test_blocks(user: User, count: int = 100) -> List[Block]:
    """Создает тестовые блоки"""
    blocks = []
    
    print(f"Создаю {count} тестовых блоков...")
    
    # Создаем блоки в разных слоях и уровнях
    max_layers = 10  # Максимум 10 слоев
    max_levels = 5   # Максимум 5 уровней
    
    for i in range(count):
        # Распределяем блоки по слоям и уровням
        layer = i % max_layers
        level = (i // max_layers) % max_levels
        
        content = generate_random_content(50)  # Ограничиваем длину
        
        block = Block(
            content=content,
            layer=layer,
            level=level
        ).save()
        
        # Связываем с пользователем
        block.created_by.connect(user)
        
        blocks.append(block)
        
        if (i + 1) % 20 == 0:
            print(f"  Создано {i + 1} блоков...")
    
    print(f"✓ Создано {len(blocks)} блоков")
    return blocks

def create_test_links(blocks: List[Block], user: User, count: int = 100) -> List[LinkMetadata]:
    """Создает тестовые связи между блоками"""
    links = []
    
    print(f"Создаю {count} тестовых связей...")
    
    # Сортируем блоки по слоям для создания DAG
    sorted_blocks = sorted(blocks, key=lambda b: (b.layer, b.level))
    
    attempts = 0
    max_attempts = count * 5  # Увеличиваем количество попыток
    
    while len(links) < count and attempts < max_attempts:
        attempts += 1
        
        # Выбираем блоки так, чтобы from_block был в меньшем слое чем to_block
        from_idx = random.randint(0, len(sorted_blocks) - 2)
        to_idx = random.randint(from_idx + 1, len(sorted_blocks) - 1)
        
        from_block = sorted_blocks[from_idx]
        to_block = sorted_blocks[to_idx]
        
        # Дополнительная проверка слоев для избежания циклов
        if from_block.layer >= to_block.layer:
            continue
            
        # Проверяем что связь еще не существует
        try:
            existing_link = LinkMetadata.nodes.filter(
                source_id=getattr(from_block, 'element_id'),
                target_id=getattr(to_block, 'element_id')
            ).first()
        except LinkMetadata.DoesNotExist:
            existing_link = None
        
        if existing_link:
            continue
        
        try:
            # Создаем связь напрямую без проверки ацикличности (мы уже обеспечили DAG)
            # from_block.link_to(to_block, user)
            
            # Создаем прямую связь
            from_block.target.connect(to_block)
            
            # Создаем метаданные
            link_metadata = LinkMetadata(
                source_id=getattr(from_block, 'element_id'),
                target_id=getattr(to_block, 'element_id')
            ).save()
            link_metadata.created_by.connect(user)
            
            links.append(link_metadata)
            
            if len(links) % 20 == 0:
                print(f"  Создано {len(links)} связей...")
                
        except Exception as e:
            print(f"Ошибка создания связи: {e}")
            continue
    
    print(f"✓ Создано {len(links)} связей (из {attempts} попыток)")
    return links

def create_test_tags() -> List[Tag]:
    """Создает тестовые теги"""
    tag_names = [
        'python', 'javascript', 'react', 'vue', 'angular', 'node.js',
        'database', 'sql', 'nosql', 'mongodb', 'postgresql',
        'frontend', 'backend', 'fullstack', 'devops',
        'algorithms', 'data-structures', 'machine-learning',
        'web-development', 'mobile', 'testing', 'security',
        'cloud', 'docker', 'kubernetes', 'api', 'microservices'
    ]
    
    tags = []
    
    print(f"Создаю {len(tag_names)} тегов...")
    
    for tag_name in tag_names:
        tag = Tag(text=tag_name).save()
        tags.append(tag)
    
    print(f"✓ Создано {len(tags)} тегов")
    return tags

def assign_random_tags(blocks: List[Block], tags: List[Tag]):
    """Назначает случайные теги блокам"""
    print("Назначаю случайные теги блокам...")
    
    for block in blocks:
        # Каждому блоку назначаем 1-3 случайных тега
        num_tags = random.randint(1, 3)
        block_tags = random.sample(tags, min(num_tags, len(tags)))
        
        for tag in block_tags:
            tag.block.connect(block)
    
    print("✓ Теги назначены")

def verify_data():
    """Проверяет что данные создались корректно"""
    print("\n=== Проверка созданных данных ===")
    
    # Подсчитываем количество созданных объектов
    users_count = len(User.nodes.all())
    blocks_count = len(Block.nodes.all())
    links_count = len(LinkMetadata.nodes.all())
    tags_count = len(Tag.nodes.all())
    
    print(f"Пользователи: {users_count}")
    print(f"Блоки: {blocks_count}")
    print(f"Связи: {links_count}")
    print(f"Теги: {tags_count}")
    
    # Проверяем связи блоков с пользователями
    blocks_with_users = 0
    for block in Block.nodes.all():
        if block.created_by.single():
            blocks_with_users += 1
    
    print(f"Блоки со связью к пользователю: {blocks_with_users}")
    
    # Проверяем связи тегов с блоками
    tags_with_blocks = 0
    for tag in Tag.nodes.all():
        if tag.block.all():
            tags_with_blocks += 1
    
    print(f"Теги со связью к блокам: {tags_with_blocks}")
    
    return {
        'users': users_count,
        'blocks': blocks_count,
        'links': links_count,
        'tags': tags_count,
        'blocks_with_users': blocks_with_users,
        'tags_with_blocks': tags_with_blocks
    }

def main():
    """Основная функция"""
    print("=== Заполнение Neo4j тестовыми данными ===")
    print(f"Подключение к Neo4j: {config.DATABASE_URL}")
    
    try:
        # Проверяем подключение
        db.cypher_query("RETURN 1")
        print("✓ Подключение к Neo4j установлено")
        
    except Exception as e:
        print(f"❌ Ошибка подключения к Neo4j: {e}")
        print("Убедитесь что Neo4j запущен и доступен")
        return False
    
    # Предупреждение о очистке базы
    response = input("\n⚠️  ВНИМАНИЕ: Это очистит ВСЮ базу данных Neo4j. Продолжить? (yes/no): ")
    if response.lower() != 'yes':
        print("Операция отменена")
        return False
    
    try:
        # Очищаем базу данных
        print("\n🗑️  Очищаю базу данных...")
        clear_neo4j_database(db)
        print("✓ База данных очищена")
        
        # Создаем тестовые данные
        print("\n📊 Создаю тестовые данные...")
        
        # 1. Создаем пользователя
        user = create_test_user()
        
        # 2. Создаем блоки
        blocks = create_test_blocks(user, 100)
        
        # 3. Создаем связи
        links = create_test_links(blocks, user, 100)
        
        # 4. Создаем теги
        tags = create_test_tags()
        
        # 5. Назначаем теги блокам
        assign_random_tags(blocks, tags)
        
        # 6. Проверяем результат
        stats = verify_data()
        
        print("\n✅ Тестовые данные успешно созданы!")
        print(f"📈 Статистика: {stats}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании данных: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 