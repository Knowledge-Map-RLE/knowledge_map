#!/usr/bin/env python3
"""
Тест для проверки функциональности физических масштабов уровней
"""

import requests
import json

# Конфигурация
API_URL = "http://localhost:8000"

def test_scale_utilities():
    """Тестируем утилиты работы с масштабами"""
    print("🧪 Тестируем утилиты конвертации масштабов...")
    
    # Импортируем утилиты (это Python эквивалент для тестирования логики)
    def exponent_to_readable_scale(exponent):
        """Python версия exponentToReadableScale для тестирования"""
        units = [
            {'name': 'нанометры', 'symbol': 'нм', 'exponent': -9},
            {'name': 'микрометры', 'symbol': 'мкм', 'exponent': -6},
            {'name': 'миллиметры', 'symbol': 'мм', 'exponent': -3},
            {'name': 'сантиметры', 'symbol': 'см', 'exponent': -2},
            {'name': 'дециметры', 'symbol': 'дм', 'exponent': -1},
            {'name': 'метры', 'symbol': 'м', 'exponent': 0},
            {'name': 'километры', 'symbol': 'км', 'exponent': 3},
            {'name': 'мегаметры', 'symbol': 'Мм', 'exponent': 6},
            {'name': 'гигаметры', 'symbol': 'Гм', 'exponent': 9},
        ]
        
        best_unit = next(unit for unit in units if unit['exponent'] == 0)  # метры по умолчанию
        
        for unit in units:
            if unit['exponent'] <= exponent:
                best_unit = unit
            else:
                break
        
        value = 10 ** (exponent - best_unit['exponent'])
        return {'value': value, 'unit': best_unit}
    
    def format_scale_for_display(exponent):
        """Python версия formatScaleForDisplay для тестирования"""
        result = exponent_to_readable_scale(exponent)
        value = result['value']
        unit = result['unit']
        
        if value == int(value):
            display_value = str(int(value))
        elif value < 1:
            display_value = f"{value:.3f}".rstrip('0').rstrip('.')
        else:
            display_value = f"{value:.1f}".rstrip('0').rstrip('.')
        
        return f"{display_value} {unit['symbol']}"
    
    # Тестовые случаи
    test_cases = [
        (0, "1 м"),      # 10^0 = 1 метр
        (3, "1 км"),     # 10^3 = 1 километр  
        (-3, "1 мм"),    # 10^-3 = 1 миллиметр
        (-9, "1 нм"),    # 10^-9 = 1 нанометр
        (1, "10 м"),     # 10^1 = 10 метров
        (4, "10 км"),    # 10^4 = 10 километров
        (-2, "1 см"),    # 10^-2 = 1 сантиметр
    ]
    
    for exponent, expected in test_cases:
        result = format_scale_for_display(exponent)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {exponent:2d} → {result:8s} (ожидалось: {expected})")
        
    print()

def test_api_endpoints():
    """Тестируем API эндпоинты для работы с масштабами"""
    print("🌐 Тестируем API эндпоинты...")
    
    try:
        # Проверяем здоровье API
        response = requests.get(f"{API_URL}/health")
        if response.status_code == 200:
            print("  ✅ API сервер работает")
        else:
            print("  ❌ API сервер недоступен")
            return
        
        # Получаем текущие блоки
        response = requests.get(f"{API_URL}/layout/neo4j")
        if response.status_code == 200:
            data = response.json()
            blocks = data.get('blocks', [])
            print(f"  ✅ Загружено {len(blocks)} блоков")
            
            # Проверяем есть ли поле physical_scale в блоках
            if blocks:
                first_block = blocks[0]
                has_physical_scale = 'physical_scale' in first_block
                print(f"  {'✅' if has_physical_scale else '❌'} Поле physical_scale {'присутствует' if has_physical_scale else 'отсутствует'} в блоках")
                
                # Показываем пример блока
                print(f"  📝 Пример блока: {first_block['id'][:8]}... level={first_block.get('level', 0)}, physical_scale={first_block.get('physical_scale', 0)}")
            
        else:
            print(f"  ❌ Ошибка получения данных: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("  ❌ Не удается подключиться к API серверу")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    
    print()

def test_pin_with_scale():
    """Тестируем закрепление блока с масштабом"""
    print("📌 Тестируем закрепление блока с физическим масштабом...")
    
    try:
        # Получаем первый незакрепленный блок
        response = requests.get(f"{API_URL}/layout/neo4j")
        if response.status_code != 200:
            print("  ❌ Не удается получить данные о блоках")
            return
            
        data = response.json()
        blocks = data.get('blocks', [])
        
        unpinned_block = None
        for block in blocks:
            if not block.get('is_pinned', False):
                unpinned_block = block
                break
        
        if not unpinned_block:
            print("  ❌ Нет незакрепленных блоков для тестирования")
            return
        
        block_id = unpinned_block['id']
        test_scale = 3  # 10^3 = 1 км
        
        print(f"  🔧 Закрепляем блок {block_id[:8]}... с масштабом {test_scale} (1 км)")
        
        # Закрепляем блок с масштабом
        response = requests.post(
            f"{API_URL}/api/blocks/{block_id}/pin_with_scale",
            json={"physical_scale": test_scale}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✅ Блок успешно закреплен: {result.get('message', 'OK')}")
            
            # Проверяем что блок действительно закреплен с правильным масштабом
            response = requests.get(f"{API_URL}/layout/neo4j")
            if response.status_code == 200:
                updated_data = response.json()
                updated_blocks = updated_data.get('blocks', [])
                
                updated_block = next((b for b in updated_blocks if b['id'] == block_id), None)
                if updated_block:
                    is_pinned = updated_block.get('is_pinned', False)
                    physical_scale = updated_block.get('physical_scale', 0)
                    
                    print(f"  {'✅' if is_pinned else '❌'} Блок {'закреплен' if is_pinned else 'не закреплен'}")
                    print(f"  {'✅' if physical_scale == test_scale else '❌'} Масштаб: {physical_scale} (ожидалось: {test_scale})")
                else:
                    print("  ❌ Не удается найти обновленный блок")
            else:
                print("  ❌ Не удается проверить результат")
                
        else:
            print(f"  ❌ Ошибка закрепления: {response.status_code}")
            try:
                error_data = response.json()
                print(f"    Детали: {error_data}")
            except:
                print(f"    Ответ: {response.text}")
                
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
    
    print()

if __name__ == "__main__":
    print("🚀 Тестирование функциональности физических масштабов")
    print("=" * 60)
    print()
    
    test_scale_utilities()
    test_api_endpoints() 
    test_pin_with_scale()
    
    print("✨ Тестирование завершено!") 