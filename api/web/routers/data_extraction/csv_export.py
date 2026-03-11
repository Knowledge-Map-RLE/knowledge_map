"""Роутер для экспорта и импорта аннотаций в формате YAML"""
import logging
import io
import yaml
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from src.models import PDFDocument
from services.yaml_export_service import YAMLExportService
from services.data_extraction_service import DataExtractionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["yaml_export"])
yaml_service = YAMLExportService()
data_extraction_service = DataExtractionService()


@router.get("/annotations/export-yaml")
async def export_annotations_yaml(doc_id: str):
    """
    Экспортировать все аннотации и связи документа в YAML файл.

    Args:
        doc_id: ID документа

    Returns:
        YAML файл с аннотациями и связями
    """
    try:
        # Получить документ
        doc = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не найден")

        # Определить имя файла
        if doc.doi:
            filename = f"{doc.doi}.yaml"
        else:
            base_name = doc.original_filename.rsplit('.', 1)[0] if doc.original_filename else doc_id
            filename = f"{base_name}_annotations.yaml"

        # Получить все аннотации и связи через YAML сервис
        data = yaml_service.export_annotations_to_yaml(doc_id)

        # Создать YAML в памяти
        output = io.StringIO()
        yaml.safe_dump(
            data,
            output,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2
        )

        # Вернуть YAML файл
        output.seek(0)
        yaml_content = output.getvalue()

        # Кодировка UTF-8 без BOM
        yaml_bytes = yaml_content.encode('utf-8')

        return StreamingResponse(
            io.BytesIO(yaml_bytes),
            media_type="application/x-yaml; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка экспорта аннотаций в YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {str(e)}")


@router.post("/annotations/import-yaml")
async def import_annotations_yaml(doc_id: str, file: UploadFile = File(...)):
    """
    Импортировать аннотации и связи из YAML файла.

    Args:
        doc_id: ID документа
        file: YAML файл с аннотациями

    Returns:
        Статистика импорта
    """
    try:
        # Проверить существование документа
        doc = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не найден")

        # Получить текст документа для валидации офсетов
        markdown_data = await data_extraction_service.get_document_markdown(doc_id)
        text_length = len(markdown_data.get("text", ""))

        # Прочитать YAML файл
        contents = await file.read()
        yaml_text = contents.decode('utf-8')
        data = yaml.safe_load(yaml_text)

        # Импортировать аннотации и связи через YAML сервис
        result = await yaml_service.import_annotations_from_dict(
            doc_id=doc_id,
            data=data,
            text_length=text_length
        )

        return {
            "success": result["success"],
            "message": "Импорт завершен",
            "created_annotations": result["created_annotations"],
            "created_relations": result["created_relations"],
            "total_in_file": result["total_in_file"],
            "errors": result.get("errors", [])
        }

    except HTTPException:
        raise
    except yaml.YAMLError as e:
        logger.error(f"Ошибка парсинга YAML: {e}")
        raise HTTPException(status_code=400, detail=f"Некорректный формат YAML: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка импорта аннотаций из YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка импорта: {str(e)}")
