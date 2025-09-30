"""
Обобщение структуры всех XML файлов из PMC OA bulk архивов.
"""
import gzip
import logging
import os
import tarfile
from lxml import etree
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import time
from collections import defaultdict

# ================== Конфигурация ==================

LOCAL_DIR = Path("E:/Данные/PubMed_Central")
OUTPUT_FILE = Path("./logs/pmc_oa_bulk_generalization_structure_all_xml.log")
LOG_FILE = Path("./logs/pmc_oa_bulk_generalization_structure_all_xml_processing.log")
MAX_WORKERS = min(cpu_count(), 8)  # Увеличиваем количество процессов для ускорения

# ================== Логирование ==================

ROOT_DIR = Path(__file__).resolve().parents[1]  # worker_data_to_db
OUTPUT_FILE = ROOT_DIR / "logs" / "pmc_oa_bulk_generalization_structure_all_xml.log"
LOG_FILE = ROOT_DIR / "logs" / "pmc_oa_bulk_generalization_structure_all_xml_processing.log"

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

def strip_namespace(name: str) -> str:
    """Удаляет namespace из имени тега/атрибута: '{ns}tag' -> 'tag'."""
    if not name:
        return name
    if '}' in name:
        return name.split('}', 1)[1]
    return name

# Атрибутные окончания цепочек, для которых сохраняем путь без значения
ATTR_PATH_SUFFIXES_NO_VALUE = {
    "article → @id",
    "sub-article → @id",
    "sub-article → front-stub → related-article → @id",
    "ack → @id",
    "ack → p → @id",
    "abbrev → @id",
    "abbrev → @title",
    "award-id → @rid",
    "→ @href",
    "→ @id",
    "ext-link → @id",
    "xref → @rid",
    "ref → @id",
    "mixed-citation → @id",
    "supplementary-material → @id",
    "sec → @id",
    "fig → @id",
    "contrib → @id",
    "kwd → @id",
    "aff → @id",
    "table-wrap → @id",
    "app → @id",
    "fn → @id",
    "fn-group → @id",
    "term → @id",
    "related-object → @source-id",
    "related-article → @page",
    "issue → @seq",
    "corresp → @id",
    "boxed-text → @id",
    "abstract → @id",
    "graphic → @id",
    "table → @id",
    "sec → p → @id",
    "term → @id",
    "def → @id",
    "body → @id",
}

def should_omit_attribute_value(path_without_value: str, attr_name: str) -> bool:
    """Возвращает True, если для данной цепочки следует не записывать значение атрибута.

    path_without_value ожидается в формате: "... → @attr" (без значения).
    """
    # Любой href без значения
    if attr_name.lower() == "href":
        return True
    # Совпадение по вхождению (подстрока может быть не в конце пути)
    for fragment in ATTR_PATH_SUFFIXES_NO_VALUE:
        if fragment in path_without_value:
            return True
    return False

