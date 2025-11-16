"""
Модуль для фильтрации Markdown текста перед NLP аннотацией.

Исключает из обработки:
- YAML frontmatter метаданные (между ---)
- Секции References/Bibliography
- Таблицы Markdown и HTML (оставляя только <caption>)
- Теги <figure> (оставляя только <figcaption>)
- Символы заголовков # (аннотируя сам текст заголовков как предложения)
"""

import re
import logging
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FilteredTextResult:
    """
    Результат фильтрации Markdown текста.

    Attributes:
        filtered_text: Отфильтрованный текст для аннотации
        offset_map: Список соответствий (filtered_pos -> original_pos)
    """
    filtered_text: str
    offset_map: List[int]  # offset_map[filtered_pos] = original_pos


class MarkdownFilter:
    """
    Фильтр для Markdown текста перед NLP обработкой.

    Удаляет элементы форматирования, которые не должны аннотироваться,
    сохраняя при этом маппинг офсетов для корректной привязки аннотаций.
    """

    def __init__(self):
        """Инициализация фильтра."""
        # Паттерны для определения начала исключаемых секций
        self.metadata_pattern = re.compile(r'^---\s*$')
        self.references_pattern = re.compile(
            r'^##?\s*(References|Bibliography|Citations)\s*$',
            re.IGNORECASE
        )
        # Паттерн для заголовков
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+?)$')
        # Паттерн для таблиц Markdown
        self.table_separator_pattern = re.compile(r'^\s*\|[\s\-:|]+\|\s*$')
        self.table_row_pattern = re.compile(r'^\s*\|.+\|\s*$')
        # HTML паттерны
        self.html_table_pattern = re.compile(r'<table[^>]*>.*?</table>', re.IGNORECASE | re.DOTALL)
        self.caption_pattern = re.compile(r'<caption[^>]*>(.*?)</caption>', re.IGNORECASE | re.DOTALL)
        self.figure_pattern = re.compile(r'<figure[^>]*>(.*?)</figure>', re.IGNORECASE | re.DOTALL)
        self.figcaption_pattern = re.compile(r'<figcaption[^>]*>(.*?)</figcaption>', re.IGNORECASE | re.DOTALL)

    def filter_text(self, markdown_text: str) -> FilteredTextResult:
        """
        Фильтрует markdown текст, исключая ненужные для аннотации элементы.

        Двухэтапная обработка:
        1. Удаление HTML таблиц и обработка figure (с сохранением offset mapping)
        2. Построчная обработка Markdown элементов

        Args:
            markdown_text: Исходный markdown текст

        Returns:
            FilteredTextResult с отфильтрованным текстом и маппингом офсетов
        """
        logger.info(f"Начало фильтрации Markdown текста, длина: {len(markdown_text)}")

        # Этап 1: Обработка HTML элементов
        text_after_html, html_offset_map = self._process_html_elements(markdown_text)

        # Этап 2: Построчная обработка
        filtered_chars = []
        offset_map = []

        lines = text_after_html.split('\n')
        char_pos = 0
        in_metadata_block = False  # Для блоков метаданных (включая frontmatter)
        in_table = False
        i = 0

        while i < len(lines):
            line = lines[i]

            # Проверка начала блока метаданных (--- в любом месте документа)
            if self.metadata_pattern.match(line):
                if not in_metadata_block:
                    # Начало блока метаданных
                    in_metadata_block = True
                    logger.info(f"Найден блок метаданных на строке {i}, пропускаем до закрывающего ---")
                    char_pos += len(line) + 1
                    i += 1
                    continue
                else:
                    # Конец блока метаданных
                    in_metadata_block = False
                    logger.info(f"Конец блока метаданных на строке {i}")
                    char_pos += len(line) + 1
                    i += 1
                    continue

            # Пропускаем строки внутри блока метаданных
            if in_metadata_block:
                char_pos += len(line) + 1
                i += 1
                continue

            # Проверка секции References
            if self.references_pattern.match(line):
                logger.info(f"Найдена секция References на строке {i}, пропускаем до конца")
                break

            # Проверка Markdown таблиц
            if self.table_row_pattern.match(line):
                if self.table_separator_pattern.match(line):
                    in_table = True
                    char_pos += len(line) + 1
                    i += 1
                    continue

                if in_table or (i + 1 < len(lines) and
                               self.table_separator_pattern.match(lines[i + 1])):
                    char_pos += len(line) + 1
                    i += 1
                    continue
            else:
                in_table = False

            # Обработка заголовков
            heading_match = self.heading_pattern.match(line)
            if heading_match:
                heading_markers = heading_match.group(1)
                heading_text = heading_match.group(2).strip()

                # Находим позицию начала текста в line
                prefix_len = len(heading_markers)
                for j in range(prefix_len, len(line)):
                    if line[j] != ' ':
                        prefix_len = j
                        break

                # Пропускаем маркеры #
                char_pos += prefix_len

                # Добавляем текст заголовка с маппингом через html_offset_map
                for char in heading_text:
                    filtered_chars.append(char)
                    # Маппим через два уровня: сначала в text_after_html, потом в original
                    if char_pos < len(html_offset_map):
                        offset_map.append(html_offset_map[char_pos])
                    else:
                        offset_map.append(char_pos)
                    char_pos += 1

                # Добавляем точку
                if not heading_text.endswith('.'):
                    filtered_chars.append('.')
                    if char_pos > 0 and char_pos - 1 < len(html_offset_map):
                        offset_map.append(html_offset_map[char_pos - 1])
                    else:
                        offset_map.append(char_pos - 1)

                # Пропускаем остаток строки
                char_pos += len(line) - prefix_len - len(heading_text)

                # Добавляем newline
                if i < len(lines) - 1:
                    filtered_chars.append('\n')
                    if char_pos < len(html_offset_map):
                        offset_map.append(html_offset_map[char_pos])
                    else:
                        offset_map.append(char_pos)
                    char_pos += 1

                i += 1
                continue

            # Обычная строка - копируем с маппингом
            for char in line:
                filtered_chars.append(char)
                if char_pos < len(html_offset_map):
                    offset_map.append(html_offset_map[char_pos])
                else:
                    offset_map.append(char_pos)
                char_pos += 1

            # Добавляем newline
            if i < len(lines) - 1:
                filtered_chars.append('\n')
                if char_pos < len(html_offset_map):
                    offset_map.append(html_offset_map[char_pos])
                else:
                    offset_map.append(char_pos)
                char_pos += 1

            i += 1

        filtered_text = ''.join(filtered_chars)

        logger.info(
            f"Фильтрация завершена: оригинал {len(markdown_text)} -> "
            f"отфильтровано {len(filtered_text)} символов"
        )

        return FilteredTextResult(
            filtered_text=filtered_text,
            offset_map=offset_map
        )

    def _process_html_elements(self, text: str) -> tuple[str, List[int]]:
        """
        Обрабатывает HTML элементы: удаляет таблицы (сохраняя <caption>), обрабатывает figure.

        Args:
            text: Исходный текст

        Returns:
            Tuple из (обработанный текст, offset_map)
        """
        result_chars = []
        offset_map = []
        pos = 0

        while pos < len(text):
            # Проверяем HTML таблицы
            table_match = self.html_table_pattern.match(text, pos)
            if table_match:
                # Ищем caption внутри таблицы
                table_content = table_match.group(0)
                caption_match = self.caption_pattern.search(table_content)

                if caption_match:
                    # Есть caption - извлекаем только его содержимое
                    caption_text = caption_match.group(1)

                    # Находим позицию caption в оригинальном тексте
                    caption_full_start = text.find('<caption', pos)
                    caption_tag_match = re.match(r'<caption[^>]*>', text[caption_full_start:], re.IGNORECASE)
                    caption_content_start = caption_full_start + len(caption_tag_match.group(0))

                    # Добавляем содержимое caption с правильным маппингом
                    for i, char in enumerate(caption_text):
                        result_chars.append(char)
                        offset_map.append(caption_content_start + i)

                # Пропускаем всю таблицу
                pos = table_match.end()
                continue

            # Проверяем figure
            figure_match = self.figure_pattern.match(text, pos)
            if figure_match:
                figure_content = figure_match.group(1)
                figcaption_match = self.figcaption_pattern.search(figure_content)

                if figcaption_match:
                    # Есть figcaption - извлекаем только его содержимое
                    caption_text = figcaption_match.group(1)

                    # Находим позицию figcaption в оригинальном тексте
                    figcaption_full_start = text.find('<figcaption', pos)
                    figcaption_tag_match = re.match(r'<figcaption[^>]*>', text[figcaption_full_start:], re.IGNORECASE)
                    figcaption_content_start = figcaption_full_start + len(figcaption_tag_match.group(0))

                    # Добавляем содержимое figcaption с правильным маппингом
                    for i, char in enumerate(caption_text):
                        result_chars.append(char)
                        offset_map.append(figcaption_content_start + i)

                # Пропускаем весь figure блок
                pos = figure_match.end()
                continue

            # Обычный символ - копируем
            result_chars.append(text[pos])
            offset_map.append(pos)
            pos += 1

        return ''.join(result_chars), offset_map

    def map_offset_to_original(
        self,
        filtered_offset: int,
        offset_map: List[int]
    ) -> int:
        """
        Преобразует офсет из отфильтрованного текста в оригинальный.

        Args:
            filtered_offset: Позиция в отфильтрованном тексте
            offset_map: Список маппинга офсетов

        Returns:
            Соответствующая позиция в оригинальном тексте
        """
        if not offset_map:
            return filtered_offset

        if filtered_offset < 0:
            return 0

        if filtered_offset >= len(offset_map):
            # Вышли за пределы - берём последний известный офсет
            # и добавляем разницу
            if offset_map:
                last_filtered = len(offset_map) - 1
                last_original = offset_map[-1]
                return last_original + (filtered_offset - last_filtered)
            return filtered_offset

        return offset_map[filtered_offset]
