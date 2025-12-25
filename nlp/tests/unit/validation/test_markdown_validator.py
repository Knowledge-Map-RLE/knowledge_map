"""
Юнит тесты для модуля валидации markdown.

Тестирует каждый валидатор отдельно:
- YAML frontmatter валидация
- H1 заголовок валидация
- HTML таблицы
- HTML изображения
- Двунаправленная валидация ссылок
"""
import pytest
from pathlib import Path
import sys

# Добавить src в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from validation import (
    validate_markdown,
    ValidationResult,
    ErrorType,
    ErrorSeverity,
)
from validation.markdown_validator import (
    validate_frontmatter,
    validate_h1_uniqueness,
    validate_html_tables,
    validate_html_images,
    validate_references_bidirectional,
)


class TestFrontmatterValidation:
    """Тесты валидации YAML frontmatter."""

    def test_valid_frontmatter(self):
        """Валидный frontmatter должен пройти."""
        markdown = """---
title: Test Article
author: John Doe
tags:
  - test
  - markdown
---

# Content
Some content here."""
        result = validate_frontmatter(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['has_frontmatter'] is True

    def test_no_frontmatter(self):
        """Документ без frontmatter допустим."""
        markdown = """# Content
Some content here."""
        result = validate_frontmatter(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['has_frontmatter'] is False

    def test_unclosed_frontmatter(self):
        """Открытый frontmatter без закрытия должен быть ошибкой."""
        markdown = """---
title: Test Article
author: John Doe

# Content
Some content here."""
        result = validate_frontmatter(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.MALFORMED_FRONTMATTER

    def test_invalid_yaml_frontmatter(self):
        """Невалидный YAML в frontmatter должен быть ошибкой."""
        markdown = """---
title: Test Article
author: John Doe
tags:
  - test
  - markdown
  invalid yaml content
---

# Content"""
        result = validate_frontmatter(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.INVALID_YAML


class TestH1Validation:
    """Тесты валидации H1 заголовков."""

    def test_single_h1_valid(self):
        """Документ с одним H1 должен быть валидным."""
        markdown = """# Main Title

## Section 1
Content here.

## Section 2
More content."""
        result = validate_h1_uniqueness(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['h1_text'] == "# Main Title"

    def test_no_h1_error(self):
        """Документ без H1 должен быть ошибкой."""
        markdown = """## Section 1
Content here.

## Section 2
More content."""
        result = validate_h1_uniqueness(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.MISSING_H1

    def test_multiple_h1_error(self):
        """Документ с несколькими H1 должен быть ошибкой."""
        markdown = """# First Title

Content here.

# Second Title

More content."""
        result = validate_h1_uniqueness(markdown)
        assert not result.is_valid
        assert len(result.errors) == 2
        for error in result.errors:
            assert error.error_type == ErrorType.MULTIPLE_H1

    def test_h1_with_spaces(self):
        """H1 с пробелами после # должен быть валидным."""
        markdown = """#    Title with spaces

Content here."""
        result = validate_h1_uniqueness(markdown)
        assert result.is_valid


class TestHTMLTableValidation:
    """Тесты валидации таблиц - только HTML."""

    def test_html_table_allowed(self):
        """HTML таблица должна быть разрешена."""
        markdown = """# Article

<table>
  <tr>
    <td>Cell 1</td>
    <td>Cell 2</td>
  </tr>
</table>"""
        result = validate_html_tables(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['markdown_tables_found'] == 0

    def test_markdown_table_rejected(self):
        """Markdown таблица должна быть отклонена."""
        markdown = """# Article

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |"""
        result = validate_html_tables(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.MARKDOWN_TABLE_FOUND

    def test_multiple_markdown_tables(self):
        """Несколько markdown таблиц должны быть обнаружены."""
        markdown = """# Article

| Col 1 | Col 2 |
|-------|-------|
| A     | B     |

Some text.

| Col 1 | Col 2 |
|-------|-------|
| C     | D     |"""
        result = validate_html_tables(markdown)
        assert not result.is_valid
        assert len(result.errors) == 2
        assert result.metadata['markdown_tables_found'] == 2


class TestHTMLImageValidation:
    """Тесты валидации изображений - только HTML."""

    def test_html_img_allowed(self):
        """HTML img тег должен быть разрешен."""
        markdown = """# Article

<img src="image.png" alt="Alt text">"""
        result = validate_html_images(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['markdown_images_found'] == 0

    def test_html_figure_allowed(self):
        """HTML figure с img должен быть разрешен."""
        markdown = """# Article

<figure>
  <img src="image.png" alt="Alt text">
  <figcaption>Image caption</figcaption>
</figure>"""
        result = validate_html_images(markdown)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_markdown_image_rejected(self):
        """Markdown изображение должно быть отклонено."""
        markdown = """# Article

![Alt text](image.png)"""
        result = validate_html_images(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.MARKDOWN_IMAGE_FOUND

    def test_multiple_markdown_images(self):
        """Несколько markdown изображений должны быть обнаружены."""
        markdown = """# Article

![First image](image1.png)

Some text.

![Second image](image2.png)"""
        result = validate_html_images(markdown)
        assert not result.is_valid
        assert len(result.errors) == 2
        assert result.metadata['markdown_images_found'] == 2


class TestReferencesValidation:
    """Тесты валидации двунаправленных ссылок."""

    def test_valid_references(self):
        """Валидные ссылки с соответствующими цитатами."""
        markdown = """# Article

This is a citation [1] and another one [2].

Some more text with citation [1] again.

## References

[1]: Smith, J. (2023). First reference.
[2]: Johnson, M. (2023). Second reference."""
        result = validate_references_bidirectional(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata['total_citations'] == 3
        assert result.metadata['total_references'] == 2

    def test_citation_without_reference(self):
        """Цитата без соответствующей ссылки - ошибка."""
        markdown = """# Article

This is a citation [1] and citation [2].

## References

[1]: Smith, J. (2023). First reference."""
        result = validate_references_bidirectional(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.CITATION_WITHOUT_REFERENCE
        assert result.errors[0].severity == ErrorSeverity.ERROR

    def test_orphaned_reference(self):
        """Ссылка без цитаты - предупреждение."""
        markdown = """# Article

This is a citation [1].

## References

[1]: Smith, J. (2023). First reference.
[2]: Johnson, M. (2023). Unused reference."""
        result = validate_references_bidirectional(markdown)
        assert result.is_valid  # Ошибок нет, есть предупреждение
        assert len(result.warnings) == 1
        assert result.warnings[0].error_type == ErrorType.ORPHANED_REFERENCE
        assert result.warnings[0].severity == ErrorSeverity.WARNING

    def test_missing_references_section(self):
        """Отсутствие раздела References."""
        markdown = """# Article

This is a citation [1]."""
        result = validate_references_bidirectional(markdown)
        assert result.is_valid  # Только warning
        assert len(result.warnings) == 1
        assert result.warnings[0].error_type == ErrorType.MISSING_REFERENCES_SECTION

    def test_duplicate_reference_number(self):
        """Дубликаты номеров ссылок - ошибка."""
        markdown = """# Article

Citation [1] and citation [2].

## References

[1]: Smith, J. (2023). First reference.
[1]: Johnson, M. (2023). Duplicate number."""
        result = validate_references_bidirectional(markdown)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ErrorType.DUPLICATE_REFERENCE_NUMBER

    def test_complex_references(self):
        """Сложный случай с несколькими проблемами."""
        markdown = """# Article

Citation [1], citation [2], citation [3].

## References

[1]: First reference.
[2]: Second reference.
[4]: Fourth reference (orphaned).
[2]: Second reference duplicate."""
        result = validate_references_bidirectional(markdown)
        # Должны быть: citation [3] без ссылки, orphaned [4], duplicate [2]
        assert not result.is_valid
        assert any(e.error_type == ErrorType.CITATION_WITHOUT_REFERENCE for e in result.errors)
        assert any(e.error_type == ErrorType.DUPLICATE_REFERENCE_NUMBER for e in result.errors)
        assert any(w.error_type == ErrorType.ORPHANED_REFERENCE for w in result.warnings)


class TestFullValidation:
    """Тесты полной валидации документа."""

    def test_valid_complete_document(self):
        """Полностью валидный документ."""
        markdown = """---
title: Complete Article
author: John Doe
---

# Article Title

This is a well-formed article [1] with proper structure [2].

## Section 1

Content with citation [1].

<table>
  <tr>
    <td>Data 1</td>
    <td>Data 2</td>
  </tr>
</table>

<img src="image.png" alt="Image">

## References

[1]: Smith, J. (2023). First reference.
[2]: Johnson, M. (2023). Second reference."""
        result = validate_markdown(markdown)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_document_with_multiple_errors(self):
        """Документ с несколькими ошибками."""
        markdown = """# First Title

## Second Title

This has markdown image ![alt](img.png).

| Bad | Markdown | Table |
|-----|----------|-------|
| 1   | 2        | 3     |

Citation without reference [99].

## References

[1]: Unused reference."""
        result = validate_markdown(markdown)
        assert not result.is_valid
        assert len(result.errors) > 0
        # Должны быть ошибки: multiple H1, markdown image, markdown table, citation without reference
        error_types = [e.error_type for e in result.errors]
        assert ErrorType.MULTIPLE_H1 in error_types
        assert ErrorType.MARKDOWN_IMAGE_FOUND in error_types
        assert ErrorType.MARKDOWN_TABLE_FOUND in error_types
        assert ErrorType.CITATION_WITHOUT_REFERENCE in error_types

    def test_document_with_warnings_only(self):
        """Документ с предупреждениями но без ошибок."""
        markdown = """# Title

Citation [1].

## References

[1]: First reference.
[2]: Unused reference."""
        result = validate_markdown(markdown)
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) > 0


class TestErrorDetails:
    """Тесты деталей об ошибках - координаты и контекст."""

    def test_error_coordinates_h1(self):
        """Проверка координат ошибки H1."""
        markdown = """Line 1

# First H1

# Second H1"""
        result = validate_h1_uniqueness(markdown)
        assert len(result.errors) == 2
        # Первый H1 на строке 3
        assert result.errors[0].line == 3
        # Второй H1 на строке 5
        assert result.errors[1].line == 5

    def test_error_coordinates_markdown_image(self):
        """Проверка координат для markdown изображения."""
        markdown = """# Title

Some text here.

![Alt text](image.png)"""
        result = validate_html_images(markdown)
        assert len(result.errors) == 1
        error = result.errors[0]
        assert error.line == 5
        assert error.context == "![Alt text](image.png)"
        assert error.suggestion is not None

    def test_error_suggestion_provided(self):
        """Все ошибки должны иметь рекомендацию."""
        markdown = """# Title

![Markdown image](image.png)"""
        result = validate_html_images(markdown)
        assert len(result.errors) == 1
        assert result.errors[0].suggestion is not None
        assert "HTML" in result.errors[0].suggestion or "html" in result.errors[0].suggestion.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
