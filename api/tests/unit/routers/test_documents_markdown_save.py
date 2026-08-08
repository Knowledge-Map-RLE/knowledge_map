"""
Tests for web PUT /documents/{doc_id}/markdown handler.

Verifies that saving with annotate=true does NOT reject invalid markdown
(regression: strict validation was forced by annotate and blocked manual
"Save" in the annotator), while explicit strict_mode still rejects.
"""

import asyncio

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi import HTTPException

pytestmark = pytest.mark.unit

VALIDATION_INVALID = {
    "success": True,
    "is_valid": False,
    "errors": [
        {
            "error_type": "missing_frontmatter",
            "message": "Документ должен начинаться с блока YAML метаданных '---'",
            "severity": "error",
            "line": 1,
            "column": 1,
            "start_offset": 0,
            "end_offset": 80,
            "context": None,
            "suggestion": "Добавьте в начало документа блок YAML метаданных",
            "metadata": {},
        }
    ],
    "warnings": [],
    "message": "Найдено 1 ошибок и 0 предупреждений",
    "total_errors": 1,
    "total_warnings": 0,
    "metadata": {"text_length": 100, "has_frontmatter": "False"},
}

VALIDATION_VALID = {
    "success": True,
    "is_valid": True,
    "errors": [],
    "warnings": [],
    "message": "Markdown валидный",
    "total_errors": 0,
    "total_warnings": 0,
    "metadata": {"text_length": 100, "has_frontmatter": "True"},
}


def _fake_grpc_client(validation=VALIDATION_INVALID):
    client = MagicMock()
    client.validate_markdown = AsyncMock(return_value=validation)
    return client


class TestUpdateMarkdownAnnotate:
    def test_annotate_saves_invalid_markdown_without_status(self):
        """annotate=true saves invalid markdown (200), but does NOT mark annotated."""
        from web.routers.data_extraction.documents import update_document_markdown
        from src.schemas.api import UpdateMarkdownRequest

        request = UpdateMarkdownRequest(markdown="# Test\n\nfoo", annotate=True)

        mock_update = AsyncMock(
            return_value={"s3_key": "documents/doc_1/doc_1_user.md", "title": "Test"}
        )

        async def scenario():
            with patch(
                "web.routers.data_extraction.documents.update_markdown",
                new=mock_update,
            ), patch(
                "services.nlp_grpc_client.get_nlp_grpc_client",
                return_value=_fake_grpc_client(VALIDATION_INVALID),
            ):
                return await update_document_markdown(
                    "doc_1", request, doc_repo=MagicMock(), storage=MagicMock()
                )

        result = asyncio.run(scenario())

        assert result.success is True
        assert result.s3_key == "documents/doc_1/doc_1_user.md"
        assert result.validation is not None
        assert result.validation["is_valid"] is False

        mock_update.assert_awaited_once()
        kwargs = mock_update.call_args.kwargs
        assert kwargs["annotate"] is False
        assert kwargs["doc_id"] == "doc_1"

    def test_annotate_marks_annotated_for_valid_markdown(self):
        """annotate=true with valid markdown saves AND marks annotated."""
        from web.routers.data_extraction.documents import update_document_markdown
        from src.schemas.api import UpdateMarkdownRequest

        request = UpdateMarkdownRequest(markdown="# Test\n\nvalid", annotate=True)

        mock_update = AsyncMock(
            return_value={"s3_key": "documents/doc_1/doc_1_user.md", "title": "Test"}
        )

        async def scenario():
            with patch(
                "web.routers.data_extraction.documents.update_markdown",
                new=mock_update,
            ), patch(
                "services.nlp_grpc_client.get_nlp_grpc_client",
                return_value=_fake_grpc_client(VALIDATION_VALID),
            ):
                return await update_document_markdown(
                    "doc_1", request, doc_repo=MagicMock(), storage=MagicMock()
                )

        result = asyncio.run(scenario())

        assert result.success is True
        assert result.validation["is_valid"] is True

        mock_update.assert_awaited_once()
        assert mock_update.call_args.kwargs["annotate"] is True

    def test_strict_mode_still_rejects_invalid(self):
        """Explicit strict_mode=true keeps rejecting invalid markdown."""
        from web.routers.data_extraction.documents import update_document_markdown
        from src.schemas.api import UpdateMarkdownRequest

        request = UpdateMarkdownRequest(markdown="# Test\n\nfoo", annotate=True, strict_mode=True)

        async def scenario():
            with patch(
                "web.routers.data_extraction.documents.update_markdown",
                new=AsyncMock(),
            ), patch(
                "services.nlp_grpc_client.get_nlp_grpc_client",
                return_value=_fake_grpc_client(),
            ):
                await update_document_markdown(
                    "doc_1", request, doc_repo=MagicMock(), storage=MagicMock()
                )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.status_code == 400
        assert "Валидация" in exc_info.value.detail["error"]
