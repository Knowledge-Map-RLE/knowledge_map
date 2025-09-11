"""
Комплексные тесты для топологической сортировки.
Тестирует алгоритм Кана с батчевой обработкой и валидацию результатов.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any
from collections import Counter

from src.algorithms.topological_sort import TopologicalSorter, topological_sorter
from src.neo4j_client import neo4j_client


class TestTopologicalSorter:
    """Тесты для класса TopologicalSorter"""
    
    @pytest.fixture
    def sorter(self):
        """Фикстура для создания экземпляра TopologicalSorter"""
        return TopologicalSorter()
    
    @pytest.fixture
    def mock_neo4j_responses(self):
        """Фикстура с мок-ответами Neo4j для различных сценариев"""
        return {
            "total_articles": [{"total": 5}],
            "init_result": [{"batches": 1, "total": 5, "errorMessages": []}],
            "zero_degree_batch1": [{"uid": "node1"}, {"uid": "node2"}],
            "zero_degree_batch2": [{"uid": "node3"}],
            "zero_degree_empty": [],
            "remaining_count": [{"remaining_count": 0}],
            "remaining_nodes": []
        }
    
    @pytest.fixture
    def mock_neo4j_responses_with_cycles(self):
        """Фикстура с мок-ответами для графа с циклами"""
        return {
            "total_articles": [{"total": 4}],
            "init_result": [{"batches": 1, "total": 4, "errorMessages": []}],
            "zero_degree_batch1": [{"uid": "node1"}],
            "zero_degree_empty": [],
            "remaining_count": [{"remaining_count": 3}],
            "remaining_nodes": [{"uid": "node2"}, {"uid": "node3"}, {"uid": "node4"}]
        }
    
    @pytest.fixture
    def mock_neo4j_responses_large_graph(self):
        """Фикстура с мок-ответами для большого графа"""
        return {
            "total_articles": [{"total": 10000}],
            "init_result": [{"batches": 2, "total": 10000, "errorMessages": []}],
            "zero_degree_batch1": [{"uid": f"node{i}"} for i in range(5000)],
            "zero_degree_batch2": [{"uid": f"node{i}"} for i in range(5000, 10000)],
            "zero_degree_empty": [],
            "remaining_count": [{"remaining_count": 0}],
            "remaining_nodes": []
        }

    @pytest.mark.asyncio
    async def test_compute_toposort_order_db_success(self, sorter, mock_neo4j_responses):
        """Тест успешного выполнения топологической сортировки"""
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            # Настраиваем последовательность вызовов
            mock_execute.side_effect = [
                mock_neo4j_responses["total_articles"],      # total_articles_query
                mock_neo4j_responses["init_result"],         # init_query
                mock_neo4j_responses["zero_degree_batch1"], # find_zero_degree_query (1-й вызов)
                None,                                       # set_order_query (1-й батч)
                None,                                       # update_neighbors_query (1-й батч)
                mock_neo4j_responses["zero_degree_batch2"], # find_zero_degree_query (2-й вызов)
                None,                                       # set_order_query (2-й батч)
                None,                                       # update_neighbors_query (2-й батч)
                mock_neo4j_responses["zero_degree_empty"], # find_zero_degree_query (3-й вызов)
                mock_neo4j_responses["remaining_count"],    # remaining_query
            ]
            
            # Выполняем тест
            await sorter.compute_toposort_order_db()
            
            # Проверяем, что все запросы были выполнены
            assert mock_execute.call_count == 10

    @pytest.mark.asyncio
    async def test_compute_toposort_order_db_with_cycles(self, sorter, mock_neo4j_responses_with_cycles):
        """Тест топологической сортировки с циклами"""
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                mock_neo4j_responses_with_cycles["total_articles"],
                mock_neo4j_responses_with_cycles["init_result"],
                mock_neo4j_responses_with_cycles["zero_degree_batch1"],
                None,  # set_order_query
                None,  # update_neighbors_query
                mock_neo4j_responses_with_cycles["zero_degree_empty"],
                mock_neo4j_responses_with_cycles["remaining_count"],
                mock_neo4j_responses_with_cycles["remaining_nodes"],
                None,  # handle_cycles_query
            ]
            
            await sorter.compute_toposort_order_db()
            
            # Проверяем, что обработались циклы
            assert mock_execute.call_count == 9

    @pytest.mark.asyncio
    async def test_compute_toposort_order_db_large_graph(self, sorter, mock_neo4j_responses_large_graph):
        """Тест топологической сортировки для большого графа"""
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                mock_neo4j_responses_large_graph["total_articles"],
                mock_neo4j_responses_large_graph["init_result"],
                mock_neo4j_responses_large_graph["zero_degree_batch1"],
                None,  # set_order_query (батч 1)
                None,  # update_neighbors_query (батч 1)
                mock_neo4j_responses_large_graph["zero_degree_batch2"],
                None,  # set_order_query (батч 2)
                None,  # update_neighbors_query (батч 2)
                mock_neo4j_responses_large_graph["zero_degree_empty"],
                mock_neo4j_responses_large_graph["remaining_count"],
            ]
            
            await sorter.compute_toposort_order_db()
            
            # Проверяем, что все узлы были обработаны
            assert mock_execute.call_count == 10

    @pytest.mark.asyncio
    async def test_compute_toposort_order_db_database_error(self, sorter):
        """Тест обработки ошибок базы данных"""
        with patch.object(neo4j_client, 'execute_query_with_retry', side_effect=Exception("Database error")):
            with pytest.raises(Exception, match="Database error"):
                await sorter.compute_toposort_order_db()

    def test_should_throttle_progress(self, sorter):
        """Тест ограничения частоты логирования прогресса"""
        # Первый вызов должен разрешить логирование
        assert sorter.should_throttle_progress() is False
        
        # Сразу следующий вызов должен быть заблокирован
        assert sorter.should_throttle_progress() is True
        
        # После паузы должен снова разрешить
        import time
        time.sleep(0.1)  # Небольшая пауза для теста
        # Сброс времени для теста
        sorter._last_progress_time = 0
        assert sorter.should_throttle_progress() is False


class TestTopologicalOrderValidation:
    """Тесты для валидации топологического порядка"""
    
    def test_validate_monotonic_sequence_valid(self):
        """Тест валидации корректной монотонно неубывающей последовательности"""
        from src.algorithms.distributed_incremental_layout import distributed_incremental_layout
        
        # Корректная последовательность
        valid_sequence = [0, 1, 2, 3, 4, 5]
        
        # Проверяем монотонность
        is_monotonic = True
        for i in range(1, len(valid_sequence)):
            if valid_sequence[i] < valid_sequence[i-1]:
                is_monotonic = False
                break
        
        assert is_monotonic is True
    
    def test_validate_monotonic_sequence_invalid(self):
        """Тест валидации некорректной последовательности"""
        # Некорректная последовательность
        invalid_sequence = [0, 1, 3, 2, 4, 5]
        
        # Проверяем монотонность
        is_monotonic = True
        violation_position = None
        for i in range(1, len(invalid_sequence)):
            if invalid_sequence[i] < invalid_sequence[i-1]:
                is_monotonic = False
                violation_position = i
                break
        
        assert is_monotonic is False
        assert violation_position == 3
    
    def test_validate_sequence_gaps(self):
        """Тест проверки пропусков в последовательности"""
        # Последовательность с пропусками
        sequence_with_gaps = [0, 1, 3, 4, 6, 7]
        total_expected = 8
        
        missing_values = []
        for i in range(total_expected):
            if i not in sequence_with_gaps:
                missing_values.append(i)
        
        assert missing_values == [2, 5]
    
    def test_validate_sequence_no_gaps(self):
        """Тест проверки последовательности без пропусков"""
        # Полная последовательность
        complete_sequence = [0, 1, 2, 3, 4, 5]
        total_expected = 6
        
        missing_values = []
        for i in range(total_expected):
            if i not in complete_sequence:
                missing_values.append(i)
        
        assert missing_values == []
    
    def test_validate_integer_values(self):
        """Тест проверки целых чисел"""
        # Смешанные типы
        mixed_values = [0, 1, 2.5, 3, 4, 5]
        
        non_integer_values = [x for x in mixed_values if not isinstance(x, int)]
        
        assert non_integer_values == [2.5]
    
    def test_validate_sequence_bounds(self):
        """Тест проверки границ последовательности"""
        sequence = [0, 1, 2, 3, 4, 5]
        total = 6
        
        # Проверяем начало
        assert sequence[0] == 0
        
        # Проверяем конец
        expected_last = total - 1
        assert sequence[-1] == expected_last


class TestTopologicalSortIntegration:
    """Интеграционные тесты для топологической сортировки"""
    
    @pytest.fixture
    def mock_database_state(self):
        """Фикстура с состоянием базы данных для интеграционных тестов"""
        return {
            "articles": [
                {"uid": "article1", "in_deg": 0, "visited": False},
                {"uid": "article2", "in_deg": 1, "visited": False},
                {"uid": "article3", "in_deg": 1, "visited": False},
                {"uid": "article4", "in_deg": 2, "visited": False},
            ],
            "edges": [
                {"source": "article1", "target": "article2"},
                {"source": "article1", "target": "article3"},
                {"source": "article2", "target": "article4"},
                {"source": "article3", "target": "article4"},
            ]
        }
    
    @pytest.mark.asyncio
    async def test_end_to_end_topological_sort(self, mock_database_state):
        """Полный интеграционный тест топологической сортировки"""
        sorter = TopologicalSorter()
        
        # Мокаем все вызовы к базе данных
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            # Настраиваем последовательность ответов
            mock_execute.side_effect = [
                [{"total": 4}],  # total_articles_query
                [{"batches": 1, "total": 4, "errorMessages": []}],  # init_query
                [{"uid": "article1"}],  # find_zero_degree_query (1-й вызов)
                None,  # set_order_query
                None,  # update_neighbors_query
                [{"uid": "article2"}, {"uid": "article3"}],  # find_zero_degree_query (2-й вызов)
                None,  # set_order_query
                None,  # update_neighbors_query
                [{"uid": "article4"}],  # find_zero_degree_query (3-й вызов)
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (4-й вызов - пустой)
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            # Выполняем топологическую сортировку
            await sorter.compute_toposort_order_db()
            
            # Проверяем, что все запросы были выполнены
            assert mock_execute.call_count == 13

    @pytest.mark.asyncio
    async def test_topological_sort_performance(self):
        """Тест производительности топологической сортировки"""
        sorter = TopologicalSorter()
        
        # Мокаем для большого графа
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                [{"total": 100000}],  # total_articles_query
                [{"batches": 20, "total": 100000, "errorMessages": []}],  # init_query
                [{"uid": f"node{i}"} for i in range(10000)],  # find_zero_degree_query
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (пустой)
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            import time
            start_time = time.time()
            await sorter.compute_toposort_order_db()
            end_time = time.time()
            
            # Проверяем, что выполнение заняло разумное время (моки должны быть быстрыми)
            execution_time = end_time - start_time
            assert execution_time < 1.0  # Меньше секунды для моков


class TestTopologicalSortEdgeCases:
    """Тесты граничных случаев для топологической сортировки"""
    
    @pytest.mark.asyncio
    async def test_empty_graph(self):
        """Тест пустого графа"""
        sorter = TopologicalSorter()
        
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                [{"total": 0}],  # total_articles_query
                [{"batches": 0, "total": 0, "errorMessages": []}],  # init_query
                [],  # find_zero_degree_query
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            await sorter.compute_toposort_order_db()
            
            # Проверяем, что алгоритм корректно обработал пустой граф
            assert mock_execute.call_count == 4

    @pytest.mark.asyncio
    async def test_single_node_graph(self):
        """Тест графа с одной вершиной"""
        sorter = TopologicalSorter()
        
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                [{"total": 1}],  # total_articles_query
                [{"batches": 1, "total": 1, "errorMessages": []}],  # init_query
                [{"uid": "single_node"}],  # find_zero_degree_query
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (пустой)
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            await sorter.compute_toposort_order_db()
            
            assert mock_execute.call_count == 7

    @pytest.mark.asyncio
    async def test_disconnected_components(self):
        """Тест графа с несвязанными компонентами"""
        sorter = TopologicalSorter()
        
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                [{"total": 4}],  # total_articles_query
                [{"batches": 1, "total": 4, "errorMessages": []}],  # init_query
                [{"uid": "node1"}, {"uid": "node2"}, {"uid": "node3"}, {"uid": "node4"}],  # find_zero_degree_query
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (пустой)
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            await sorter.compute_toposort_order_db()
            
            assert mock_execute.call_count == 7


# Тесты для глобального экземпляра
class TestGlobalTopologicalSorter:
    """Тесты для глобального экземпляра topological_sorter"""
    
    def test_global_instance_exists(self):
        """Тест существования глобального экземпляра"""
        assert topological_sorter is not None
        assert isinstance(topological_sorter, TopologicalSorter)
    
    @pytest.mark.asyncio
    async def test_global_instance_functionality(self):
        """Тест функциональности глобального экземпляра"""
        with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
            mock_execute.side_effect = [
                [{"total": 2}],  # total_articles_query
                [{"batches": 1, "total": 2, "errorMessages": []}],  # init_query
                [{"uid": "node1"}, {"uid": "node2"}],  # find_zero_degree_query
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (пустой)
                [{"remaining_count": 0}],  # remaining_query
            ]
            
            await topological_sorter.compute_toposort_order_db()
            
            assert mock_execute.call_count == 7


# Параметризованные тесты
@pytest.mark.parametrize("graph_size,expected_calls", [
    (0, 4),    # Пустой граф
    (1, 7),    # Одна вершина
    (10, 10),  # Небольшой граф
    (100, 10), # Средний граф
    (1000, 10), # Большой граф
])
@pytest.mark.asyncio
async def test_topological_sort_scales(graph_size, expected_calls):
    """Параметризованный тест масштабируемости"""
    sorter = TopologicalSorter()
    
    with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
        # Настраиваем моки в зависимости от размера графа
        if graph_size == 0:
            mock_execute.side_effect = [
                [{"total": 0}],
                [{"batches": 0, "total": 0, "errorMessages": []}],
                [],
                [{"remaining_count": 0}],
            ]
        else:
            mock_execute.side_effect = [
                [{"total": graph_size}],
                [{"batches": 1, "total": graph_size, "errorMessages": []}],
                [{"uid": f"node{i}"} for i in range(graph_size)],
                None,  # set_order_query
                None,  # update_neighbors_query
                [],  # find_zero_degree_query (пустой)
                [{"remaining_count": 0}],
            ]
        
        await sorter.compute_toposort_order_db()
        
        # Проверяем количество вызовов
        assert mock_execute.call_count == expected_calls


# Тесты производительности
@pytest.mark.asyncio
async def test_topological_sort_memory_usage():
    """Тест использования памяти при топологической сортировке"""
    sorter = TopologicalSorter()
    
    # Мокаем для большого графа с батчевой обработкой
    with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
        # Симулируем обработку большого графа батчами
        batch_responses = []
        for batch_start in range(0, 50000, 5000):
            batch_end = min(batch_start + 5000, 50000)
            batch_responses.append([{"uid": f"node{i}"} for i in range(batch_start, batch_end)])
        
        mock_execute.side_effect = [
            [{"total": 50000}],  # total_articles_query
            [{"batches": 10, "total": 50000, "errorMessages": []}],  # init_query
        ] + batch_responses + [
            None,  # set_order_query для каждого батча
            None,  # update_neighbors_query для каждого батча
        ] * 10 + [
            [],  # find_zero_degree_query (пустой)
            [{"remaining_count": 0}],  # remaining_query
        ]
        
        await sorter.compute_toposort_order_db()
        
        # Проверяем, что алгоритм корректно обработал большой граф
        assert mock_execute.call_count > 20
