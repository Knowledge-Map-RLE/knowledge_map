#!/usr/bin/env python3
"""
Тесты для проверки тестовых данных в Neo4j
Проверяет корректность созданных блоков, связей, пользователей и тегов
"""

import sys
import os
import unittest
from typing import List, Dict, Any

# Добавляем путь к api папке для импорта моделей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from neomodel import config, db
from models import User, Block, Tag, LinkMetadata

# Настройка подключения к Neo4j
NEO4J_URL = os.getenv('NEO4J_URL', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

config.DATABASE_URL = f'bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{NEO4J_URL.replace("bolt://", "")}'


class TestNeo4jData(unittest.TestCase):
    """Тесты для проверки данных в Neo4j"""
    
    @classmethod
    def setUpClass(cls):
        """Настройка перед запуском всех тестов"""
        try:
            # Проверяем подключение к Neo4j
            db.cypher_query("RETURN 1")
            print("✓ Подключение к Neo4j установлено")
        except Exception as e:
            cls.fail(f"Не удалось подключиться к Neo4j: {e}")
    
    def test_01_database_connection(self):
        """Тест подключения к базе данных"""
        try:
            result, _ = db.cypher_query("RETURN 1 as test")
            self.assertEqual(result[0][0], 1)
            print("✓ База данных доступна")
        except Exception as e:
            self.fail(f"Ошибка подключения: {e}")
    
    def test_02_users_exist(self):
        """Тест существования пользователей"""
        users = User.nodes.all()
        self.assertGreater(len(users), 0, "В базе должен быть хотя бы один пользователь")
        
        print(f"✓ Найдено пользователей: {len(users)}")
        
        # Проверяем что у пользователей есть все обязательные поля
        for user in users:
            self.assertIsNotNone(user.login, "У пользователя должен быть login")
            self.assertIsNotNone(user.nickname, "У пользователя должен быть nickname")
            self.assertIsNotNone(user.password, "У пользователя должен быть password")
            
        print("✓ Все пользователи имеют обязательные поля")
    
    def test_03_blocks_exist(self):
        """Тест существования блоков"""
        blocks = Block.nodes.all()
        self.assertGreaterEqual(len(blocks), 50, "В базе должно быть минимум 50 блоков")
        
        print(f"✓ Найдено блоков: {len(blocks)}")
        
        # Проверяем что у блоков есть все обязательные поля
        layers = set()
        levels = set()
        
        for block in blocks:
            self.assertIsNotNone(block.content, "У блока должен быть content")
            self.assertIsNotNone(block.layer, "У блока должен быть layer")
            self.assertIsNotNone(block.level, "У блока должен быть level")
            
            layers.add(block.layer)
            levels.add(block.level)
        
        print(f"✓ Блоки распределены по слоям: {sorted(layers)}")
        print(f"✓ Блоки распределены по уровням: {sorted(levels)}")
        
        # Проверяем разнообразие слоев и уровней
        self.assertGreater(len(layers), 1, "Блоки должны быть в разных слоях")
        self.assertGreater(len(levels), 1, "Блоки должны быть на разных уровнях")
    
    def test_04_links_exist(self):
        """Тест существования связей"""
        links = LinkMetadata.nodes.all()
        self.assertGreater(len(links), 0, "В базе должны быть связи")
        
        print(f"✓ Найдено связей: {len(links)}")
        
        # Проверяем что у связей есть все обязательные поля
        for link in links:
            self.assertIsNotNone(link.source_id, "У связи должен быть source_id")
            self.assertIsNotNone(link.target_id, "У связи должен быть target_id")
            self.assertNotEqual(link.source_id, link.target_id, "Связь не должна указывать на тот же блок")
        
        print("✓ Все связи имеют корректные source_id и target_id")
    
    def test_05_tags_exist(self):
        """Тест существования тегов"""
        tags = Tag.nodes.all()
        self.assertGreater(len(tags), 0, "В базе должны быть теги")
        
        print(f"✓ Найдено тегов: {len(tags)}")
        
        # Проверяем что у тегов есть текст
        tag_texts = []
        for tag in tags:
            self.assertIsNotNone(tag.text, "У тега должен быть text")
            self.assertNotEqual(tag.text.strip(), "", "Текст тега не должен быть пустым")
            tag_texts.append(tag.text)
        
        # Проверяем уникальность тегов
        self.assertEqual(len(tag_texts), len(set(tag_texts)), "Теги должны быть уникальными")
        print("✓ Все теги уникальны и имеют текст")
    
    def test_06_block_user_relationships(self):
        """Тест связей блоков с пользователями"""
        blocks = Block.nodes.all()
        blocks_with_users = 0
        
        for block in blocks:
            creator = block.created_by.single()
            if creator:
                blocks_with_users += 1
                self.assertIsInstance(creator, User, "Создатель блока должен быть пользователем")
        
        self.assertGreater(blocks_with_users, 0, "Хотя бы у некоторых блоков должен быть создатель")
        
        coverage = (blocks_with_users / len(blocks)) * 100
        print(f"✓ {blocks_with_users} из {len(blocks)} блоков имеют создателя ({coverage:.1f}%)")
    
    def test_07_tag_block_relationships(self):
        """Тест связей тегов с блоками"""
        tags = Tag.nodes.all()
        tags_with_blocks = 0
        total_tag_assignments = 0
        
        for tag in tags:
            tagged_blocks = tag.block.all()
            if tagged_blocks:
                tags_with_blocks += 1
                total_tag_assignments += len(tagged_blocks)
        
        self.assertGreater(tags_with_blocks, 0, "Хотя бы некоторые теги должны быть назначены блокам")
        
        coverage = (tags_with_blocks / len(tags)) * 100
        avg_assignments = total_tag_assignments / len(tags) if tags else 0
        
        print(f"✓ {tags_with_blocks} из {len(tags)} тегов назначены блокам ({coverage:.1f}%)")
        print(f"✓ Среднее количество назначений на тег: {avg_assignments:.1f}")
    
    def test_08_graph_acyclicity(self):
        """Тест ацикличности графа"""
        # Проверяем что граф ациклический через Cypher запрос
        query = """
        MATCH path = (start:Block)-[:LINK_TO*]->(start)
        RETURN COUNT(path) as cycles
        """
        
        result, _ = db.cypher_query(query)
        cycles_count = result[0][0] if result else 0
        
        self.assertEqual(cycles_count, 0, f"В графе не должно быть циклов, найдено: {cycles_count}")
        print("✓ Граф является ациклическим")
    
    def test_09_data_consistency(self):
        """Тест консистентности данных"""
        # Проверяем что все source_id и target_id в LinkMetadata соответствуют реальным блокам
        links = LinkMetadata.nodes.all()
        block_ids = {getattr(block, 'element_id') for block in Block.nodes.all()}
        
        invalid_links = 0
        for link in links:
            if link.source_id not in block_ids:
                invalid_links += 1
                print(f"⚠️  Связь {getattr(link, 'element_id')} ссылается на несуществующий source_id: {link.source_id}")
            
            if link.target_id not in block_ids:
                invalid_links += 1
                print(f"⚠️  Связь {getattr(link, 'element_id')} ссылается на несуществующий target_id: {link.target_id}")
        
        self.assertEqual(invalid_links, 0, f"Найдены некорректные ссылки в связях: {invalid_links}")
        print("✓ Все связи ссылаются на существующие блоки")
    
    def test_10_performance_check(self):
        """Тест производительности запросов"""
        import time
        
        # Тест времени выполнения основных запросов
        start_time = time.time()
        blocks = Block.nodes.all()
        blocks_time = time.time() - start_time
        
        start_time = time.time()
        links = LinkMetadata.nodes.all()
        links_time = time.time() - start_time
        
        start_time = time.time()
        users = User.nodes.all()
        users_time = time.time() - start_time
        
        print(f"✓ Время запроса блоков: {blocks_time:.3f}s ({len(blocks)} блоков)")
        print(f"✓ Время запроса связей: {links_time:.3f}s ({len(links)} связей)")
        print(f"✓ Время запроса пользователей: {users_time:.3f}s ({len(users)} пользователей)")
        
        # Проверяем что запросы выполняются за разумное время
        self.assertLess(blocks_time, 5.0, "Запрос блоков должен выполняться быстро")
        self.assertLess(links_time, 5.0, "Запрос связей должен выполняться быстро")
        self.assertLess(users_time, 5.0, "Запрос пользователей должен выполняться быстро")


class TestDataStatistics(unittest.TestCase):
    """Тесты для получения статистики данных"""
    
    def test_data_distribution(self):
        """Тест распределения данных"""
        blocks = Block.nodes.all()
        
        # Распределение по слоям
        layer_distribution = {}
        level_distribution = {}
        
        for block in blocks:
            layer = block.layer
            level = block.level
            
            layer_distribution[layer] = layer_distribution.get(layer, 0) + 1
            level_distribution[level] = level_distribution.get(level, 0) + 1
        
        print("\n📊 Статистика распределения блоков:")
        print(f"По слоям: {dict(sorted(layer_distribution.items()))}")
        print(f"По уровням: {dict(sorted(level_distribution.items()))}")
        
        # Проверяем что распределение относительно равномерное
        if layer_distribution:
            min_layer_count = min(layer_distribution.values())
            max_layer_count = max(layer_distribution.values())
            ratio = max_layer_count / min_layer_count if min_layer_count > 0 else float('inf')
            
            self.assertLess(ratio, 5.0, f"Распределение по слоям слишком неравномерное: {ratio:.1f}")
            print(f"✓ Распределение по слоям относительно равномерное (ratio: {ratio:.1f})")
    
    def test_connectivity_statistics(self):
        """Тест статистики связности графа"""
        blocks = Block.nodes.all()
        links = LinkMetadata.nodes.all()
        
        if not blocks:
            self.skipTest("Нет блоков для анализа")
        
        # Подсчитываем степени вершин
        out_degrees = {}  # исходящие связи
        in_degrees = {}   # входящие связи
        
        # Инициализируем все блоки с нулевой степенью
        for block in blocks:
            block_id = getattr(block, 'element_id')
            out_degrees[block_id] = 0
            in_degrees[block_id] = 0
        
        # Подсчитываем степени
        for link in links:
            if link.source_id in out_degrees:
                out_degrees[link.source_id] += 1
            if link.target_id in in_degrees:
                in_degrees[link.target_id] += 1
        
        # Статистика
        total_out = sum(out_degrees.values())
        total_in = sum(in_degrees.values())
        avg_out = total_out / len(blocks) if blocks else 0
        avg_in = total_in / len(blocks) if blocks else 0
        
        isolated_blocks = sum(1 for block_id in out_degrees 
                             if out_degrees[block_id] == 0 and in_degrees[block_id] == 0)
        
        print(f"\n🔗 Статистика связности:")
        print(f"Всего связей: {len(links)}")
        print(f"Средняя исходящая степень: {avg_out:.2f}")
        print(f"Средняя входящая степень: {avg_in:.2f}")
        print(f"Изолированных блоков: {isolated_blocks} из {len(blocks)}")
        
        # Проверяем что граф достаточно связный
        connectivity_ratio = (len(blocks) - isolated_blocks) / len(blocks) if blocks else 0
        self.assertGreater(connectivity_ratio, 0.7, f"Слишком много изолированных блоков: {isolated_blocks}")
        print(f"✓ Связность графа: {connectivity_ratio:.1%}")


def run_tests():
    """Запускает все тесты"""
    print("=== Тестирование данных Neo4j ===\n")
    
    # Создаем тестовый набор
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем тесты в порядке важности
    suite.addTests(loader.loadTestsFromTestCase(TestNeo4jData))
    suite.addTests(loader.loadTestsFromTestCase(TestDataStatistics))
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Выводим итоговую статистику
    print(f"\n=== Результаты тестирования ===")
    print(f"Запущено тестов: {result.testsRun}")
    print(f"Ошибки: {len(result.errors)}")
    print(f"Неудачи: {len(result.failures)}")
    
    if result.errors:
        print("\n❌ Ошибки:")
        for test, error in result.errors:
            print(f"  {test}: {error.strip()}")
    
    if result.failures:
        print("\n❌ Неудачи:")
        for test, failure in result.failures:
            print(f"  {test}: {failure.strip()}")
    
    success = len(result.errors) == 0 and len(result.failures) == 0
    
    if success:
        print("\n✅ Все тесты прошли успешно!")
    else:
        print(f"\n❌ Тесты завершились с ошибками")
    
    return success


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1) 