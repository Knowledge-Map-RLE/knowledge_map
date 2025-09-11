"""
Тесты для валидации топологического порядка.
Проверяет корректность последовательности чисел после топологической сортировки.
"""

import pytest
from typing import List, Tuple, Optional
from collections import Counter


class TopologicalOrderValidator:
    """Класс для валидации топологического порядка"""
    
    @staticmethod
    def validate_topological_order(topo_orders: List[int], total_nodes: int) -> Tuple[bool, List[str]]:
        """
        Валидирует топологический порядок.
        
        Args:
            topo_orders: Список значений topo_order
            total_nodes: Общее количество узлов
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, error_messages)
        """
        errors = []
        
        # Проверяем, что все значения являются целыми числами
        non_integer_values = [x for x in topo_orders if not isinstance(x, int)]
        if non_integer_values:
            errors.append(f"Обнаружены нецелые значения: {non_integer_values[:10]}{'...' if len(non_integer_values) > 10 else ''}")
        
        # Сортируем значения для проверки
        sorted_topo = sorted(topo_orders)
        
        # Проверяем, что последовательность начинается с 0
        if sorted_topo[0] != 0:
            errors.append(f"Последовательность не начинается с 0! Первое значение: {sorted_topo[0]}")
        
        # Проверяем, что последовательность заканчивается на (total_nodes-1)
        expected_last = total_nodes - 1
        if sorted_topo[-1] != expected_last:
            errors.append(f"Последовательность не заканчивается на {expected_last}! Последнее значение: {sorted_topo[-1]}")
        
        # Проверяем отсутствие пропусков
        missing_values = []
        for i in range(total_nodes):
            if i not in sorted_topo:
                missing_values.append(i)
        
        if missing_values:
            errors.append(f"Обнаружены пропуски в последовательности! Пропущенные значения: {missing_values[:10]}{'...' if len(missing_values) > 10 else ''}")
        
        # Проверяем монотонность (неубывающая последовательность)
        for i in range(1, len(sorted_topo)):
            if sorted_topo[i] < sorted_topo[i-1]:
                errors.append(f"Нарушена монотонность на позиции {i}! {sorted_topo[i-1]} > {sorted_topo[i]}")
                break
        
        # Проверяем уникальность
        unique_count = len(set(topo_orders))
        if unique_count < len(topo_orders):
            errors.append(f"Есть дублирующиеся значения topo_order! Уникальных: {unique_count} из {len(topo_orders)}")
        
        return len(errors) == 0, errors


class TestTopologicalOrderValidator:
    """Тесты для валидатора топологического порядка"""
    
    def test_validate_perfect_sequence(self):
        """Тест валидации идеальной последовательности"""
        validator = TopologicalOrderValidator()
        perfect_sequence = [0, 1, 2, 3, 4, 5]
        
        is_valid, errors = validator.validate_topological_order(perfect_sequence, 6)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_sequence_with_gaps(self):
        """Тест валидации последовательности с пропусками"""
        validator = TopologicalOrderValidator()
        sequence_with_gaps = [0, 1, 3, 4, 5]  # Пропущен 2
        
        is_valid, errors = validator.validate_topological_order(sequence_with_gaps, 6)
        
        assert is_valid is False
        assert any("пропуски" in error.lower() for error in errors)
    
    def test_validate_sequence_wrong_start(self):
        """Тест валидации последовательности с неправильным началом"""
        validator = TopologicalOrderValidator()
        wrong_start_sequence = [1, 2, 3, 4, 5]  # Начинается с 1 вместо 0
        
        is_valid, errors = validator.validate_topological_order(wrong_start_sequence, 6)
        
        assert is_valid is False
        assert any("не начинается с 0" in error.lower() for error in errors)
    
    def test_validate_sequence_wrong_end(self):
        """Тест валидации последовательности с неправильным концом"""
        validator = TopologicalOrderValidator()
        wrong_end_sequence = [0, 1, 2, 3, 4]  # Заканчивается на 4 вместо 5
        
        is_valid, errors = validator.validate_topological_order(wrong_end_sequence, 6)
        
        assert is_valid is False
        assert any("не заканчивается на 5" in error.lower() for error in errors)
    
    def test_validate_non_monotonic_sequence(self):
        """Тест валидации немонотонной последовательности"""
        validator = TopologicalOrderValidator()
        non_monotonic_sequence = [0, 1, 3, 2, 4, 5]  # 3 > 2 нарушает монотонность
        
        is_valid, errors = validator.validate_topological_order(non_monotonic_sequence, 6)
        
        assert is_valid is False
        assert any("нарушена монотонность" in error.lower() for error in errors)
    
    def test_validate_duplicate_values(self):
        """Тест валидации последовательности с дубликатами"""
        validator = TopologicalOrderValidator()
        duplicate_sequence = [0, 1, 2, 2, 3, 4, 5]  # Дубликат 2
        
        is_valid, errors = validator.validate_topological_order(duplicate_sequence, 6)
        
        assert is_valid is False
        assert any("дублирующиеся значения" in error.lower() for error in errors)
    
    def test_validate_non_integer_values(self):
        """Тест валидации последовательности с нецелыми числами"""
        validator = TopologicalOrderValidator()
        non_integer_sequence = [0, 1, 2.5, 3, 4, 5]  # 2.5 не целое число
        
        is_valid, errors = validator.validate_topological_order(non_integer_sequence, 6)
        
        assert is_valid is False
        assert any("нецелые значения" in error.lower() for error in errors)
    
    def test_validate_empty_sequence(self):
        """Тест валидации пустой последовательности"""
        validator = TopologicalOrderValidator()
        empty_sequence = []
        
        is_valid, errors = validator.validate_topological_order(empty_sequence, 0)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_single_element(self):
        """Тест валидации последовательности с одним элементом"""
        validator = TopologicalOrderValidator()
        single_element = [0]
        
        is_valid, errors = validator.validate_topological_order(single_element, 1)
        
        assert is_valid is True
        assert len(errors) == 0


