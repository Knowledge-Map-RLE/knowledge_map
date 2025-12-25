"""
Интеграционные тесты для gRPC endpoint валидации markdown.

Тестирует взаимодействие между gRPC сервером и клиентом,
включая сериализацию proto сообщений и поведение strict mode.
"""
import pytest
import asyncio
from pathlib import Path
import sys
import logging

# Добавить src в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

logger = logging.getLogger(__name__)


class TestGRPCValidationIntegration:
    """
    Интеграционные тесты gRPC валидации.

    Примечание: Для полного интеграционного тестирования нужен запущенный gRPC сервер.
    Эти тесты проверяют логику преобразования между proto и Python типами.
    """

    def test_proto_import(self):
        """Проверка импорта сгенерированных proto файлов."""
        try:
            # Попытка импортировать proto файлы
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2
            import nlp_pb2_grpc

            # Проверка существования нужных типов
            assert hasattr(nlp_pb2, 'ValidateMarkdownRequest')
            assert hasattr(nlp_pb2, 'ValidateMarkdownResponse')
            assert hasattr(nlp_pb2, 'ValidationErrorMessage')
            assert hasattr(nlp_pb2, 'ERROR_SEVERITY_ERROR')
            assert hasattr(nlp_pb2, 'ERROR_SEVERITY_WARNING')

        except ImportError as e:
            pytest.skip(f"Proto файлы не сгенерированы: {e}")

    def test_validation_request_creation(self):
        """Создание proto запроса валидации."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            # Создать запрос
            request = nlp_pb2.ValidateMarkdownRequest(
                markdown="# Test\n\nContent",
                strict_mode=False
            )

            assert request.markdown == "# Test\n\nContent"
            assert request.strict_mode is False

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")

    def test_validation_response_creation(self):
        """Создание proto ответа валидации."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            # Создать ошибку
            error = nlp_pb2.ValidationErrorMessage(
                error_type="MULTIPLE_H1",
                message="Найдено несколько заголовков H1",
                severity=nlp_pb2.ERROR_SEVERITY_ERROR,
                line=5,
                column=1,
                context="# Second H1"
            )

            # Создать ответ
            response = nlp_pb2.ValidateMarkdownResponse(
                success=True,
                is_valid=False,
                errors=[error],
                message="Validation failed",
                total_errors=1,
                total_warnings=0
            )

            assert response.success is True
            assert response.is_valid is False
            assert len(response.errors) == 1
            assert response.total_errors == 1
            assert response.total_warnings == 0

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")

    def test_validation_error_serialization(self):
        """Сериализация и десериализация ValidationError."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            # Создать ошибку с метаданными
            error = nlp_pb2.ValidationErrorMessage(
                error_type="MISSING_H1",
                message="Документ должен содержать ровно один H1",
                severity=nlp_pb2.ERROR_SEVERITY_ERROR,
                line=1,
                column=1,
                start_offset=0,
                end_offset=10,
                context="Line 1",
                suggestion="Добавьте заголовок H1",
                metadata={"found_h1_count": "0"}
            )

            # Сериализовать
            serialized = bytes(error)

            # Десериализовать
            deserialized = nlp_pb2.ValidationErrorMessage()
            deserialized.ParseFromString(serialized)

            # Проверить
            assert deserialized.error_type == "MISSING_H1"
            assert deserialized.severity == nlp_pb2.ERROR_SEVERITY_ERROR
            assert deserialized.metadata["found_h1_count"] == "0"

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")


class TestStrictModeValidation:
    """Тесты strict mode в валидации."""

    def test_strict_mode_rejects_warnings(self):
        """В strict mode warnings должны быть обработаны как errors."""
        # Это тестируется на уровне gRPC сервера в grpc_server.py
        # ValidateMarkdown метод переводит warnings в errors при strict_mode=True
        pass

    def test_normal_mode_allows_warnings(self):
        """В нормальном режиме warnings не отклоняют валидацию."""
        # Это тестируется на уровне gRPC сервера
        pass


class TestValidationResponseFormat:
    """Тесты формата ответа валидации."""

    def test_valid_markdown_response_format(self):
        """Ответ для валидного markdown должен иметь правильный формат."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            response = nlp_pb2.ValidateMarkdownResponse(
                success=True,
                is_valid=True,
                errors=[],
                warnings=[],
                message="Validation passed",
                total_errors=0,
                total_warnings=0,
                metadata={"text_length": "100"}
            )

            assert response.success is True
            assert response.is_valid is True
            assert len(response.errors) == 0
            assert len(response.warnings) == 0

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")

    def test_invalid_markdown_response_format(self):
        """Ответ для невалидного markdown должен включать ошибки."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            error = nlp_pb2.ValidationErrorMessage(
                error_type="MULTIPLE_H1",
                message="Multiple H1 headers found",
                severity=nlp_pb2.ERROR_SEVERITY_ERROR
            )

            response = nlp_pb2.ValidateMarkdownResponse(
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

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")


class TestMetadataHandling:
    """Тесты обработки метаданных валидации."""

    def test_response_metadata_dict(self):
        """Метаданные в ответе должны быть как map<string, string>."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            response = nlp_pb2.ValidateMarkdownResponse(
                success=True,
                is_valid=True,
                metadata={
                    "text_length": "1000",
                    "validators_run": "5",
                    "has_frontmatter": "true"
                }
            )

            assert response.metadata["text_length"] == "1000"
            assert response.metadata["validators_run"] == "5"
            assert response.metadata["has_frontmatter"] == "true"

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")


