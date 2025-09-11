"""
Модуль для сохранения изолированных вершин в файл
"""

import logging
from pathlib import Path
from typing import Set, List

logger = logging.getLogger(__name__)

class IsolatedVerticesManager:
    """Менеджер для сохранения изолированных вершин в файл"""
    
    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.isolated_file = self.log_dir / "isolated_vertices.txt"
        self._isolated_vertices: Set[str] = set()
        self._load_isolated_vertices()
    
    def _load_isolated_vertices(self) -> None:
        """Загружает список изолированных вершин из файла"""
        if self.isolated_file.exists():
            try:
                with open(self.isolated_file, 'r', encoding='utf-8') as f:
                    self._isolated_vertices = set(line.strip() for line in f if line.strip())
                logger.info(f"Загружено {len(self._isolated_vertices)} изолированных вершин из файла")
            except Exception as e:
                logger.warning(f"Ошибка при загрузке изолированных вершин: {e}")
                self._isolated_vertices = set()
        else:
            logger.info("Файл с изолированными вершинами не найден, начинаем с пустого списка")
    
    def save_isolated_vertices(self, isolated_pmids: List[str]) -> None:
        """
        Сохраняет список изолированных вершин в файл
        
        Args:
            isolated_pmids: Список PMID изолированных вершин
        """
        if not isolated_pmids:
            logger.info("Нет изолированных вершин для сохранения")
            return
        
        # Добавляем новые изолированные вершины в наш список
        new_isolated = set(isolated_pmids) - self._isolated_vertices
        self._isolated_vertices.update(isolated_pmids)
        
        if new_isolated:
            logger.info(f"Добавлено {len(new_isolated)} новых изолированных вершин")
            self._save_to_file()
        else:
            logger.info("Все изолированные вершины уже сохранены")
    
    def _save_to_file(self) -> None:
        """Сохраняет список изолированных вершин в файл"""
        try:
            with open(self.isolated_file, 'w', encoding='utf-8') as f:
                for pmid in sorted(self._isolated_vertices):
                    f.write(f"{pmid}\n")
            logger.info(f"Сохранено {len(self._isolated_vertices)} изолированных вершин в файл")
        except Exception as e:
            logger.error(f"Ошибка при сохранении изолированных вершин: {e}")
    
    def get_cached_isolated_count(self) -> int:
        """Возвращает количество изолированных вершин из кэша"""
        return len(self._isolated_vertices)
    
    def cleanup_isolated_vertices(self) -> None:
        """Очищает файл с изолированными вершинами (для тестирования)"""
        if self.isolated_file.exists():
            self.isolated_file.unlink()
            logger.info("Файл с изолированными вершинами удален")
        
        self._isolated_vertices.clear()
        logger.info("Кэш изолированных вершин очищен")
