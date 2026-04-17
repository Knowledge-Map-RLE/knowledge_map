"""
Обобщение структуры всех XML файлов.
"""
import gzip
import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import time

# ================== Конфигурация ==================

LOCAL_DIR = Path("D:/Данные/PubMed")
OUTPUT_FILE = Path("./logs/pubmed_baseline_generalization_structure_all_xml.log")
LOG_FILE = Path("./logs/pubmed_baseline_generalization_structure_all_xml_processing.log")
MAX_WORKERS = min(cpu_count(), 4)  # Ограничиваем количество процессов

# ================== Логирование ==================

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== Функции анализа XML ==================

def get_xml_paths(element, current_path=""):
    """
    Рекурсивно извлекает все XML пути из элемента.
    Оптимизированная версия с использованием генератора для экономии памяти.
    
    Args:
        element: XML элемент
        current_path: текущий путь (для рекурсии)
    
    Yields:
        str: XML путь
    """
    # Добавляем текущий путь
    if current_path:
        yield current_path
    
    # Обрабатываем дочерние элементы
    for child in element:
        child_path = f"{current_path} → {child.tag}" if current_path else child.tag
        yield from get_xml_paths(child, child_path)

def analyze_xml_file(file_path):
    """
    Анализирует один XML файл и извлекает все уникальные пути.
    Обрабатывает .xml.gz файлы на лету без распаковки.
    Оптимизированная версия с использованием генератора.
    
    Args:
        file_path: путь к XML файлу
    
    Returns:
        set: множество уникальных XML путей
    """
    logger.info(f"Анализируем файл: {file_path.name}")
    
    try:
        # Определяем, нужно ли распаковывать gzip
        if file_path.suffix == '.gz':
            # Обрабатываем .xml.gz файл на лету
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                # Парсим XML напрямую из потока
                root = ET.parse(f).getroot()
        else:
            # Обычный XML файл
            with open(file_path, 'r', encoding='utf-8') as f:
                root = ET.parse(f).getroot()
        
        # Извлекаем все пути используя генератор для экономии памяти
        paths = set(get_xml_paths(root))
        
        logger.info(f"Найдено {len(paths)} уникальных путей в {file_path.name}")
        return paths
        
    except Exception as e:
        logger.error(f"Ошибка при анализе {file_path.name}: {e}")
        return set()

def load_existing_paths():
    """
    Загружает уже существующие пути из файла результатов.
    
    Returns:
        set: множество существующих путей
    """
    if not OUTPUT_FILE.exists():
        return set()
    
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except Exception as e:
        logger.warning(f"Не удалось загрузить существующие пути: {e}")
        return set()

def save_paths_to_file(paths):
    """
    Сохраняет отсортированные пути в файл результатов.
    
    Args:
        paths: множество путей для сохранения
    """
    sorted_paths = sorted(paths)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for path in sorted_paths:
            f.write(f"{path}\n")
    logger.info(f"Сохранено {len(sorted_paths)} уникальных путей в {OUTPUT_FILE}")

def analyze_all_xml_files():
    """
    Анализирует все XML файлы в директории с параллелизацией и сохраняет результаты.
    Результаты сохраняются после обработки каждого файла для предотвращения потери данных.
    Сложность: O(n * m * d) где n - количество файлов, m - среднее количество элементов в файле, d - средняя глубина
    """
    start_time = time.time()
    
    if not LOCAL_DIR.exists():
        logger.error(f"Директория {LOCAL_DIR} не существует")
        return
    
    # Находим все XML файлы
    xml_files = list(LOCAL_DIR.glob("*.xml.gz")) + list(LOCAL_DIR.glob("*.xml"))
    
    if not xml_files:
        logger.error(f"Не найдено XML файлов в {LOCAL_DIR}")
        return
    
    logger.info(f"Найдено {len(xml_files)} XML файлов для анализа")
    logger.info(f"Используем {MAX_WORKERS} процессов для параллельной обработки")
    
    # Загружаем существующие пути
    all_paths = load_existing_paths()
    logger.info(f"Загружено {len(all_paths)} существующих путей")
    
    # Параллельная обработка файлов
    processed_count = 0
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Запускаем задачи
        future_to_file = {executor.submit(analyze_xml_file, xml_file): xml_file 
                         for xml_file in xml_files}
        
        # Собираем результаты по мере готовности
        for future in as_completed(future_to_file):
            xml_file = future_to_file[future]
            try:
                file_paths = future.result()
                all_paths.update(file_paths)
                processed_count += 1
                
                # Сохраняем результаты после каждого файла
                save_paths_to_file(all_paths)
                
                if processed_count % 10 == 0:  # Логируем каждые 10 файлов
                    logger.info(f"Обработано {processed_count}/{len(xml_files)} файлов")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке {xml_file.name}: {e}")
    
    logger.info(f"Всего найдено {len(all_paths)} уникальных XML путей")
    
    elapsed_time = time.time() - start_time
    logger.info(f"Обработка завершена за {elapsed_time:.2f} секунд")
    logger.info(f"Результаты сохранены в {OUTPUT_FILE}")
    logger.info(f"Первые 10 путей:")
    sorted_paths = sorted(all_paths)
    for i, path in enumerate(sorted_paths[:10]):
        logger.info(f"  {i+1}. {path}")

if __name__ == "__main__":
    analyze_all_xml_files()