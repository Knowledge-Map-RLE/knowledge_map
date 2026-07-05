"""
Валидация канонического формата Markdown.

Чистые функции для валидации различных аспектов markdown документа.
Каждая функция возвращает ValidationResult с найденными ошибками.
"""
import re
from typing import List, Optional, Any
import yaml

from .types import (
    ValidationResult, ValidationError, ErrorType, ErrorSeverity,
    Citation, Reference
)


def validate_markdown(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Главная функция валидации - компонует все валидаторы.

    Args:
        text: Markdown текст для валидации
        config: Опциональная конфигурация NLP сервиса

    Returns:
        ValidationResult со всеми найденными ошибками и предупреждениями

    Example:
        >>> result = validate_markdown(markdown_text)
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(f"Line {error.line}: {error.message}")
    """
    result = ValidationResult(is_valid=True)

    # Проверка длины документа
    if config and hasattr(config, 'max_markdown_length'):
        if len(text) > config.max_markdown_length:
            result.add_error(ValidationError(
                error_type=ErrorType.MALFORMED_FRONTMATTER,
                message=f"Документ слишком длинный ({len(text)} > {config.max_markdown_length} символов)",
                severity=ErrorSeverity.ERROR,
                start_offset=0,
                end_offset=len(text)
            ))
            return result

    # Запустить все валидаторы (порядок важен!)
    validators = [
        validate_frontmatter,
        validate_doi,
        validate_no_text_between_frontmatter_and_h1,
        validate_h1_uniqueness,
        validate_html_tables,
        validate_html_images,
        validate_references_bidirectional,
    ]

    for validator in validators:
        validator_result = validator(text, config)
        result.merge(validator_result)

    # Добавить метаданные
    result.metadata['text_length'] = len(text)
    result.metadata['validators_run'] = [v.__name__ for v in validators]

    return result


def validate_frontmatter(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Валидация YAML frontmatter.

    Правила:
    - Документ должен начинаться с --- (блок метаданных)
    - Если начинается с ---, должен содержать валидный YAML
    - Должен заканчиваться на ---

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками frontmatter
    """
    result = ValidationResult(is_valid=True)

    lines = text.split('\n')
    if not lines:
        return result

    # Проверить, начинается ли с ---
    if not lines[0].strip() == '---':
        first_line_len = min(len(lines[0]), 80) if lines[0] else 1
        result.add_error(ValidationError(
            error_type=ErrorType.MISSING_FRONTMATTER,
            message="Документ должен начинаться с блока YAML метаданных '---'",
            severity=ErrorSeverity.ERROR,
            line=1,
            column=1,
            start_offset=0,
            end_offset=first_line_len if first_line_len > 0 else 1,
            suggestion="Добавьте в начало документа блок YAML метаданных между маркерами '---'"
        ))
        result.metadata['has_frontmatter'] = False
        return result

    result.metadata['has_frontmatter'] = True

    # Найти закрывающий ---
    closing_index = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            closing_index = i
            break

    if closing_index is None:
        opening_line_len = len(lines[0]) if lines else 3
        result.add_error(ValidationError(
            error_type=ErrorType.MALFORMED_FRONTMATTER,
            message="Найдено открытие frontmatter '---', но нет закрытия",
            severity=ErrorSeverity.ERROR,
            line=1,
            column=1,
            start_offset=0,
            end_offset=opening_line_len,
            suggestion="Добавьте закрывающую строку '---' после содержания YAML"
        ))
        return result

    # Извлечь и валидировать YAML
    yaml_lines = lines[1:closing_index]
    yaml_text = '\n'.join(yaml_lines)

    try:
        yaml_data = yaml.safe_load(yaml_text)
        result.metadata['frontmatter_data'] = yaml_data
    except yaml.YAMLError as e:
        # Вычислить номер строки ошибки
        error_line = 1 + (e.problem_mark.line if hasattr(e, 'problem_mark') else 0)
        yaml_start = len(lines[0]) + 1  # после открывающего ---\n
        yaml_end = sum(len(l) + 1 for l in lines[:closing_index])  # до закрывающего ---

        result.add_error(ValidationError(
            error_type=ErrorType.INVALID_YAML,
            message=f"Невалидный YAML в frontmatter: {str(e)}",
            severity=ErrorSeverity.ERROR,
            line=error_line,
            start_offset=yaml_start,
            end_offset=yaml_end,
            context=yaml_text[:200] if len(yaml_text) > 200 else yaml_text,
            suggestion="Исправьте синтаксис YAML"
        ))

    return result


def validate_doi(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    В метаданных frontmatter обязательно поле doi в формате полного URL.

    Формат: https://doi.org/[префикс]/[суффикс]
    Например: https://doi.org/10.1007/s00401-019-02056-w

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками DOI
    """
    result = ValidationResult(is_valid=True)
    lines = text.split('\n')

    if not lines or lines[0].strip() != '---':
        return result

    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            closing_idx = i
            break

    if closing_idx is None:
        return result

    yaml_lines = lines[1:closing_idx]
    yaml_text = '\n'.join(yaml_lines)

    try:
        yaml_data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return result

    if yaml_data is None:
        result.add_error(ValidationError(
            error_type=ErrorType.MISSING_DOI,
            message="В метаданных frontmatter обязательно поле doi",
            severity=ErrorSeverity.ERROR,
            line=1,
            suggestion="Добавьте 'doi: https://doi.org/префикс/суффикс' в секцию frontmatter"
        ))
        return result

    if not isinstance(yaml_data, dict):
        return result

    doi = yaml_data.get('doi')

    if doi is None or (isinstance(doi, str) and not doi.strip()):
        result.add_error(ValidationError(
            error_type=ErrorType.MISSING_DOI,
            message="В метаданных frontmatter обязательно поле doi",
            severity=ErrorSeverity.ERROR,
            line=1,
            suggestion="Добавьте 'doi: https://doi.org/префикс/суффикс' в секцию frontmatter"
        ))
        return result

    doi_str = str(doi).strip()
    import re
    doi_pattern = re.compile(r'^https://doi\.org/10\.\d{4,}/.+$')
    if not doi_pattern.match(doi_str):
        result.add_error(ValidationError(
            error_type=ErrorType.INVALID_DOI_FORMAT,
            message=f"Поле doi должно быть полным URL вида https://doi.org/10.xxxx/..., получено: '{doi_str}'",
            severity=ErrorSeverity.ERROR,
            line=1,
            start_offset=0,
            end_offset=len(lines[0]) if lines else 0,
            suggestion="Исправьте формат: 'doi: https://doi.org/10.префикс/суффикс'"
        ))

    return result


def validate_no_text_between_frontmatter_and_h1(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Между закрывающим --- frontmatter и заголовком H1 должна быть ровно одна пустая строка.

    Правила:
    - Если между --- и H1 есть непустой текст → ошибка
    - Если между --- и H1 0 пустых строк (H1 сразу после ---) → ошибка
    - Если между --- и H1 больше 1 пустой строки → ошибка
    - Ровно 1 пустая строка → корректно

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками если найден текст между --- и H1
    """
    result = ValidationResult(is_valid=True)
    lines = text.split('\n')

    if not lines or lines[0].strip() != '---':
        return result

    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            closing_idx = i
            break

    if closing_idx is None:
        return result

    h1_idx = None
    for i in range(closing_idx + 1, len(lines)):
        if lines[i].strip().startswith('# '):
            h1_idx = i
            break

    if h1_idx is None:
        return result

    lines_between = lines[closing_idx + 1:h1_idx]
    non_empty = [(i, lines_between[i]) for i in range(len(lines_between))
                 if lines_between[i].strip()]
    empty_count = sum(1 for l in lines_between if not l.strip())

    first_bad_idx = closing_idx + 1

    if non_empty:
        first_bad_idx += non_empty[0][0]
        bad_line = non_empty[0][1]
        offset = 0
        for i in range(first_bad_idx):
            offset += len(lines[i]) + 1

        result.add_error(ValidationError(
            error_type=ErrorType.TEXT_BETWEEN_FRONTMATTER_AND_H1,
            message=f"Между '---' и H1 есть текст: '{bad_line.strip()}'",
            severity=ErrorSeverity.ERROR,
            line=first_bad_idx + 1,
            column=1,
            start_offset=offset,
            end_offset=offset + len(bad_line),
            context=bad_line.strip(),
            suggestion="Удалите текст между '---' и заголовком H1, оставив только пустую строку"
        ))
    elif empty_count == 0:
        first_bad_idx = closing_idx + 1
        offset = 0
        for i in range(first_bad_idx):
            offset += len(lines[i]) + 1

        result.add_error(ValidationError(
            error_type=ErrorType.TEXT_BETWEEN_FRONTMATTER_AND_H1,
            message="После '---' отсутствует пустая строка перед H1",
            severity=ErrorSeverity.ERROR,
            line=first_bad_idx,
            start_offset=offset,
            end_offset=offset,
            suggestion="Добавьте пустую строку между '---' и заголовком H1"
        ))
    elif empty_count > 1:
        offset = 0
        for i in range(closing_idx + 2):
            offset += len(lines[i]) + 1

        result.add_error(ValidationError(
            error_type=ErrorType.TEXT_BETWEEN_FRONTMATTER_AND_H1,
            message=f"После '---' {empty_count} пустых строк вместо одной",
            severity=ErrorSeverity.ERROR,
            line=closing_idx + 2,
            start_offset=offset,
            end_offset=offset,
            suggestion="Оставьте ровно одну пустую строку между '---' и заголовком H1"
        ))

    return result


def validate_h1_uniqueness(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Валидация уникальности заголовка H1.

    Правила:
    - Только одна строка начинающаяся с "# " (один #)
    - Может быть любое количество ## или более глубоких заголовков

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками H1
    """
    result = ValidationResult(is_valid=True)

    # Паттерн для H1: строка начинается с "# " (не ##)
    h1_pattern = re.compile(r'^#\s+.+$', re.MULTILINE)

    matches = list(h1_pattern.finditer(text))

    if len(matches) == 0:
        result.add_error(ValidationError(
            error_type=ErrorType.MISSING_H1,
            message="Документ должен содержать ровно один заголовок H1 (# Название)",
            severity=ErrorSeverity.ERROR,
            line=1,
            suggestion="Добавьте один заголовок '# Название' в начало документа"
        ))
    elif len(matches) > 1:
        # Показать все дубликаты
        for i, match in enumerate(matches):
            line_num = text[:match.start()].count('\n') + 1
            h1_text = match.group(0)

            result.add_error(ValidationError(
                error_type=ErrorType.MULTIPLE_H1,
                message=f"Найдено несколько заголовков H1 (#{i+1} из {len(matches)}): {h1_text}",
                severity=ErrorSeverity.ERROR,
                line=line_num,
                start_offset=match.start(),
                end_offset=match.end(),
                context=h1_text,
                suggestion="Оставьте только один H1 заголовок, остальные конвертируйте в H2 (##) или глубже"
            ))
    else:
        # Ровно один H1 - хорошо!
        match = matches[0]
        line_num = text[:match.start()].count('\n') + 1
        result.metadata['h1_line'] = line_num
        result.metadata['h1_text'] = match.group(0)

    return result


def validate_html_tables(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Валидация формата таблиц - только HTML.

    Правила:
    - Нет markdown таблиц (трубы |---|---|)
    - HTML <table> теги разрешены

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками таблиц
    """
    result = ValidationResult(is_valid=True)

    # Паттерн для разделителя markdown таблицы: |---|---|
    md_table_sep = re.compile(r'^\s*\|[\s\-:|]+\|\s*$', re.MULTILINE)

    matches = list(md_table_sep.finditer(text))

    for match in matches:
        line_num = text[:match.start()].count('\n') + 1

        # Получить окружающие строки для контекста
        lines = text.split('\n')
        context_lines = []
        if line_num > 1:
            context_lines.append(lines[line_num - 2])
        context_lines.append(lines[line_num - 1])
        if line_num < len(lines):
            context_lines.append(lines[line_num])

        result.add_error(ValidationError(
            error_type=ErrorType.MARKDOWN_TABLE_FOUND,
            message="Markdown таблицы не разрешены. Используйте HTML <table> вместо этого.",
            severity=ErrorSeverity.ERROR,
            line=line_num,
            start_offset=match.start(),
            end_offset=match.end(),
            context='\n'.join(context_lines),
            suggestion="Конвертируйте в HTML формат таблицы: <table><tr><td>...</td></tr></table>"
        ))

    result.metadata['markdown_tables_found'] = len(matches)

    return result


def validate_html_images(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Валидация формата изображений - только HTML.

    Правила:
    - Нет markdown изображений: ![alt](url)
    - HTML <img> или <figure> теги разрешены

    Args:
        text: Markdown текст
        config: Конфигурация (не используется)

    Returns:
        ValidationResult с ошибками изображений
    """
    result = ValidationResult(is_valid=True)

    # Паттерн для markdown изображений: ![alt](url)
    md_image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    matches = list(md_image_pattern.finditer(text))

    for match in matches:
        line_num = text[:match.start()].count('\n') + 1
        col_num = match.start() - text.rfind('\n', 0, match.start())

        alt_text = match.group(1)
        img_url = match.group(2)

        # Рекомендация для замены
        if alt_text:
            suggestion = f'<figure><img src="{img_url}" alt="{alt_text}"><figcaption>{alt_text}</figcaption></figure>'
        else:
            suggestion = f'<img src="{img_url}" alt="">'

        result.add_error(ValidationError(
            error_type=ErrorType.MARKDOWN_IMAGE_FOUND,
            message=f"Markdown изображения не разрешены: {match.group(0)}",
            severity=ErrorSeverity.ERROR,
            line=line_num,
            column=col_num,
            start_offset=match.start(),
            end_offset=match.end(),
            context=match.group(0),
            suggestion=f"Используйте HTML формат: {suggestion}"
        ))

    result.metadata['markdown_images_found'] = len(matches)

    return result


def validate_references_bidirectional(text: str, config: Optional[Any] = None) -> ValidationResult:
    """
    Валидация двунаправленных ссылок и ссылок.

    Правила:
    - Документ должен заканчиваться разделом ## References (опционально по конфигу)
    - Все цитаты [N] в тексте должны иметь соответствующую запись ссылки
    - Все записи ссылок должны быть процитированы хотя бы один раз
    - Номера ссылок должны быть уникальными
    - Формат: [N]: библиографический текст

    Args:
        text: Markdown текст
        config: Конфигурация (может содержать require_references_section)

    Returns:
        ValidationResult с ошибками ссылок
    """
    result = ValidationResult(is_valid=True)

    # Найти раздел References
    ref_section_match = re.search(
        r'^##\s+(References|Bibliography|Citations)\s*$',
        text,
        re.MULTILINE | re.IGNORECASE
    )

    # Требование к разделу References определяется конфигом
    require_references = True
    if config and hasattr(config, 'require_references_section'):
        require_references = config.require_references_section

    if not ref_section_match:
        if require_references:
            result.add_error(ValidationError(
                error_type=ErrorType.MISSING_REFERENCES_SECTION,
                message="Документ должен заканчиваться разделом ## References",
                severity=ErrorSeverity.ERROR,
                suggestion="Добавьте раздел '## References' в конец документа"
            ))
        return result

    ref_section_start = ref_section_match.end()

    # Разделить на основной текст и раздел ссылок
    body = text[:ref_section_match.start()]
    references_text = text[ref_section_start:]

    # Извлечь цитаты из основного текста: [1], [2], и т.д.
    citations = _extract_citations(body)

    # Извлечь ссылки из раздела References: [1]: текст
    references = _extract_references(references_text, ref_section_start)

    # Построить множества номеров
    cited_numbers = {c.number for c in citations}
    reference_numbers = {r.number for r in references}

    # Проверить цитаты без ссылок
    uncited_refs = cited_numbers - reference_numbers
    for num in sorted(uncited_refs):
        # Найти цитату для лучшего отчёта об ошибке
        citation = next(c for c in citations if c.number == num)

        result.add_error(ValidationError(
            error_type=ErrorType.CITATION_WITHOUT_REFERENCE,
            message=f"Цитата [{num}] не имеет соответствующей записи ссылки",
            severity=ErrorSeverity.ERROR,
            line=citation.line,
            column=citation.column,
            start_offset=citation.start_offset,
            end_offset=citation.end_offset,
            context=citation.context,
            suggestion=f"Добавьте '[{num}]: библиографический текст' в раздел References"
        ))

    # Проверить висячие ссылки (не процитированные)
    orphaned_refs = reference_numbers - cited_numbers
    for num in sorted(orphaned_refs):
        # Найти ссылку для лучшего отчёта об ошибке
        reference = next(r for r in references if r.number == num)

        result.add_error(ValidationError(
            error_type=ErrorType.ORPHANED_REFERENCE,
            message=f"Ссылка [{num}] не процитирована в тексте",
            severity=ErrorSeverity.ERROR,
            line=reference.line,
            start_offset=reference.start_offset,
            end_offset=reference.end_offset,
            context=reference.text[:100] + "..." if len(reference.text) > 100 else reference.text,
            suggestion=f"Либо процитируйте [{num}] в тексте, либо удалите эту ссылку"
        ))

    # Проверить дубликаты номеров ссылок
    ref_num_counts = {}
    for ref in references:
        ref_num_counts[ref.number] = ref_num_counts.get(ref.number, 0) + 1

    for num, count in ref_num_counts.items():
        if count > 1:
            result.add_error(ValidationError(
                error_type=ErrorType.DUPLICATE_REFERENCE_NUMBER,
                message=f"Номер ссылки [{num}] определён {count} раз",
                severity=ErrorSeverity.ERROR,
                suggestion=f"Убедитесь, что каждый номер ссылки встречается только один раз"
            ))

    # Метаданные
    result.metadata['total_citations'] = len(citations)
    result.metadata['total_references'] = len(references)
    result.metadata['unique_citations'] = len(cited_numbers)
    result.metadata['unique_references'] = len(reference_numbers)

    return result


def _extract_citations(text: str) -> List[Citation]:
    """
    Извлечь все цитаты [N] из текста.

    Args:
        text: Markdown текст

    Returns:
        Список найденных цитат
    """
    citations = []
    # Паттерн: [N] где N - число
    pattern = re.compile(r'\[(\d+)\]')

    for match in pattern.finditer(text):
        number = int(match.group(1))
        line_num = text[:match.start()].count('\n') + 1
        col_num = match.start() - text.rfind('\n', 0, match.start())

        # Получить контекст (окружающий текст)
        context_start = max(0, match.start() - 30)
        context_end = min(len(text), match.end() + 30)
        context = text[context_start:context_end]

        citations.append(Citation(
            number=number,
            start_offset=match.start(),
            end_offset=match.end(),
            line=line_num,
            column=col_num,
            context=context
        ))

    return citations


def _extract_references(text: str, offset: int) -> List[Reference]:
    """
    Извлечь все записи ссылок из раздела References.

    Формат: [N]: библиографический текст

    Args:
        text: Текст раздела References (без самого заголовка)
        offset: Смещение в исходном документе

    Returns:
        Список найденных ссылок
    """
    references = []
    # Паттерн: [N]: текст (в начале строки)
    pattern = re.compile(r'^\[(\d+)\]:\s*(.+)$', re.MULTILINE)

    for match in pattern.finditer(text):
        number = int(match.group(1))
        ref_text = match.group(2).strip()
        line_num = text[:match.start()].count('\n') + 1

        references.append(Reference(
            number=number,
            text=ref_text,
            start_offset=offset + match.start(),
            end_offset=offset + match.end(),
            line=line_num
        ))

    return references