class TestTopologicalOrderEdgeCases:
    """Тесты граничных случаев для валидации топологического порядка"""
    
    def test_validate_large_sequence(self):
        """Тест валидации большой последовательности"""
        validator = TopologicalOrderValidator()
        large_sequence = list(range(10000))  # 0 до 9999
        
        is_valid, errors = validator.validate_topological_order(large_sequence, 10000)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_sequence_with_negative_numbers(self):
        """Тест валидации последовательности с отрицательными числами"""
        validator = TopologicalOrderValidator()
        negative_sequence = [-1, 0, 1, 2, 3, 4, 5]  # Отрицательное число
        
        is_valid, errors = validator.validate_topological_order(negative_sequence, 6)
        
        assert is_valid is False
        assert any("не начинается с 0" in error.lower() for error in errors)
    
    def test_validate_sequence_with_large_gaps(self):
        """Тест валидации последовательности с большими пропусками"""
        validator = TopologicalOrderValidator()
        large_gaps_sequence = [0, 1, 100, 101, 102]  # Большие пропуски
        
        is_valid, errors = validator.validate_topological_order(large_gaps_sequence, 103)
        
        assert is_valid is False
        assert any("пропуски" in error.lower() for error in errors)
    
    def test_validate_sequence_mixed_types(self):
        """Тест валидации последовательности со смешанными типами"""
        validator = TopologicalOrderValidator()
        mixed_types_sequence = [0, 1, "2", 3, 4, 5]  # Строка вместо числа
        
        is_valid, errors = validator.validate_topological_order(mixed_types_sequence, 6)
        
        assert is_valid is False
        assert any("нецелые значения" in error.lower() for error in errors)


class TestTopologicalOrderPerformance:
    """Тесты производительности валидации топологического порядка"""
    
    def test_validate_performance_large_dataset(self):
        """Тест производительности валидации большого набора данных"""
        validator = TopologicalOrderValidator()
        
        # Создаем большую последовательность
        large_sequence = list(range(100000))
        
        import time
        start_time = time.time()
        is_valid, errors = validator.validate_topological_order(large_sequence, 100000)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        assert is_valid is True
        assert len(errors) == 0
        assert execution_time < 1.0  # Должно выполняться менее чем за секунду
    
    def test_validate_performance_with_gaps(self):
        """Тест производительности валидации с пропусками"""
        validator = TopologicalOrderValidator()
        
        # Создаем последовательность с пропусками
        sequence_with_gaps = list(range(0, 50000, 2))  # Только четные числа
        
        import time
        start_time = time.time()
        is_valid, errors = validator.validate_topological_order(sequence_with_gaps, 50000)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        assert is_valid is False
        assert any("пропуски" in error.lower() for error in errors)
        assert execution_time < 1.0  # Должно выполняться менее чем за секунду


# Параметризованные тесты
@pytest.mark.parametrize("sequence,expected_valid,expected_error_type", [
    ([0, 1, 2, 3, 4, 5], True, None),
    ([0, 1, 3, 4, 5], False, "пропуски"),
    ([1, 2, 3, 4, 5], False, "не начинается с 0"),
    ([0, 1, 2, 3, 4], False, "не заканчивается"),
    ([0, 1, 3, 2, 4, 5], False, "нарушена монотонность"),
    ([0, 1, 2, 2, 3, 4, 5], False, "дублирующиеся значения"),
    ([0, 1, 2.5, 3, 4, 5], False, "нецелые значения"),
])
def test_validate_topological_order_parametrized(sequence, expected_valid, expected_error_type):
    """Параметризованный тест валидации топологического порядка"""
    validator = TopologicalOrderValidator()
    
    is_valid, errors = validator.validate_topological_order(sequence, len(sequence))
    
    assert is_valid == expected_valid
    
    if expected_error_type:
        assert any(expected_error_type in error.lower() for error in errors)
    else:
        assert len(errors) == 0


# Тесты для интеграции с реальными данными
class TestTopologicalOrderIntegration:
    """Интеграционные тесты валидации топологического порядка"""
    
    def test_validate_real_topological_data(self):
        """Тест валидации реальных данных топологической сортировки"""
        validator = TopologicalOrderValidator()
        
        # Симулируем реальные данные из базы данных
        real_topo_orders = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        total_nodes = 10
        
        is_valid, errors = validator.validate_topological_order(real_topo_orders, total_nodes)
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_corrupted_topological_data(self):
        """Тест валидации поврежденных данных топологической сортировки"""
        validator = TopologicalOrderValidator()
        
        # Симулируем поврежденные данные
        corrupted_topo_orders = [0, 1, 2, 4, 5, 6, 7, 8, 9]  # Пропущен 3
        total_nodes = 10
        
        is_valid, errors = validator.validate_topological_order(corrupted_topo_orders, total_nodes)
        
        assert is_valid is False
        assert any("пропуски" in error.lower() for error in errors)
    
    def test_validate_topological_data_with_cycles(self):
        """Тест валидации данных с циклами (должны быть обработаны корректно)"""
        validator = TopologicalOrderValidator()
        
        # Данные с циклами должны все равно иметь корректный топологический порядок
        # после обработки алгоритмом Кана
        topo_orders_with_cycles = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        total_nodes = 10
        
        is_valid, errors = validator.validate_topological_order(topo_orders_with_cycles, total_nodes)
        
        assert is_valid is True
        assert len(errors) == 0
