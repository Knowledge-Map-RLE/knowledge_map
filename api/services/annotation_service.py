"""Сервис для работы с аннотациями Markdown документов"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import HTTPException
from neomodel import db

from src.models import MarkdownAnnotation, PDFDocument, User, AnnotationRelationRel

logger = logging.getLogger(__name__)


class AnnotationService:
    """Сервис для управления аннотациями Markdown текста"""

    async def create_annotation(
        self,
        doc_id: str,
        text: str,
        annotation_type: str,
        start_offset: int,
        end_offset: int,
        color: str = "#ffeb3b",
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Создать новую аннотацию для документа

        Args:
            doc_id: ID документа
            text: Аннотируемый текст
            annotation_type: Тип аннотации
            start_offset: Начальная позиция в тексте
            end_offset: Конечная позиция в тексте
            color: Цвет выделения (hex)
            user_id: ID пользователя (опционально)
            metadata: Дополнительные метаданные
            confidence: Уверенность NLP модели (0.0-1.0)

        Returns:
            Словарь с данными созданной аннотации
        """
        try:
            # Проверка существования документа
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if not document:
                raise HTTPException(status_code=404, detail=f"Документ {doc_id} не найден")

            # Валидация позиций
            if start_offset < 0 or end_offset <= start_offset:
                raise HTTPException(
                    status_code=400,
                    detail="Некорректные позиции аннотации: start_offset должен быть >= 0 и end_offset > start_offset"
                )

            # Создание аннотации
            annotation = MarkdownAnnotation(
                text=text,
                annotation_type=annotation_type,
                start_offset=start_offset,
                end_offset=end_offset,
                color=color,
                metadata=metadata or {},
                confidence=confidence,
                created_date=datetime.utcnow()
            ).save()

            # Связь с документом
            document.markdown_annotations.connect(annotation)

            # Связь с пользователем (если указан)
            if user_id:
                user = User.nodes.get_or_none(uid=user_id)
                if user:
                    annotation.created_by.connect(user)

            logger.info(f"Создана аннотация {annotation.uid} для документа {doc_id}")

            return self._annotation_to_dict(annotation)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка создания аннотации: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка создания аннотации: {str(e)}")

    async def get_annotations(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Получить все аннотации документа

        Args:
            doc_id: ID документа

        Returns:
            Список аннотаций
        """
        try:
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if not document:
                raise HTTPException(status_code=404, detail=f"Документ {doc_id} не найден")

            # Получаем все markdown аннотации документа
            # Используем Cypher запрос для получения аннотаций
            query = """
            MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
            RETURN a
            ORDER BY a.start_offset
            """
            results, meta = db.cypher_query(query, {'doc_id': doc_id})

            annotations = []
            for row in results:
                ann_node = MarkdownAnnotation.inflate(row[0])
                annotations.append(self._annotation_to_dict(ann_node))

            logger.info(f"Получено {len(annotations)} аннотаций для документа {doc_id}")
            return annotations

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка получения аннотаций: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка получения аннотаций: {str(e)}")

    async def update_annotation(
        self,
        annotation_id: str,
        text: Optional[str] = None,
        annotation_type: Optional[str] = None,
        start_offset: Optional[int] = None,
        end_offset: Optional[int] = None,
        color: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Обновить существующую аннотацию

        Args:
            annotation_id: ID аннотации
            text: Новый текст (опционально)
            annotation_type: Новый тип (опционально)
            start_offset: Новая начальная позиция (опционально)
            end_offset: Новая конечная позиция (опционально)
            color: Новый цвет (опционально)
            metadata: Новые метаданные (опционально)

        Returns:
            Обновленная аннотация
        """
        try:
            annotation = MarkdownAnnotation.nodes.get_or_none(uid=annotation_id)
            if not annotation:
                raise HTTPException(status_code=404, detail=f"Аннотация {annotation_id} не найдена")

            # Обновление полей
            if text is not None:
                annotation.text = text
            if annotation_type is not None:
                annotation.annotation_type = annotation_type
            if start_offset is not None:
                annotation.start_offset = start_offset
            if end_offset is not None:
                annotation.end_offset = end_offset
            if color is not None:
                annotation.color = color
            if metadata is not None:
                annotation.metadata = metadata

            # Валидация позиций после обновления
            if annotation.start_offset < 0 or annotation.end_offset <= annotation.start_offset:
                raise HTTPException(
                    status_code=400,
                    detail="Некорректные позиции аннотации после обновления"
                )

            annotation.save()
            logger.info(f"Обновлена аннотация {annotation_id}")

            return self._annotation_to_dict(annotation)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка обновления аннотации: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка обновления аннотации: {str(e)}")

    async def delete_annotation(self, annotation_id: str) -> Dict[str, str]:
        """
        Удалить аннотацию

        Args:
            annotation_id: ID аннотации

        Returns:
            Сообщение об успешном удалении
        """
        try:
            annotation = MarkdownAnnotation.nodes.get_or_none(uid=annotation_id)
            if not annotation:
                raise HTTPException(status_code=404, detail=f"Аннотация {annotation_id} не найдена")

            # Удаляем все связи перед удалением узла
            annotation.delete()

            logger.info(f"Удалена аннотация {annotation_id}")
            return {"message": f"Аннотация {annotation_id} успешно удалена"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка удаления аннотации: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка удаления аннотации: {str(e)}")

    async def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Создать связь между двумя аннотациями

        Args:
            source_id: ID исходной аннотации
            target_id: ID целевой аннотации
            relation_type: Тип связи
            metadata: Дополнительные метаданные

        Returns:
            Данные созданной связи
        """
        try:
            source = MarkdownAnnotation.nodes.get_or_none(uid=source_id)
            if not source:
                raise HTTPException(status_code=404, detail=f"Исходная аннотация {source_id} не найдена")

            target = MarkdownAnnotation.nodes.get_or_none(uid=target_id)
            if not target:
                raise HTTPException(status_code=404, detail=f"Целевая аннотация {target_id} не найдена")

            if source_id == target_id:
                raise HTTPException(status_code=400, detail="Нельзя создать связь аннотации с самой собой")

            # Создание связи
            rel = source.relations_to.connect(target, {
                'relation_type': relation_type,
                'created_date': datetime.utcnow(),
                'metadata': metadata or {}
            })

            logger.info(f"Создана связь '{relation_type}' между аннотациями {source_id} -> {target_id}")

            # Получаем UID связи
            rel_data = source.relations_to.relationship(target)

            return {
                "relation_uid": rel_data.uid,
                "source_uid": source_id,
                "target_uid": target_id,
                "relation_type": relation_type,
                "created_date": rel_data.created_date.isoformat() if rel_data.created_date else None,
                "metadata": rel_data.metadata or {}
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка создания связи: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка создания связи: {str(e)}")

    async def delete_relation(self, source_id: str, target_id: str) -> Dict[str, str]:
        """
        Удалить связь между аннотациями

        Args:
            source_id: ID исходной аннотации
            target_id: ID целевой аннотации

        Returns:
            Сообщение об успешном удалении
        """
        try:
            source = MarkdownAnnotation.nodes.get_or_none(uid=source_id)
            if not source:
                raise HTTPException(status_code=404, detail=f"Исходная аннотация {source_id} не найдена")

            target = MarkdownAnnotation.nodes.get_or_none(uid=target_id)
            if not target:
                raise HTTPException(status_code=404, detail=f"Целевая аннотация {target_id} не найдена")

            # Удаление связи
            source.relations_to.disconnect(target)

            logger.info(f"Удалена связь между аннотациями {source_id} -> {target_id}")
            return {"message": f"Связь между {source_id} и {target_id} успешно удалена"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка удаления связи: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка удаления связи: {str(e)}")

    async def get_relations(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Получить все связи между аннотациями документа

        Args:
            doc_id: ID документа

        Returns:
            Список связей
        """
        try:
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if not document:
                raise HTTPException(status_code=404, detail=f"Документ {doc_id} не найден")

            # Cypher запрос для получения всех связей между аннотациями документа
            query = """
            MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a1:MarkdownAnnotation)
            MATCH (a1)-[r:RELATES_TO]->(a2:MarkdownAnnotation)
            RETURN a1.uid AS source_uid, a2.uid AS target_uid, r.relation_type AS relation_type,
                   r.uid AS relation_uid, r.created_date AS created_date, r.metadata AS metadata
            """
            results, meta = db.cypher_query(query, {'doc_id': doc_id})

            relations = []
            for row in results:
                try:
                    # Проверяем, что все необходимые данные присутствуют
                    if not row[0] or not row[1]:
                        logger.warning(f"Пропускаем связь с отсутствующими аннотациями: {row}")
                        continue

                    # Обработка created_date - может быть datetime, float (timestamp) или None
                    created_date_value = row[4]
                    created_date_str = None
                    if created_date_value:
                        if hasattr(created_date_value, 'isoformat'):
                            # Это datetime объект
                            created_date_str = created_date_value.isoformat()
                        elif isinstance(created_date_value, (int, float)):
                            # Это Unix timestamp
                            created_date_str = datetime.fromtimestamp(created_date_value).isoformat()
                        else:
                            # Пытаемся конвертировать в строку
                            created_date_str = str(created_date_value)

                    relations.append({
                        "source_uid": row[0],
                        "target_uid": row[1],
                        "relation_type": row[2] or "RELATED",
                        "relation_uid": row[3],
                        "created_date": created_date_str,
                        "metadata": row[5] or {}
                    })
                except Exception as e:
                    logger.warning(f"Ошибка обработки связи: {e}, row: {row}")
                    continue

            logger.info(f"Получено {len(relations)} связей для документа {doc_id}")
            return relations

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка получения связей: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка получения связей: {str(e)}")

    async def batch_update_offsets(self, updates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Массовое обновление offset аннотаций

        Args:
            updates: Список обновлений формата [{annotation_id, start_offset, end_offset}, ...]

        Returns:
            Статус выполнения с количеством обновленных аннотаций
        """
        updated_count = 0
        errors = []

        try:
            for update in updates:
                try:
                    annotation_id = update.get("annotation_id")
                    start_offset = update.get("start_offset")
                    end_offset = update.get("end_offset")

                    if not annotation_id or start_offset is None or end_offset is None:
                        errors.append(f"Пропущено обновление с неполными данными: {update}")
                        continue

                    # Валидация
                    if start_offset < 0 or end_offset <= start_offset:
                        errors.append(
                            f"Аннотация {annotation_id}: некорректные offset (start={start_offset}, end={end_offset})"
                        )
                        continue

                    annotation = MarkdownAnnotation.nodes.get_or_none(uid=annotation_id)
                    if not annotation:
                        errors.append(f"Аннотация {annotation_id} не найдена")
                        continue

                    # Обновление offset
                    annotation.start_offset = start_offset
                    annotation.end_offset = end_offset
                    annotation.save()

                    updated_count += 1

                except Exception as e:
                    errors.append(f"Ошибка обновления аннотации {update.get('annotation_id', 'unknown')}: {str(e)}")
                    continue

            logger.info(f"Batch update: обновлено {updated_count} аннотаций, ошибок: {len(errors)}")

            return {
                "success": len(errors) == 0 or updated_count > 0,
                "updated_count": updated_count,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Критическая ошибка batch update: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка массового обновления: {str(e)}")

    def _annotation_to_dict(self, annotation: MarkdownAnnotation) -> Dict[str, Any]:
        """Конвертировать аннотацию в словарь для JSON ответа"""
        return {
            "uid": annotation.uid,
            "text": annotation.text,
            "annotation_type": annotation.annotation_type,
            "start_offset": annotation.start_offset,
            "end_offset": annotation.end_offset,
            "color": annotation.color,
            "metadata": annotation.metadata or {},
            "confidence": annotation.confidence,
            "created_date": annotation.created_date.isoformat() if annotation.created_date else None
        }