def get_xml_paths(element, current_path=""):
    """
    Рекурсивно извлекает все XML пути из элемента.
    Оптимизированная версия с использованием генератора для экономии памяти.
    Пропускает все элементы math и их дочерние элементы.
    Исправлено для работы с lxml.
    
    Args:
        element: XML элемент
        current_path: текущий путь (для рекурсии)
    
    Yields:
        str: XML путь
    """
    # Пропускаем элементы math и любые теги, содержащие подстроки 'formula'/'mathml'/'math'
    tag_name = strip_namespace(element.tag or '')
    tag_lower = tag_name.lower()
    if (
        tag_lower == 'math'
        or 'formula' in tag_lower
        or 'mathml' in tag_lower
        or 'math' in tag_lower
    ):
        return
    
    # Добавляем текущий путь
    if current_path:
        yield current_path
    
    # Добавляем атрибуты текущего элемента как узлы цепочки вида: "… → @attr=value"
    if element.attrib:
        for raw_attr, raw_val in element.attrib.items():
            attr_name = strip_namespace(raw_attr)
            # Фильтрация по правилам исключения
            attr_lower = attr_name.lower()
            if attr_lower == 'math' or 'formula' in attr_lower or 'mathml' in attr_lower or 'math' in attr_lower:
                continue
            base_path = current_path if current_path else tag_name
            path_without_value = f"{base_path} → @{attr_name}"
            if should_omit_attribute_value(path_without_value, attr_name):
                yield path_without_value
            else:
                value_str = str(raw_val)
                # Усечение слишком длинных значений для лога
                if len(value_str) > 512:
                    value_str = value_str[:512] + '…'
                yield f"{path_without_value}={value_str}"
    
    # Обрабатываем дочерние элементы - исправлено для lxml
    try:
        # Безопасный способ итерации по дочерним элементам lxml
        for child in element.iterchildren():
            # Пропускаем дочерние элементы math и любые *formula*
            child_tag = strip_namespace(child.tag or '')
            child_tag_lower = child_tag.lower()
            if (
                child_tag_lower == 'math'
                or 'formula' in child_tag_lower
                or 'mathml' in child_tag_lower
                or 'math' in child_tag_lower
            ):
                continue
            child_path = f"{current_path} → {child_tag}" if current_path else child_tag
            yield from get_xml_paths(child, child_path)
    except Exception as e:
        # Если не удалось итерировать по дочерним элементам, пробуем альтернативный способ
        try:
            # Альтернативный способ через xpath
            children = element.xpath('./*')
            for child in children:
                child_tag = strip_namespace(child.tag or '')
                child_tag_lower = child_tag.lower()
                if (
                    child_tag_lower == 'math'
                    or 'formula' in child_tag_lower
                    or 'mathml' in child_tag_lower
                    or 'math' in child_tag_lower
                ):
                    continue
                child_path = f"{current_path} → {child_tag}" if current_path else child_tag
                yield from get_xml_paths(child, child_path)
        except Exception as e2:
            # Если и это не сработало, пропускаем
            logger.debug(f"Не удалось обработать дочерние элементы: {e}, {e2}")
            pass

# Функция analyze_xml_from_tar удалена, так как не используется в основном коде

def analyze_tar_archive(tar_path):
    """
    Анализирует один tar.gz архив и извлекает все пути из всех XML файлов с подсчётом частоты.
    Оптимизированная версия с использованием defaultdict для ускорения.
    
    Args:
        tar_path: путь к tar.gz архиву
    
    Returns:
        dict: словарь с путями и их частотами {путь: количество_вхождений}
    """
    logger.info(f"Анализируем архив: {tar_path.name}")
    
    # Используем defaultdict для ускорения операций
    path_counts = defaultdict(int)
    
    try:
        with tarfile.open(tar_path, 'r:gz') as tar:
            # Получаем список всех XML файлов в архиве
            xml_members = [member for member in tar.getmembers() 
                          if member.isfile() and member.name.endswith('.xml')]
            
            logger.info(f"Найдено {len(xml_members)} XML файлов в {tar_path.name}")
            
            # Анализируем каждый XML файл
            for xml_member in xml_members:
                try:
                    xml_file = tar.extractfile(xml_member)
                    if xml_file is None:
                        continue
                    
                    # Парсим XML с lxml (быстрее чем ElementTree)
                    # Используем более быстрый парсер для больших файлов
                    parser = etree.XMLParser(
                        recover=True, 
                        huge_tree=True,
                        strip_cdata=False,
                        resolve_entities=False,
                        remove_blank_text=True  # Удаляем пустые текстовые узлы
                    )
                    root = etree.parse(xml_file, parser).getroot()
                    
                    # Извлекаем пути и считаем их (defaultdict автоматически создаёт ключи)
                    # Используем итеративный подход для экономии памяти
                    try:
                        for path in get_xml_paths(root):
                            path_counts[path] += 1
                    except Exception as path_error:
                        logger.warning(f"Ошибка при извлечении путей из {xml_member.name}: {path_error}")
                        continue
                    finally:
                        # Принудительная очистка памяти для больших файлов
                        del root
                    
                except Exception as e:
                    logger.warning(f"Ошибка при анализе {xml_member.name}: {e}")
                    continue
        
        logger.info(f"Найдено {len(path_counts)} уникальных путей в {tar_path.name}")
        return dict(path_counts)  # Конвертируем обратно в обычный dict
        
    except Exception as e:
        logger.error(f"Ошибка при анализе архива {tar_path.name}: {e}")
        return {}

