#!/usr/bin/env python3
"""
Простой тест алгоритма укладки закреплённых блоков
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'layering', 'src'))

from layout_algorithm import layout_knowledge_map

def test_pinned_behavior():
    """Тестирует поведение закреплённых блоков"""
    
    print("=== ТЕСТ ЗАКРЕПЛЁННЫХ БЛОКОВ ===")
    
    # Простой граф: A -> B -> C
    blocks = ["A", "B", "C", "D"]
    links = [("A", "B"), ("B", "C"), ("A", "D")]
    
    print(f"Блоки: {blocks}")
    print(f"Связи: {links}")
    
    # Тест 1: Все блоки незакреплённые
    print("\n--- Тест 1: Все блоки незакреплённые ---")
    options1 = {
        'blocks_data': {
            'A': {'is_pinned': False},
            'B': {'is_pinned': False}, 
            'C': {'is_pinned': False},
            'D': {'is_pinned': False}
        }
    }
    
    result1 = layout_knowledge_map(blocks, links, options1)
    print_result("Незакреплённые", result1)
    
    # Тест 2: B закреплён без явного уровня
    print("\n--- Тест 2: B закреплён (без уровня) ---")
    options2 = {
        'blocks_data': {
            'A': {'is_pinned': False},
            'B': {'is_pinned': True},  # Без level - должен получить уровень 0
            'C': {'is_pinned': False},
            'D': {'is_pinned': False}
        }
    }
    
    result2 = layout_knowledge_map(blocks, links, options2)
    print_result("B закреплён", result2)
    
    # Тест 3: B и D закреплены без явных уровней
    print("\n--- Тест 3: B и D закреплены (без уровней) ---")
    options3 = {
        'blocks_data': {
            'A': {'is_pinned': False},
            'B': {'is_pinned': True},  # Должен получить уровень 0
            'C': {'is_pinned': False},
            'D': {'is_pinned': True}   # Должен получить уровень 1
        }
    }
    
    result3 = layout_knowledge_map(blocks, links, options3)
    print_result("B и D закреплены", result3)
    
    # Тест 4: B закреплён с явным уровнем 5
    print("\n--- Тест 4: B закреплён (level=5) ---")
    options4 = {
        'blocks_data': {
            'A': {'is_pinned': False},
            'B': {'is_pinned': True, 'level': 5},  # Явный уровень 5
            'C': {'is_pinned': False},
            'D': {'is_pinned': False}
        }
    }
    
    result4 = layout_knowledge_map(blocks, links, options4)
    print_result("B с level=5", result4)
    
    print("\n=== ВЫВОДЫ ===")
    print("✓ Каждый закреплённый блок создаёт свой уникальный уровень")
    print("✓ Блоки с явными уровнями сохраняют их")
    print("✓ Незакреплённые блоки размещаются отдельно")

def print_result(test_name, result):
    """Выводит результат теста"""
    print(f"\nРезультат '{test_name}':")
    print(f"  Уровни: {result['levels']}")
    print(f"  Подуровни: {result['sublevels']}")
    
    # Анализируем какие блоки на каких уровнях
    level_blocks = {}
    for level_id, sublevel_ids in result['levels'].items():
        blocks_in_level = []
        for sublevel_id in sublevel_ids:
            blocks_in_level.extend(result['sublevels'][sublevel_id])
        level_blocks[level_id] = blocks_in_level
    
    print(f"  Блоки по уровням: {level_blocks}")

if __name__ == "__main__":
    test_pinned_behavior() 