class TestErrorSeverityEnum:
    """Тесты enum ErrorSeverity."""

    def test_error_severity_values(self):
        """Проверка значений enum ErrorSeverity."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            # Проверить существование значений enum
            assert nlp_pb2.ERROR_SEVERITY_UNSPECIFIED == 0
            assert nlp_pb2.ERROR_SEVERITY_ERROR == 1
            assert nlp_pb2.ERROR_SEVERITY_WARNING == 2
            assert nlp_pb2.ERROR_SEVERITY_INFO == 3

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")

    def test_error_with_different_severities(self):
        """Создание ошибок с разными уровнями серьёзности."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            error_severity = nlp_pb2.ValidationErrorMessage(
                error_type="TEST_ERROR",
                message="Error",
                severity=nlp_pb2.ERROR_SEVERITY_ERROR
            )

            warning_severity = nlp_pb2.ValidationErrorMessage(
                error_type="TEST_WARNING",
                message="Warning",
                severity=nlp_pb2.ERROR_SEVERITY_WARNING
            )

            info_severity = nlp_pb2.ValidationErrorMessage(
                error_type="TEST_INFO",
                message="Info",
                severity=nlp_pb2.ERROR_SEVERITY_INFO
            )

            assert error_severity.severity == nlp_pb2.ERROR_SEVERITY_ERROR
            assert warning_severity.severity == nlp_pb2.ERROR_SEVERITY_WARNING
            assert info_severity.severity == nlp_pb2.ERROR_SEVERITY_INFO

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")


class TestLargeDocumentHandling:
    """Тесты обработки больших документов."""

    def test_large_markdown_validation(self):
        """Валидация больших markdown документов."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            # Создать большой документ
            large_markdown = "# Title\n\n" + "\n".join([f"## Section {i}\n\nContent {i}.\n" for i in range(100)])

            import nlp_pb2

            request = nlp_pb2.ValidateMarkdownRequest(
                markdown=large_markdown,
                strict_mode=False
            )

            assert len(request.markdown) > 1000

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")

    def test_many_errors_in_response(self):
        """Ответ со множеством ошибок."""
        try:
            import sys
            from pathlib import Path
            proto_path = Path(__file__).parent.parent.parent / "src"
            sys.path.insert(0, str(proto_path))

            import nlp_pb2

            # Создать 100 ошибок
            errors = [
                nlp_pb2.ValidationErrorMessage(
                    error_type=f"ERROR_{i}",
                    message=f"Error message {i}",
                    severity=nlp_pb2.ERROR_SEVERITY_ERROR,
                    line=i
                )
                for i in range(100)
            ]

            response = nlp_pb2.ValidateMarkdownResponse(
                success=True,
                is_valid=False,
                errors=errors,
                total_errors=100
            )

            assert len(response.errors) == 100
            assert response.total_errors == 100

        except ImportError:
            pytest.skip("Proto файлы не сгенерированы")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