def load_existing_paths():
    """
    Загружает уже существующие пути из файла результатов с их счётчиками.
    
    Returns:
        dict: словарь с путями и их частотами {путь: количество_вхождений}
    """
    if not OUTPUT_FILE.exists():
        return {}
    
    try:
        path_counts = {}
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Парсим строку формата "(число) путь"
                if line.startswith('(') and ') ' in line:
                    try:
                        # Находим закрывающую скобку
                        end_bracket = line.find(') ')
                        if end_bracket > 0:
                            count_str = line[1:end_bracket]
                            path = line[end_bracket + 2:]  # +2 для пропуска ") "
                            count = int(count_str)
                            path_counts[path] = count
                    except (ValueError, IndexError):
                        # Если не удалось распарсить, считаем как старый формат без счётчика
                        path_counts[line] = 1
                else:
                    # Старый формат без счётчика
                    path_counts[line] = 1
        
        return path_counts
    except Exception as e:
        logger.warning(f"Не удалось загрузить существующие пути: {e}")
        return {}

def save_paths_to_file(path_counts):
    """
    Сохраняет отсортированные пути с их счётчиками в файл результатов.
    Оптимизированная версия с батчевой записью.
    
    Args:
        path_counts: словарь с путями и их частотами {путь: количество_вхождений}
    """
    # Фильтруем строки путей, чтобы исключить любые содержащие 'math' или 'formula'
    lower_exclude = ('mathml', 'math', 'formula')
    filtered_path_counts = {
        path: count for path, count in path_counts.items()
        if all(excl not in path.lower() for excl in lower_exclude)
    }
    
    # Сортируем по пути
    sorted_paths = sorted(filtered_path_counts.items())
    
    # Батчевая запись для ускорения
    with open(OUTPUT_FILE, 'w', encoding='utf-8', buffering=8192) as f:
        # Подготавливаем все строки заранее
        lines = [f"({count}) {path}\n" for path, count in sorted_paths]
        f.writelines(lines)
    
    logger.info(f"Сохранено {len(sorted_paths)} уникальных путей в {OUTPUT_FILE}")

def analyze_all_tar_archives():
    """
    Анализирует все tar.gz архивы в директории с параллелизацией и сохраняет результаты.
    Результаты сохраняются после обработки каждого архива для предотвращения потери данных.
    """
    start_time = time.time()
    
    if not LOCAL_DIR.exists():
        logger.error(f"Директория {LOCAL_DIR} не существует")
        return
    
    # Находим все tar.gz архивы
    tar_files = list(LOCAL_DIR.glob("*.tar.gz"))
    
    if not tar_files:
        logger.error(f"Не найдено tar.gz архивов в {LOCAL_DIR}")
        return
    
    logger.info(f"Найдено {len(tar_files)} tar.gz архивов для анализа")
    logger.info(f"Используем {MAX_WORKERS} процессов для параллельной обработки")
    
    # Загружаем существующие пути с счётчиками
    all_path_counts = load_existing_paths()
    logger.info(f"Загружено {len(all_path_counts)} существующих путей")
    
    # Параллельная обработка архивов
    processed_count = 0
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Запускаем задачи
        future_to_file = {executor.submit(analyze_tar_archive, tar_file): tar_file 
                         for tar_file in tar_files}
        
        # Собираем результаты по мере готовности
        for future in as_completed(future_to_file):
            tar_file = future_to_file[future]
            try:
                archive_path_counts = future.result()
                
                # Объединяем счётчики
                for path, count in archive_path_counts.items():
                    all_path_counts[path] = all_path_counts.get(path, 0) + count
                
                processed_count += 1
                
                # Сохраняем результаты после каждого архива
                save_paths_to_file(all_path_counts)
                
                if processed_count % 5 == 0:  # Логируем каждые 5 архивов
                    logger.info(f"Обработано {processed_count}/{len(tar_files)} архивов")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке {tar_file.name}: {e}")
    
    logger.info(f"Всего найдено {len(all_path_counts)} уникальных XML путей")
    
    elapsed_time = time.time() - start_time
    logger.info(f"Обработка завершена за {elapsed_time:.2f} секунд")
    logger.info(f"Результаты сохранены в {OUTPUT_FILE}")
    logger.info(f"Первые 10 путей с счётчиками:")
    sorted_paths = sorted(all_path_counts.items())
    for i, (path, count) in enumerate(sorted_paths[:10]):
        logger.info(f"  {i+1}. ({count}) {path}")

if __name__ == "__main__":
    analyze_all_tar_archives()
