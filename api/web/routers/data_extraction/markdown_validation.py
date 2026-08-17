"""Роутер для валидации markdown документов"""
import logging
from fastapi import APIRouter, HTTPException

from src.schemas.api import ValidateMarkdownRequest, ValidateMarkdownResponse
from services.nlp_grpc_client import get_nlp_grpc_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["markdown-validation"])


@router.post(
    "/markdown/validate",
    response_model=ValidateMarkdownResponse,
    summary="Валидация канонического формата markdown",
    description="""
Валидирует markdown документ на соответствие каноническому формату:
- YAML frontmatter с полем doi (обязательны)
- Ровно один заголовок H1
- HTML таблицы (не markdown)
- HTML изображения (не markdown)
- Двунаправленные ссылки и References

Параметры:
- markdown: содержание markdown документа
- strict_mode: если True, warnings становятся errors
    """
)
async def validate_markdown(request: ValidateMarkdownRequest):
    """
    Валидация канонического формата markdown.

    Проверяет соответствие следующим правилам:
    1. YAML Frontmatter с полем doi (обязательны)
    2. H1 heading: ровно один заголовок первого уровня
    3. Tables: только HTML, не markdown таблицы
    4. Images: только HTML, не markdown изображения
    5. References: двунаправленная проверка цитат и ссылок

    Args:
        request: ValidateMarkdownRequest с markdown контентом

    Returns:
        ValidateMarkdownResponse с результатами валидации и ошибками

    Raises:
        HTTPException: если произойдёт ошибка при валидации
    """
    try:
        logger.info(f"Валидация markdown: длина текста={len(request.markdown)} символов")

        # Получить gRPC клиент и подключиться
        grpc_client = get_nlp_grpc_client()
        await grpc_client.connect()

        # Вызвать метод валидации
        result = await grpc_client.validate_markdown(
            markdown=request.markdown,
            strict_mode=request.strict_mode
        )

        logger.info(
            f"Результат валидации: is_valid={result['is_valid']}, "
            f"errors={result['total_errors']}, warnings={result['total_warnings']}"
        )

        # Конвертировать результат в ответ
        return ValidateMarkdownResponse(**result)

    except Exception as e:
        logger.error(f"Ошибка при валидации markdown: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка валидации: {str(e)}"
        )
