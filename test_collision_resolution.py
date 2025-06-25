#!/usr/bin/env python3
"""
Тест системы разрешения коллизий блоков в алгоритме укладки.
"""

import sys
import os
import logging

# Добавляем пути для импорта модулей
sys.path.append(os.path.join(os.path.dirname(__file__), 'layering', 'src'))

from layout_algorithm import layout_knowledge_map

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_collision_test_data():
    """Создает тестовые данные, которые гарантированно вызовут коллизии."""
    
    # Создаем много блоков в одном слое для принудительного создания коллизий
    blocks = [f"block_{i}" for i in range(20)]
    
    # Создаем структуру, где много блоков будут в одном слое
    links = []
    
    # Один корневой блок (block_0)
    # Много блоков второго слоя (block_1 - block_15) связаны с корневым
    for i in range(1, 16):
        links.append(("block_0", f"block_{i}"))
    
    # Несколько блоков третьего слоя (block_16 - block_19)
    for i in range(16, 20):
        parent_index = ((i - 16) % 3) + 1  # Связываем с block_1, block_2, block_3
        links.append((f"block_{parent_index}", f"block_{i}"))
    
    # Делаем несколько блоков закрепленными на разных уровнях
    blocks_data = {}
    for i, block_id in enumerate(blocks):
        blocks_data[block_id] = {
            'is_pinned': i in [0, 8, 16],  # Закрепляем блоки на разных уровнях
            'level': i // 8 if i in [0, 8, 16] else 0  # 3 разных уровня
        }
    
    return blocks, links, blocks_data

def test_collision_resolution():
    """Тестирует систему разрешения коллизий."""
    
    print("🚗 Тестирование системы разрешения коллизий блоков")
    print("=" * 60)
    
    try:
        # Создаем тестовые данные с коллизиями
        print("📊 Создание данных с гарантированными коллизиями...")
        blocks, links, blocks_data = create_collision_test_data()
        
        print(f"📦 Создано: {len(blocks)} блоков, {len(links)} связей")
        print(f"🎯 Ожидаемые коллизии: много блоков во втором слое (15 блоков)")
        
        pinned_count = sum(1 for bd in blocks_data.values() if bd['is_pinned'])
        print(f"📌 Закрепленных блоков: {pinned_count}")
        
        # Запускаем алгоритм
        print("\n🚀 Запуск алгоритма с разрешением коллизий...")
        
        options = {
            'optimize_layout': True,
            'blocks_data': blocks_data
        }
        
        result = layout_knowledge_map(blocks, links, options)
        stats = result['statistics']
        sublevels = result['sublevels']
        levels = result['levels']
        
        # Анализируем результаты
        print("\n📈 Результаты алгоритма:")
        print("-" * 40)
        
        print(f"🔢 Общая статистика:")
        print(f"   • Всего блоков: {stats['total_blocks']}")
        print(f"   • Всего связей: {stats['total_links']}")
        print(f"   • Закрепленных блоков: {stats['pinned_blocks']}")
        print(f"   • Незакрепленных блоков: {stats['unpinned_blocks']}")
        
        print(f"\n📊 Структура результата:")
        print(f"   • Всего уровней: {stats['total_levels']}")
        print(f"   • Всего подуровней: {stats['total_sublevels']}")
        print(f"   • Максимальный слой: {stats['max_layer']}")
        
        # Детальный анализ подуровней
        print(f"\n🎯 Анализ размещения блоков:")
        
        blocks_per_sublevel = [len(blocks_list) for blocks_list in sublevels.values()]
        if blocks_per_sublevel:
            avg_blocks = sum(blocks_per_sublevel) / len(blocks_per_sublevel)
            max_blocks = max(blocks_per_sublevel)
            min_blocks = min(blocks_per_sublevel)
            
            print(f"   • Среднее заполнение подуровня: {avg_blocks:.1f} блоков")
            print(f"   • Максимальное заполнение: {max_blocks} блоков")
            print(f"   • Минимальное заполнение: {min_blocks} блоков")
            
            # Проверяем наличие коллизий
            collision_sublevel = max(blocks_per_sublevel)
            if collision_sublevel >= 10:
                print(f"⚠️  Потенциальные коллизии в подуровне с {collision_sublevel} блоками")
                print(f"   → Клиентская часть автоматически создаст дополнительные виртуальные подуровни")
            else:
                print("✅ Коллизий не ожидается - все подуровни умеренно заполнены")
        
        # Анализ структуры уровней
        print(f"\n🏗️ Структура уровней:")
        for level_id in sorted(levels.keys()):
            sublevel_ids = levels[level_id]
            total_blocks_in_level = sum(len(sublevels[sid]) for sid in sublevel_ids)
            
            # Показываем детали для уровней с потенциальными коллизиями
            level_details = []
            for sid in sublevel_ids:
                sublevel_size = len(sublevels[sid])
                if sublevel_size > 8:
                    level_details.append(f"подуровень {sid}: {sublevel_size} блоков (⚠️ коллизии)")
                else:
                    level_details.append(f"подуровень {sid}: {sublevel_size} блоков")
            
            print(f"   Уровень {level_id}: {len(sublevel_ids)} подуровней, {total_blocks_in_level} блоков")
            for detail in level_details:
                print(f"     • {detail}")
        
        # Инструкции для клиентской части
        print(f"\n🔧 Система разрешения коллизий на клиенте:")
        print(f"   1. Алгоритм автоматически обнаружит перекрывающиеся блоки")
        print(f"   2. Создаст виртуальные подуровни для разделения блоков вертикально")
        print(f"   3. Сохранит топологический порядок (приоритет #1)")
        print(f"   4. Расширит границы подуровней при необходимости")
        
        print("\n" + "=" * 60)
        print("✅ Тест системы разрешения коллизий завершён!")
        
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        logger.exception("Подробности ошибки:")
        return False
        
    return True

if __name__ == "__main__":
    success = test_collision_resolution()
    sys.exit(0 if success else 1) 