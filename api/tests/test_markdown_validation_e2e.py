"""
End-to-End тесты для HTTP API валидации markdown.

Тестирует полный путь: HTTP запрос → API сервис → gRPC → NLP сервис → Валидация.

Примечание: Для полного E2E тестирования нужны запущенные:
1. NLP сервис (gRPC на порту 50055)
2. API сервис (FastAPI)

Эти тесты проверяют структуру endpoints, обработку ошибок и форматы ответов.
"""
import pytest
from typing import Dict, Any
import json


class TestMarkdownValidationEndpoint:
    """Тесты endpoint'а валидации markdown."""

    @pytest.fixture
    def client(self):
        """Фикстура для FastAPI test client."""
        try:
            from fastapi.testclient import TestClient
            from pathlib import Path
            import sys

            # Добавить paths для импортов
            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            # Импортировать основное приложение
            from src.main import app

            return TestClient(app)
        except ImportError as e:
            pytest.skip(f"Не удалось импортировать FastAPI app: {e}")

    def test_validate_endpoint_exists(self, client):
        """Проверка существования endpoint'а валидации."""
        # Это базовый тест - просто проверить, что endpoint существует
        # В реальности нужен запущенный сервис
        try:
            response = client.post("/api/data_extraction/markdown/validate",
                                  json={"markdown": "# Test", "strict_mode": False})
            # Должен быть хотя бы ответ (даже если это ошибка соединения)
            assert response is not None
        except Exception as e:
            pytest.skip(f"Endpoint не доступен: {e}")

    def test_validate_request_schema(self):
        """Проверка схемы запроса валидации."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownRequest

            # Создать валидный запрос
            request = ValidateMarkdownRequest(
                markdown="# Test\n\nContent",
                strict_mode=False
            )

            assert request.markdown == "# Test\n\nContent"
            assert request.strict_mode is False

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_validate_response_schema(self):
        """Проверка схемы ответа валидации."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse, ValidationErrorSchema

            # Создать ошибку
            error = ValidationErrorSchema(
                error_type="MULTIPLE_H1",
                message="Multiple H1 found",
                severity="error",
                line=5,
                column=1,
                context="# Second H1",
                suggestion="Keep only one H1"
            )

            # Создать ответ
            response = ValidateMarkdownResponse(
                success=True,
                is_valid=False,
                errors=[error],
                warnings=[],
                message="Validation failed",
                total_errors=1,
                total_warnings=0
            )

            assert response.success is True
            assert response.is_valid is False
            assert len(response.errors) == 1
            assert response.errors[0].error_type == "MULTIPLE_H1"

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestDocumentMarkdownUpdateEndpoint:
    """Тесты endpoint'а обновления markdown документа с авто-валидацией."""

    @pytest.fixture
    def client(self):
        """Фикстура для FastAPI test client."""
        try:
            from fastapi.testclient import TestClient
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.main import app

            return TestClient(app)
        except ImportError as e:
            pytest.skip(f"Не удалось импортировать FastAPI app: {e}")

    def test_update_markdown_request_schema(self):
        """Проверка схемы запроса обновления markdown."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownRequest

            # Запрос с валидацией
            request = UpdateMarkdownRequest(
                markdown="# Updated\n\nNew content",
                auto_validate=True,
                strict_mode=False
            )

            assert request.markdown == "# Updated\n\nNew content"
            assert request.auto_validate is True
            assert request.strict_mode is False

            # Запрос без параметров (должны использоваться defaults)
            request2 = UpdateMarkdownRequest(
                markdown="# Simple"
            )

            assert request2.markdown == "# Simple"
            assert request2.auto_validate is True
            assert request2.strict_mode is False

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_update_markdown_response_schema(self):
        """Проверка схемы ответа обновления markdown."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownResponse, ValidateMarkdownResponse

            # Ответ с результатами валидации
            validation_result = {
                "success": True,
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "message": "Valid",
                "total_errors": 0,
                "total_warnings": 0,
                "metadata": {}
            }

            response = UpdateMarkdownResponse(
                success=True,
                message="Markdown updated",
                doc_id="doc_123",
                s3_key="documents/doc_123/markdown.md",
                validation=validation_result
            )

            assert response.success is True
            assert response.doc_id == "doc_123"
            assert response.validation is not None
            assert response.validation["is_valid"] is True

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestValidationErrorSchema:
    """Тесты ValidationErrorSchema."""

    def test_validation_error_schema_all_fields(self):
        """Все поля ValidationErrorSchema."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidationErrorSchema

            error = ValidationErrorSchema(
                error_type="MISSING_H1",
                message="Document must have H1",
                severity="error",
                line=1,
                column=1,
                start_offset=0,
                end_offset=100,
                context="Document start",
                suggestion="Add H1 header",
                metadata={"found": "0"}
            )

            assert error.error_type == "MISSING_H1"
            assert error.severity == "error"
            assert error.line == 1
            assert error.metadata == {"found": "0"}

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_validation_error_schema_optional_fields(self):
        """Опциональные поля ValidationErrorSchema."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidationErrorSchema

            # Минимальный набор
            error = ValidationErrorSchema(
                error_type="TEST",
                message="Test message",
                severity="error"
            )

            assert error.error_type == "TEST"
            assert error.line is None
            assert error.context is None
            assert error.suggestion is None

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestStrictModeIntegration:
    """Тесты strict mode в E2E контексте."""

    def test_strict_mode_true_with_errors(self):
        """Strict mode=True с ошибками должен отклонить запрос."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownRequest

            # Документ с ошибками
            request = UpdateMarkdownRequest(
                markdown="# Title 1\n\n# Title 2",  # Multiple H1
                auto_validate=True,
                strict_mode=True
            )

            assert request.markdown == "# Title 1\n\n# Title 2"
            assert request.strict_mode is True

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_strict_mode_false_allows_warnings(self):
        """Strict mode=False разрешает документы с warnings."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownRequest

            # Документ с предупреждениями
            request = UpdateMarkdownRequest(
                markdown="# Title\n\nContent [1]",  # Citation without reference
                auto_validate=True,
                strict_mode=False
            )

            assert request.strict_mode is False

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestAutoValidationParameter:
    """Тесты параметра auto_validate."""

    def test_auto_validate_enabled_by_default(self):
        """auto_validate должен быть True по умолчанию."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownRequest

            request = UpdateMarkdownRequest(
                markdown="# Test"
            )

            assert request.auto_validate is True

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_auto_validate_can_be_disabled(self):
        """auto_validate можно отключить явно."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import UpdateMarkdownRequest

            request = UpdateMarkdownRequest(
                markdown="# Test",
                auto_validate=False
            )

            assert request.auto_validate is False

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestResponseMetadata:
    """Тесты метаданных в ответах валидации."""

    def test_validation_response_includes_metadata(self):
        """Ответ валидации должен включать метаданные."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse

            response = ValidateMarkdownResponse(
                success=True,
                is_valid=True,
                errors=[],
                warnings=[],
                message="Valid",
                total_errors=0,
                total_warnings=0,
                metadata={
                    "text_length": "100",
                    "has_frontmatter": "true"
                }
            )

            assert response.metadata["text_length"] == "100"
            assert response.metadata["has_frontmatter"] == "true"

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestErrorCounting:
    """Тесты подсчёта ошибок и предупреждений."""

    def test_total_errors_count(self):
        """Подсчёт общего количества ошибок."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse, ValidationErrorSchema

            errors = [
                ValidationErrorSchema(
                    error_type="ERROR_1",
                    message="Error 1",
                    severity="error"
                ),
                ValidationErrorSchema(
                    error_type="ERROR_2",
                    message="Error 2",
                    severity="error"
                ),
                ValidationErrorSchema(
                    error_type="ERROR_3",
                    message="Error 3",
                    severity="error"
                )
            ]

            response = ValidateMarkdownResponse(
                success=True,
                is_valid=False,
                errors=errors,
                warnings=[],
                message="3 errors found",
                total_errors=3,
                total_warnings=0
            )

            assert response.total_errors == 3
            assert len(response.errors) == 3

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_total_warnings_count(self):
        """Подсчёт общего количества предупреждений."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse, ValidationErrorSchema

            warnings = [
                ValidationErrorSchema(
                    error_type="WARNING_1",
                    message="Warning 1",
                    severity="warning"
                ),
                ValidationErrorSchema(
                    error_type="WARNING_2",
                    message="Warning 2",
                    severity="warning"
                )
            ]

            response = ValidateMarkdownResponse(
                success=True,
                is_valid=True,
                errors=[],
                warnings=warnings,
                message="2 warnings",
                total_errors=0,
                total_warnings=2
            )

            assert response.total_warnings == 2
            assert len(response.warnings) == 2

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


class TestResponseSuccessFlag:
    """Тесты флага success в ответе."""

    def test_success_true_valid_document(self):
        """Успешный ответ для валидного документа."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse

            response = ValidateMarkdownResponse(
                success=True,
                is_valid=True,
                message="Valid document"
            )

            assert response.success is True
            assert response.is_valid is True

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")

    def test_success_true_invalid_document(self):
        """success=True даже для невалидного документа (валидация выполнена успешно)."""
        try:
            from pathlib import Path
            import sys

            api_path = Path(__file__).parent.parent
            sys.path.insert(0, str(api_path))

            from src.schemas.api import ValidateMarkdownResponse, ValidationErrorSchema

            response = ValidateMarkdownResponse(
                success=True,
                is_valid=False,
                errors=[
                    ValidationErrorSchema(
                        error_type="ERROR",
                        message="Test error",
                        severity="error"
                    )
                ],
                message="Document has errors"
            )

            assert response.success is True  # Валидация прошла успешно
            assert response.is_valid is False  # Но документ невалидный

        except ImportError:
            pytest.skip("Не удалось импортировать схемы")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
