#!/usr/bin/env python3
"""
gRPC клиент для взаимодействия с NLP сервисом
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

import grpc
from grpc import aio

# Импортируем сгенерированные proto файлы
sys.path.append(str(Path(__file__).parent.parent / "utils" / "generated"))
import nlp_pb2
import nlp_pb2_grpc

logger = logging.getLogger(__name__)

logger.info("[grpc_client] Модуль nlp_grpc_client импортирован")


class NLPGRPCClient:
    """gRPC клиент для NLP сервиса"""

    def __init__(self, host: str = None, port: int = None):
        import os
        # Для локального запуска используем жестко заданные значения
        # В Docker эти значения будут переопределены переменными окружения
        env_host = os.getenv("NLP_SERVICE_HOST", "127.0.0.1")
        env_port = os.getenv("NLP_SERVICE_PORT", "50055")

        # Если переменные окружения не установлены, используем значения для локального запуска
        if env_host == "127.0.0.1" and env_port == "50055":
            # Локальный запуск - NLP сервис работает на порту 50055
            self.host = host or "127.0.0.1"
            self.port = port or 50055
        else:
            # Docker запуск - используем переменные окружения
            self.host = host or env_host
            self.port = port or int(env_port)

        self.channel = None
        self.stub = None
        self._connected = False
        logger.info(f"[grpc_client] Создан клиент с хостом: {self.host}, портом: {self.port}")
        logger.info(f"[grpc_client] Переменные окружения: NLP_SERVICE_HOST={env_host}, NLP_SERVICE_PORT={env_port}")

    async def connect(self):
        """Подключение к gRPC серверу"""
        try:
            if not self._connected:
                logger.info(f"[grpc_client] Пытаемся подключиться к {self.host}:{self.port}")
                self.channel = aio.insecure_channel(f"{self.host}:{self.port}")
                self.stub = nlp_pb2_grpc.NLPServiceStub(self.channel)
                self._connected = True
                logger.info(f"[grpc_client] Подключен к {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка подключения к {self.host}:{self.port}: {e}")
            raise

    async def disconnect(self):
        """Отключение от gRPC сервера"""
        if self.channel:
            await self.channel.close()
            self._connected = False
            logger.info("[grpc_client] Отключен от сервера")

    async def process_text(
        self,
        text: str,
        processor_names: Optional[List[str]] = None,
        merge_results: bool = False,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Обработка текста с аннотациями и отношениями

        Args:
            text: Текст для обработки
            processor_names: Список имён процессоров (если пусто - все)
            merge_results: Объединить результаты разных процессоров
            timeout: Таймаут в секундах

        Returns:
            Результат обработки
        """
        try:
            await self.connect()

            logger.info(f"[grpc_client] Отправляем запрос ProcessText: длина текста={len(text)}")

            # Создаем запрос
            request = nlp_pb2.ProcessTextRequest(
                text=text,
                processor_names=processor_names or [],
                merge_results=merge_results
            )

            # Вызываем метод
            response = await self.stub.ProcessText(request, timeout=timeout)

            logger.info(f"[grpc_client] Получен ответ ProcessText: success={response.success}")

            # Конвертируем proto в dict
            result = {
                "success": response.success,
                "results": [self._proto_result_to_dict(r) for r in response.results],
                "merged_result": self._proto_result_to_dict(response.merged_result) if response.HasField("merged_result") else None,
                "message": response.message
            }

            return result

        except grpc.RpcError as e:
            logger.error(f"[grpc_client] gRPC ошибка в process_text: {e.code()}: {e.details()}")
            raise
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка в process_text: {e}")
            raise

    async def process_selection(
        self,
        text: str,
        selection: str,
        start_offset: int,
        end_offset: int,
        processor_names: Optional[List[str]] = None,
        merge_results: bool = False,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Обработка выделенного фрагмента текста

        Args:
            text: Полный текст
            selection: Выделенный текст
            start_offset: Начальное смещение
            end_offset: Конечное смещение
            processor_names: Список имён процессоров
            merge_results: Объединить результаты
            timeout: Таймаут в секундах

        Returns:
            Результат обработки
        """
        try:
            await self.connect()

            logger.info(f"[grpc_client] Отправляем запрос ProcessSelection: selection='{selection}'")

            # Создаем запрос
            request = nlp_pb2.ProcessSelectionRequest(
                text=text,
                selection=selection,
                start_offset=start_offset,
                end_offset=end_offset,
                processor_names=processor_names or [],
                merge_results=merge_results
            )

            # Вызываем метод
            response = await self.stub.ProcessSelection(request, timeout=timeout)

            logger.info(f"[grpc_client] Получен ответ ProcessSelection: success={response.success}")

            # Конвертируем proto в dict
            result = {
                "success": response.success,
                "results": [self._proto_result_to_dict(r) for r in response.results],
                "merged_result": self._proto_result_to_dict(response.merged_result) if response.HasField("merged_result") else None,
                "message": response.message
            }

            return result

        except grpc.RpcError as e:
            logger.error(f"[grpc_client] gRPC ошибка в process_selection: {e.code()}: {e.details()}")
            raise
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка в process_selection: {e}")
            raise

    async def analyze_text(
        self,
        text: str,
        levels: Optional[List[str]] = None,
        enable_voting: bool = True,
        min_agreement: int = 2,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Многоуровневый лингвистический анализ

        Args:
            text: Текст для анализа
            levels: Список уровней анализа ("tokenization", "morphology", "syntax" и т.д.)
            enable_voting: Использовать voting между процессорами
            min_agreement: Минимальное количество процессоров для согласия
            timeout: Таймаут в секундах

        Returns:
            Результат анализа с UnifiedDocument
        """
        try:
            await self.connect()

            logger.info(f"[grpc_client] Отправляем запрос AnalyzeText: длина текста={len(text)}")

            # Конвертируем уровни в proto enum
            level_map = {
                "tokenization": nlp_pb2.LEVEL_TOKENIZATION,
                "morphology": nlp_pb2.LEVEL_MORPHOLOGY,
                "syntax": nlp_pb2.LEVEL_SYNTAX,
                "semantic_roles": nlp_pb2.LEVEL_SEMANTIC_ROLES,
                "lexical_semantics": nlp_pb2.LEVEL_LEXICAL_SEMANTICS,
                "discourse": nlp_pb2.LEVEL_DISCOURSE,
            }

            proto_levels = [level_map[l.lower()] for l in (levels or [])]

            # Создаем запрос
            request = nlp_pb2.AnalyzeTextRequest(
                text=text,
                levels=proto_levels,
                enable_voting=enable_voting,
                min_agreement=min_agreement
            )

            # Вызываем метод
            response = await self.stub.AnalyzeText(request, timeout=timeout)

            logger.info(f"[grpc_client] Получен ответ AnalyzeText: success={response.success}")

            # Конвертируем proto в dict
            result = {
                "success": response.success,
                "document": self._proto_document_to_dict(response.document) if response.HasField("document") else None,
                "message": response.message,
                "processing_time": response.processing_time
            }

            return result

        except grpc.RpcError as e:
            logger.error(f"[grpc_client] gRPC ошибка в analyze_text: {e.code()}: {e.details()}")
            raise
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка в analyze_text: {e}")
            raise

    async def get_supported_types(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Получение списка поддерживаемых типов процессоров

        Args:
            timeout: Таймаут в секундах

        Returns:
            Информация о поддерживаемых типах
        """
        try:
            await self.connect()

            logger.info("[grpc_client] Отправляем запрос GetSupportedTypes")

            # Создаем запрос
            request = nlp_pb2.GetSupportedTypesRequest()

            # Вызываем метод
            response = await self.stub.GetSupportedTypes(request, timeout=timeout)

            logger.info(f"[grpc_client] Получен ответ GetSupportedTypes: {len(response.processors)} процессоров")

            # Конвертируем proto в dict
            result = {
                "processors": [self._proto_processor_info_to_dict(p) for p in response.processors],
                "annotation_types": list(response.annotation_types),
                "relation_types": list(response.relation_types)
            }

            return result

        except grpc.RpcError as e:
            logger.error(f"[grpc_client] gRPC ошибка в get_supported_types: {e.code()}: {e.details()}")
            raise
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка в get_supported_types: {e}")
            raise

    def _proto_result_to_dict(self, result) -> Dict[str, Any]:
        """Конвертирует ProcessingResult из proto в dict"""
        return {
            "annotations": [self._proto_annotation_to_dict(a) for a in result.annotations],
            "relations": [self._proto_relation_to_dict(r) for r in result.relations],
            "processor_name": result.processor_name,
            "processor_version": result.processor_version,
            "processing_time": result.processing_time,
            "metadata": dict(result.metadata)
        }

    def _proto_annotation_to_dict(self, annotation) -> Dict[str, Any]:
        """Конвертирует AnnotationSuggestion из proto в dict"""
        return {
            "text": annotation.text,
            "annotation_type": annotation.annotation_type,
            "category": nlp_pb2.AnnotationCategory.Name(annotation.category),
            "start_offset": annotation.start_offset,
            "end_offset": annotation.end_offset,
            "confidence": annotation.confidence,
            "source": nlp_pb2.AnnotationSource.Name(annotation.source),
            "color": annotation.color,
            "metadata": dict(annotation.metadata)
        }

    def _proto_relation_to_dict(self, relation) -> Dict[str, Any]:
        """Конвертирует RelationSuggestion из proto в dict"""
        return {
            "source_text": relation.source_text,
            "target_text": relation.target_text,
            "source_start": relation.source_start,
            "source_end": relation.source_end,
            "target_start": relation.target_start,
            "target_end": relation.target_end,
            "relation_type": relation.relation_type,
            "confidence": relation.confidence,
            "source": nlp_pb2.AnnotationSource.Name(relation.source),
            "metadata": dict(relation.metadata)
        }

    def _proto_document_to_dict(self, document) -> Dict[str, Any]:
        """Конвертирует UnifiedDocument из proto в dict"""
        return {
            "text": document.text,
            "sentences": [self._proto_sentence_to_dict(s) for s in document.sentences],
            "entities": [self._proto_entity_to_dict(e) for e in document.entities],
            "metadata": dict(document.metadata),
            "processing_time": document.processing_time,
            "processors_used": list(document.processors_used)
        }

    def _proto_sentence_to_dict(self, sentence) -> Dict[str, Any]:
        """Конвертирует UnifiedSentence из proto в dict"""
        return {
            "idx": sentence.idx,
            "text": sentence.text,
            "start_char": sentence.start_char,
            "end_char": sentence.end_char,
            "tokens": [self._proto_token_to_dict(t) for t in sentence.tokens],
            "dependencies": [self._proto_dependency_to_dict(d) for d in sentence.dependencies],
            "phrases": [self._proto_phrase_to_dict(p) for p in sentence.phrases],
            "entities": [self._proto_entity_to_dict(e) for e in sentence.entities],
            "confidence": sentence.confidence,
            "metadata": dict(sentence.metadata)
        }

    def _proto_token_to_dict(self, token) -> Dict[str, Any]:
        """Конвертирует UnifiedToken из proto в dict"""
        return {
            "idx": token.idx,
            "text": token.text,
            "start_char": token.start_char,
            "end_char": token.end_char,
            "lemma": token.lemma,
            "pos": token.pos,
            "pos_fine": token.pos_fine,
            "morph": dict(token.morph),
            "confidence": token.confidence,
            "sources": list(token.sources),
            "is_stop": token.is_stop,
            "is_punct": token.is_punct,
            "is_space": token.is_space,
            "is_scientific_term": token.is_scientific_term,
            "scientific_category": token.scientific_category
        }

    def _proto_dependency_to_dict(self, dep) -> Dict[str, Any]:
        """Конвертирует UnifiedDependency из proto в dict"""
        return {
            "head_idx": dep.head_idx,
            "dependent_idx": dep.dependent_idx,
            "relation": dep.relation,
            "confidence": dep.confidence,
            "sources": list(dep.sources),
            "metadata": dict(dep.metadata)
        }

    def _proto_phrase_to_dict(self, phrase) -> Dict[str, Any]:
        """Конвертирует UnifiedPhrase из proto в dict"""
        return {
            "phrase_type": phrase.phrase_type,
            "start_idx": phrase.start_idx,
            "end_idx": phrase.end_idx,
            "tokens": [self._proto_token_to_dict(t) for t in phrase.tokens],
            "head_idx": phrase.head_idx,
            "confidence": phrase.confidence,
            "sources": list(phrase.sources)
        }

    def _proto_entity_to_dict(self, entity) -> Dict[str, Any]:
        """Конвертирует UnifiedEntity из proto в dict"""
        return {
            "text": entity.text,
            "start_char": entity.start_char,
            "end_char": entity.end_char,
            "entity_type": entity.entity_type,
            "confidence": entity.confidence,
            "sources": list(entity.sources),
            "is_scientific": entity.is_scientific,
            "scientific_domain": entity.scientific_domain,
            "metadata": dict(entity.metadata)
        }

    def _proto_processor_info_to_dict(self, info) -> Dict[str, Any]:
        """Конвертирует ProcessorInfo из proto в dict"""
        return {
            "name": info.name,
            "version": info.version,
            "description": info.description,
            "supported_categories": [nlp_pb2.AnnotationCategory.Name(c) for c in info.supported_categories],
            "supported_levels": [nlp_pb2.LinguisticLevel.Name(l) for l in info.supported_levels],
            "available": info.available
        }


# Глобальный экземпляр клиента
_nlp_grpc_client: Optional[NLPGRPCClient] = None


def get_nlp_grpc_client() -> NLPGRPCClient:
    """Получить глобальный экземпляр NLP gRPC клиента"""
    global _nlp_grpc_client
    if _nlp_grpc_client is None:
        _nlp_grpc_client = NLPGRPCClient()
        logger.info("[grpc_client] Создан глобальный экземпляр NLP клиента")
    return _nlp_grpc_client
