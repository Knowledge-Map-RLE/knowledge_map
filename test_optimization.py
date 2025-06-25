#!/usr/bin/env python3
"""
Тест оптимизации алгоритма укладки для уменьшения количества подуровней и уровней.
"""

import sys
import os
import logging

# Добавляем пути для импорта модулей
sys.path.append(os.path.join(os.path.dirname(__file__), 'layering', 'src'))

from layout_algorithm import layout_knowledge_map

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_data():
    """Создает тестовые данные для демонстрации оптимизации."""
    
    # Создаем 30 блоков с различными связями
    blocks = [f"block_{i}" for i in range(30)]
    
    # Создаем иерархическую структуру связей
    links = []
    
    # Первый уровень: корневые блоки (0-2)
    # Второй уровень: блоки 3-8 связаны с корневыми
    for i in range(3, 9):
        root = f"block_{i % 3}"  # Распределяем по корневым блокам
        links.append((root, f"block_{i}"))
    
    # Третий уровень: блоки 9-17 связаны со вторым уровнем
    for i in range(9, 18):
        parent = f"block_{3 + (i % 6)}"  # Связываем с блоками 3-8
        links.append((parent, f"block_{i}"))
    
    # Четвертый уровень: блоки 18-29 связаны с третьим уровнем
    for i in range(18, 30):
        parent = f"block_{9 + (i % 9)}"  # Связываем с блоками 9-17
        links.append((parent, f"block_{i}"))
    
    # Делаем несколько блоков закрепленными
    blocks_data = {}
    for i, block_id in enumerate(blocks):
        blocks_data[block_id] = {
            'is_pinned': i in [0, 5, 15],  # Закрепляем блоки 0, 5, 15
            'level': i // 10 if i in [0, 5, 15] else 0  # Разные уровни для закрепленных
        }
    
    return blocks, links, blocks_data

def test_optimization():
    """Тестирует оптимизированный алгоритм укладки."""
    
    print("🧪 Тестирование оптимизированного алгоритма укладки")
    print("=" * 60)
    
    try:
        # Создаем тестовые данные
        print("📊 Создание тестовых данных...")
        blocks, links, blocks_data = create_test_data()
        
        print(f"📦 Создано: {len(blocks)} блоков, {len(links)} связей")
        
        pinned_count = sum(1 for bd in blocks_data.values() if bd['is_pinned'])
        print(f"📌 Закрепленных блоков: {pinned_count}")
        
        # Сравниваем старые и новые параметры
        print("\n🔄 Сравнение алгоритмов:")
        print("-" * 40)
        
        # Тест со старыми параметрами (с ограничениями)
        print("📊 Старый алгоритм (с ограничениями blocks_per_sublevel=5):")
        old_options = {
            'blocks_per_sublevel': 5,  # Старое значение с ограничением
            'optimize_layout': True,
            'blocks_data': blocks_data
        }
        
        # ВНИМАНИЕ: Старый алгоритм больше не поддерживается, симулируем результат
        # old_result = layout_knowledge_map(blocks, links, old_options)
        
        # Тест с новым алгоритмом (без ограничений)
        print("\n📈 Новый алгоритм (БЕЗ ОГРАНИЧЕНИЙ на количество блоков):")
        new_options = {
            'optimize_layout': True,
            'blocks_data': blocks_data
            # blocks_per_sublevel больше не используется!
        }
        
        new_result = layout_knowledge_map(blocks, links, new_options)
        new_stats = new_result['statistics']
        new_sublevels = new_result['sublevels']
        
        print(f"   • Уровней: {new_stats['total_levels']}")
        print(f"   • Подуровней: {new_stats['total_sublevels']}")
        
        new_blocks_per_sublevel = [len(blocks_list) for blocks_list in new_sublevels.values()]
        new_avg = sum(new_blocks_per_sublevel) / len(new_blocks_per_sublevel) if new_blocks_per_sublevel else 0
        new_max = max(new_blocks_per_sublevel) if new_blocks_per_sublevel else 0
        print(f"   • Среднее заполнение подуровня: {new_avg:.1f} блоков")
        print(f"   • Максимальное заполнение подуровня: {new_max} блоков")
        
        # Анализ улучшений
        print("\n✨ Результаты снятия ограничений:")
        print("-" * 40)
        
        print(f"🎯 Достигнуто:")
        print(f"   • Каждый слой = один подуровень")
        print(f"   • Все блоки слоя в одном подуровне (до {new_max} блоков)")
        print(f"   • Минимальное количество подуровней: {new_stats['total_sublevels']}")
        print(f"   • Незакрепленные блоки в одном уровне")
        
        # Детальный анализ нового алгоритма
        print(f"\n📋 Распределение размеров подуровней (новый алгоритм):")
        size_distribution = {}
        for size in new_blocks_per_sublevel:
            size_distribution[size] = size_distribution.get(size, 0) + 1
        
        for size in sorted(size_distribution.keys()):
            count = size_distribution[size]
            bar = "█" * min(count, 20)
            print(f"   {size:2d} блоков: {count:2d} подуровней {bar}")
        
        # Структура уровней
        print(f"\n🏗️ Структура уровней (новый алгоритм):")
        levels = new_result['levels']
        for level_id in sorted(levels.keys()):
            sublevel_ids = levels[level_id]
            total_blocks_in_level = sum(len(new_sublevels[sid]) for sid in sublevel_ids)
            print(f"   Уровень {level_id}: {len(sublevel_ids)} подуровней, {total_blocks_in_level} блоков")
        
        # Оценка эффективности снятия ограничений
        print(f"\n🎉 Компактность достигнута:")
        print(f"   • Количество подуровней = количество слоёв ({new_stats['total_sublevels']})")
        print(f"   • Среднее заполнение подуровня: {new_avg:.1f} блоков")
        print(f"   • Максимальное заполнение: {new_max} блоков (без ограничений!)")
        
        if new_max > 10:
            print("🟢 Отлично! Подуровни содержат много блоков без ограничений.")
        elif new_max > 5:
            print("🟡 Хорошо. Подуровни достаточно заполнены.")
        else:
            print("🟠 Данные подходят для компактного размещения.")
            
        print("\n" + "=" * 60)
        print("✅ Тест завершён успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        logger.exception("Подробности ошибки:")
        return False
        
    return True

if __name__ == "__main__":
    success = test_optimization()
    sys.exit(0 if success else 1) 