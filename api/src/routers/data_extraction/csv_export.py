"""Роутер для экспорта и импорта аннотаций в формате CSV"""
import logging
import csv
import io
import json
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from src.models import PDFDocument
from services.annotation_service import AnnotationService
from services.data_extraction_service import DataExtractionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["csv_export"])
annotation_service = AnnotationService()
data_extraction_service = DataExtractionService()


@router.get("/annotations/export-csv")
async def export_annotations_csv(doc_id: str):
    """
    Экспортировать все аннотации и связи документа в CSV файл.

    Args:
        doc_id: ID документа

    Returns:
        CSV файл с аннотациями и связями
    """
    try:
        # Получить документ
        doc = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не найден")

        # Определить имя файла
        if doc.doi:
            filename = f"{doc.doi}.csv"
        else:
            base_name = doc.original_filename.rsplit('.', 1)[0] if doc.original_filename else doc_id
            filename = f"{base_name}_annotations.csv"

        # Получить все аннотации
        annotations_response = await annotation_service.get_annotations(
            doc_id=doc_id,
            skip=0,
            limit=None
        )
        annotations = annotations_response.get("annotations", [])

        # Получить все связи
        relations = await annotation_service.get_relations(doc_id)

        # Создать CSV в памяти
        output = io.StringIO()

        # Записать метаданные документа как комментарии
        output.write(f"# Document ID: {doc_id}\n")
        output.write(f"# DOI: {doc.doi or 'N/A'}\n")
        output.write(f"# Filename: {doc.original_filename or 'N/A'}\n")
        output.write(f"# Title: {doc.title or 'N/A'}\n")
        output.write("\n")

        # Секция ANNOTATIONS
        output.write("ANNOTATIONS\n")
        ann_writer = csv.writer(output)
        ann_writer.writerow([
            "uid", "text", "annotation_type", "start_offset", "end_offset",
            "color", "source", "confidence", "processor_version", "created_date", "metadata_json"
        ])

        for ann in annotations:
            metadata_json = json.dumps(ann.get("metadata", {})) if ann.get("metadata") else ""
            ann_writer.writerow([
                ann.get("uid", ""),
                ann.get("text", ""),
                ann.get("annotation_type", ""),
                ann.get("start_offset", ""),
                ann.get("end_offset", ""),
                ann.get("color", "#ffeb3b"),
                ann.get("source", "user"),
                ann.get("confidence", ""),
                ann.get("processor_version", ""),
                ann.get("created_date", ""),
                metadata_json
            ])

        # Пустая строка-разделитель
        output.write("\n")

        # Секция RELATIONS
        output.write("RELATIONS\n")
        rel_writer = csv.writer(output)
        rel_writer.writerow([
            "relation_uid", "source_uid", "target_uid", "relation_type", "created_date", "metadata_json"
        ])

        for rel in relations:
            metadata_json = json.dumps(rel.get("metadata", {})) if rel.get("metadata") else ""
            rel_writer.writerow([
                rel.get("relation_uid", ""),
                rel.get("source_uid", ""),
                rel.get("target_uid", ""),
                rel.get("relation_type", ""),
                rel.get("created_date", ""),
                metadata_json
            ])

        # Вернуть CSV файл
        output.seek(0)
        csv_content = output.getvalue()

        # Кодировка UTF-8 без BOM
        csv_bytes = csv_content.encode('utf-8')

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка экспорта аннотаций в CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {str(e)}")


@router.post("/annotations/import-csv")
async def import_annotations_csv(doc_id: str, file: UploadFile = File(...)):
    """
    Импортировать аннотации и связи из CSV файла.

    Args:
        doc_id: ID документа
        file: CSV файл с аннотациями

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

        # Прочитать CSV файл
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        lines = csv_text.splitlines()

        # Парсинг CSV
        annotations_to_create = []
        relations_to_create = []
        current_section = None

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Пропустить комментарии и пустые строки
            if line.startswith('#') or not line:
                i += 1
                continue

            # Определить секцию
            if line == "ANNOTATIONS":
                current_section = "annotations"
                i += 1
                # Пропустить заголовок
                if i < len(lines):
                    i += 1
                continue
            elif line == "RELATIONS":
                current_section = "relations"
                i += 1
                # Пропустить заголовок
                if i < len(lines):
                    i += 1
                continue

            # Парсить строки
            if current_section == "annotations":
                reader = csv.reader([lines[i]])
                row = next(reader)
                if len(row) >= 11:
                    try:
                        start_offset = int(row[3])
                        end_offset = int(row[4])

                        # Валидация офсетов
                        if start_offset < 0 or end_offset > text_length or start_offset >= end_offset:
                            logger.warning(f"Пропуск аннотации с невалидными офсетами: {start_offset}-{end_offset}")
                            i += 1
                            continue

                        metadata = json.loads(row[10]) if row[10] else {}

                        annotations_to_create.append({
                            "text": row[1],
                            "annotation_type": row[2],
                            "start_offset": start_offset,
                            "end_offset": end_offset,
                            "color": row[5] or "#ffeb3b",
                            "source": "file",  # Всегда устанавливаем source="file"
                            "confidence": float(row[7]) if row[7] else None,
                            "processor_version": row[8] or None,
                            "metadata": metadata
                        })
                    except (ValueError, json.JSONDecodeError) as e:
                        logger.warning(f"Ошибка парсинга аннотации: {e}")

            elif current_section == "relations":
                reader = csv.reader([lines[i]])
                row = next(reader)
                if len(row) >= 6:
                    try:
                        metadata = json.loads(row[5]) if row[5] else {}

                        relations_to_create.append({
                            "source_uid": row[1],
                            "target_uid": row[2],
                            "relation_type": row[3],
                            "metadata": metadata
                        })
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга связи: {e}")

            i += 1

        # Создать аннотации
        created_annotations = 0
        annotation_uid_map = {}  # старый uid -> новый uid

        for ann_data in annotations_to_create:
            try:
                result = await annotation_service.create_annotation(
                    doc_id=doc_id,
                    start_offset=ann_data["start_offset"],
                    end_offset=ann_data["end_offset"],
                    text=ann_data["text"],
                    annotation_type=ann_data["annotation_type"],
                    color=ann_data["color"],
                    source=ann_data["source"],
                    confidence=ann_data["confidence"],
                    metadata=ann_data["metadata"]
                )
                created_annotations += 1
                # Сохранить маппинг для связей
                if result.get("uid"):
                    annotation_uid_map[ann_data["text"]] = result["uid"]
            except Exception as e:
                logger.warning(f"Ошибка создания аннотации: {e}")

        # Создать связи
        created_relations = 0
        for rel_data in relations_to_create:
            try:
                await annotation_service.create_relation(
                    source_id=rel_data["source_uid"],
                    target_id=rel_data["target_uid"],
                    relation_type=rel_data["relation_type"],
                    metadata=rel_data["metadata"]
                )
                created_relations += 1
            except Exception as e:
                logger.warning(f"Ошибка создания связи: {e}")

        return {
            "success": True,
            "message": f"Импорт завершен",
            "created_annotations": created_annotations,
            "created_relations": created_relations,
            "total_in_file": {
                "annotations": len(annotations_to_create),
                "relations": len(relations_to_create)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка импорта аннотаций из CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка импорта: {str(e)}")
