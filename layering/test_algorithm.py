#!/usr/bin/env python3
"""
Простой тест алгоритма укладки с закрепленными блоками
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from layout_algorithm import layout_knowledge_map

def test_pinned_blocks():
    """Тестирует алгоритм с закрепленными блоками"""
    
    # Тестовые блоки
    blocks = ["block1", "block2", "block3", "block4", "block5", "block6"]
    
    # Тестовые связи
    links = [
        ("block1", "block2"),
        ("block2", "block3"),
        ("block1", "block4"),
        ("block4", "block5"),
        ("block3", "block6")
    ]
    
    # Опции с закрепленными блоками - некоторые без явного уровня
    options = {
        'optimize_layout': True,
        'blocks_per_sublevel': 10,
        'blocks_data': {
            'block1': {'is_pinned': True, 'level': 2},  # Явно указанный уровень
            'block3': {'is_pinned': True},              # Без уровня - должен получить свой
            'block5': {'is_pinned': True},              # Без уровня - должен получить свой
            'block2': {'is_pinned': False},
            'block4': {'is_pinned': False},
            'block6': {'is_pinned': False}
        }
    }
    
    print("=== ТЕСТ АЛГОРИТМА УКЛАДКИ С ЗАКРЕПЛЕННЫМИ БЛОКАМИ ===")
    print(f"Блоки: {blocks}")
    print(f"Связи: {links}")
    
    pinned_blocks = [bid for bid, data in options['blocks_data'].items() if data.get('is_pinned', False)]
    print(f"Закрепленные блоки: {pinned_blocks}")
    
    # block1 имеет явный уровень 2
    # block3 и block5 должны получить уникальные уровни (0 и 1)
    print("Ожидаемое поведение:")
    print("- block1: уровень 2 (явно указан)")
    print("- block3: уровень 0 (автоматически)")
    print("- block5: уровень 1 (автоматически)")
    print("- block2, block4, block6: уровни >= 3 (незакреплённые)")
    
    try:
        result = layout_knowledge_map(blocks, links, options)
        
        print("\n=== РЕЗУЛЬТАТ ===")
        print(f"Слои: {result['layers']}")
        print(f"Подуровни: {result['sublevels']}")
        print(f"Уровни: {result['levels']}")
        print(f"Статистика: {result['statistics']}")
        
        # Проверяем что каждый закреплённый блок на отдельном уровне
        print("\n=== ПРОВЕРКА УНИКАЛЬНОСТИ УРОВНЕЙ ===")
        pinned_levels = set()
        unpinned_levels = set()
        
        for sublevel_id, blocks_in_sublevel in result['sublevels'].items():
            # Находим уровень этого подуровня
            level_id = None
            for lvl, sublevels_in_level in result['levels'].items():
                if sublevel_id in sublevels_in_level:
                    level_id = lvl
                    break
            
            if level_id is not None:
                # Проверяем блоки в подуровне
                for block_id in blocks_in_sublevel:
                    block_data = options['blocks_data'].get(block_id, {})
                    if block_data.get('is_pinned', False):
                        pinned_levels.add(level_id)
                        print(f"Закреплённый блок {block_id} на уровне {level_id}")
                    else:
                        unpinned_levels.add(level_id)
                        print(f"Незакреплённый блок {block_id} на уровне {level_id}")
        
        # Проверяем что нет пересечений
        intersection = pinned_levels.intersection(unpinned_levels)
        if intersection:
            print(f"ОШИБКА: Уровни {intersection} содержат и закреплённые и незакреплённые блоки!")
            return False
        else:
            print("✓ Закреплённые и незакреплённые блоки находятся на разных уровнях")
        
        print(f"Уровни с закреплёнными блоками: {sorted(pinned_levels)}")
        print(f"Уровни с незакреплёнными блоками: {sorted(unpinned_levels)}")
        
        return True
        
    except Exception as e:
        print(f"\nОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pinned_blocks()
    sys.exit(0 if success else 1) 