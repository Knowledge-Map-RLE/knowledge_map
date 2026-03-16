#!/usr/bin/env python3
"""
gRPC сервер для NLP анализа текста
"""
import asyncio
import logging
import socket
import sys
import subprocess
import platform
import time
from pathlib import Path
from typing import Dict, Any, List

import re
import grpc
from concurrent import futures

# Добавляем путь к proto файлам и src директории
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(src_dir.parent))

# Импортируем сгенерированные proto файлы
try:
    import nlp_pb2
    import nlp_pb2_grpc
except ImportError:
    # Если proto файлы не сгенерированы, генерируем их
    proto_path = Path(__file__).parent.parent / "proto"
    src_path = Path(__file__).parent

    subprocess.run([
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_path}",
        f"--python_out={src_path}",
        f"--grpc_python_out={src_path}",
        str(proto_path / "nlp.proto")
    ], check=True)

    import nlp_pb2
    import nlp_pb2_grpc

# Настройка логирования
import os
os.makedirs('logs', exist_ok=True)

# Настройка UTF-8 для консольного вывода на Windows
stream_handler = logging.StreamHandler()
if hasattr(stream_handler.stream, 'reconfigure'):
    stream_handler.stream.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/nlp.log', encoding='utf-8'),
        stream_handler
    ]
)
logger = logging.getLogger(__name__)

# Импортируем наши модули
from config import get_config
from nlp_manager import NLPManager, get_nlp_manager
from multilevel_analyzer import MultiLevelAnalyzer
from base import AnnotationSource, AnnotationCategory
from unified_types import LinguisticLevel


def is_port_available(port: int) -> bool:
    """Проверяет, доступен ли порт для использования"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0
    except Exception:
        return False


def get_process_using_port(port: int) -> int:
    """Возвращает PID процесса, использующего указанный порт"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            return int(parts[-1])
        else:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
    except Exception as e:
        logger.error(f"Ошибка при поиске процесса на порту {port}: {e}")
    return None


def kill_process_on_port(port: int) -> bool:
    """Завершает процесс, использующий указанный порт"""
    try:
        pid = get_process_using_port(port)
        if pid:
            logger.info(f"Найден процесс {pid} на порту {port}, завершаем...")
            if platform.system() == "Windows":
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], timeout=5)
            else:
                subprocess.run(['kill', '-9', str(pid)], timeout=5)
            time.sleep(1)
            return True
    except Exception as e:
        logger.error(f"Ошибка при завершении процесса на порту {port}: {e}")
    return False


class NLPServicer(nlp_pb2_grpc.NLPServiceServicer):
    """Реализация gRPC сервиса для NLP анализа"""

    def __init__(self):
        """Инициализация сервиса"""
        self.config = get_config()
        
        # Setup models on first initialization
        try:
            from setup_models import setup_all_models
            logger.info("Setting up NLP models...")
            setup_all_models()
        except Exception as e:
            logger.warning(f"Error during model setup: {e}")
        
        self.nlp_manager = get_nlp_manager()  # создаёт и регистрирует глобальный NLPManager
        self.analyzer = MultiLevelAnalyzer()  # использует тот же экземпляр через get_nlp_manager()
        logger.info("NLP сервис инициализирован")

    def _convert_annotation_to_proto(self, annotation) -> nlp_pb2.AnnotationSuggestion:
        """Конвертирует AnnotationSuggestion в proto message"""
        # Конвертируем category
        category_map = {
            "part_of_speech": nlp_pb2.ANNOTATION_PART_OF_SPEECH,
            "syntax": nlp_pb2.ANNOTATION_SYNTAX,
            "named_entity": nlp_pb2.ANNOTATION_NAMED_ENTITY,
            "morphology": nlp_pb2.ANNOTATION_MORPHOLOGY,
            "sentence_member": nlp_pb2.ANNOTATION_SENTENCE_MEMBER,
            "scientific_entity": nlp_pb2.ANNOTATION_SCIENTIFIC_ENTITY,
            "general_entity": nlp_pb2.ANNOTATION_GENERAL_ENTITY,
        }

        # Конвертируем source
        source_map = {
            "user": nlp_pb2.USER,
            "spacy": nlp_pb2.SPACY,
            "custom": nlp_pb2.CUSTOM,
            "file": nlp_pb2.FILE,
            "nltk": nlp_pb2.NLTK,
            "stanza": nlp_pb2.STANZA,
            "udpipe": nlp_pb2.UDPIPE,
        }

        metadata = {k: str(v) for k, v in annotation.metadata.items()}

        return nlp_pb2.AnnotationSuggestion(
            text=annotation.text,
            annotation_type=annotation.annotation_type,
            category=category_map.get(annotation.category.value, nlp_pb2.ANNOTATION_CATEGORY_UNSPECIFIED),
            start_offset=annotation.start_offset,
            end_offset=annotation.end_offset,
            confidence=annotation.confidence,
            source=source_map.get(annotation.source.value, nlp_pb2.ANNOTATION_SOURCE_UNSPECIFIED),
            color=annotation.color,
            metadata=metadata
        )

    def _convert_relation_to_proto(self, relation) -> nlp_pb2.RelationSuggestion:
        """Конвертирует RelationSuggestion в proto message"""
        source_map = {
            "user": nlp_pb2.USER,
            "spacy": nlp_pb2.SPACY,
            "custom": nlp_pb2.CUSTOM,
            "file": nlp_pb2.FILE,
            "nltk": nlp_pb2.NLTK,
            "stanza": nlp_pb2.STANZA,
            "udpipe": nlp_pb2.UDPIPE,
        }

        metadata = {k: str(v) for k, v in relation.metadata.items()}

        return nlp_pb2.RelationSuggestion(
            source_text=relation.source_text,
            target_text=relation.target_text,
            source_start=relation.source_start,
            source_end=relation.source_end,
            target_start=relation.target_start,
            target_end=relation.target_end,
            relation_type=relation.relation_type,
            confidence=relation.confidence,
            source=source_map.get(relation.source.value, nlp_pb2.ANNOTATION_SOURCE_UNSPECIFIED),
            metadata=metadata
        )

    def _convert_processing_result_to_proto(self, result) -> nlp_pb2.ProcessingResult:
        """Конвертирует ProcessingResult в proto message"""
        metadata = {k: str(v) for k, v in result.metadata.items()}

        return nlp_pb2.ProcessingResult(
            annotations=[self._convert_annotation_to_proto(a) for a in result.annotations],
            relations=[self._convert_relation_to_proto(r) for r in result.relations],
            processor_name=result.processor_name,
            processor_version=result.processor_version,
            processing_time=result.processing_time,
            metadata=metadata
        )

    async def ProcessText(self, request, context):
        """Обработка текста с аннотациями и отношениями"""
        try:
            logger.info(f"ProcessText запрос: текст длиной {len(request.text)} символов")

            # Проверяем максимальную длину
            if len(request.text) > self.config.max_text_length:
                return nlp_pb2.ProcessTextResponse(
                    success=False,
                    message=f"Текст слишком длинный (максимум {self.config.max_text_length} символов)"
                )

            # Получаем список процессоров
            processor_names = list(request.processor_names) if request.processor_names else None

            # Обрабатываем текст
            start_time = time.time()
            results = self.nlp_manager.process_text(
                text=request.text,
                processor_names=processor_names
            )

            # Конвертируем результаты в proto
            proto_results = [self._convert_processing_result_to_proto(r) for r in results]

            # Если нужно объединить результаты
            merged_result = None
            if request.merge_results and len(results) > 1:
                merged = self.nlp_manager.merge_results(results)
                merged_result = self._convert_processing_result_to_proto(merged)

            processing_time = time.time() - start_time
            logger.info(f"ProcessText выполнен за {processing_time:.2f}с")

            return nlp_pb2.ProcessTextResponse(
                success=True,
                results=proto_results,
                merged_result=merged_result,
                message="Обработка выполнена успешно"
            )

        except Exception as e:
            logger.error(f"Ошибка в ProcessText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.ProcessTextResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )

    async def ProcessSelection(self, request, context):
        """Обработка выделенного фрагмента текста"""
        try:
            logger.info(f"ProcessSelection запрос: выделение '{request.selection}'")

            # Получаем список процессоров
            processor_names = list(request.processor_names) if request.processor_names else None

            # Обрабатываем выделение
            start_time = time.time()
            results = self.nlp_manager.process_selection(
                full_text=request.text,
                selection=request.selection,
                start_offset=request.start_offset,
                end_offset=request.end_offset,
                processor_names=processor_names
            )

            # Конвертируем результаты в proto
            proto_results = [self._convert_processing_result_to_proto(r) for r in results]

            # Если нужно объединить результаты
            merged_result = None
            if request.merge_results and len(results) > 1:
                merged = self.nlp_manager.merge_results(results)
                merged_result = self._convert_processing_result_to_proto(merged)

            processing_time = time.time() - start_time
            logger.info(f"ProcessSelection выполнен за {processing_time:.2f}с")

            return nlp_pb2.ProcessSelectionResponse(
                success=True,
                results=proto_results,
                merged_result=merged_result,
                message="Обработка выделения выполнена успешно"
            )

        except Exception as e:
            logger.error(f"Ошибка в ProcessSelection: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.ProcessSelectionResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )

    @staticmethod
    def _filter_text_for_analysis(text: str):
        """
        Убирает YAML front-matter и секцию References из текста перед анализом.
        Возвращает (filtered_text, char_offset) где char_offset — смещение начала
        отфильтрованного текста в оригинальном (для корректных offsets в аннотациях).
        """
        offset = 0
        # Убрать YAML front-matter (---...---)
        frontmatter_match = re.match(r'^---\r?\n.*?\r?\n---\r?\n', text, re.DOTALL)
        if frontmatter_match:
            offset = frontmatter_match.end()
            text = text[offset:]

        # Убрать секцию References (## References и всё после)
        ref_match = re.search(r'\n##\s+References\b', text, re.IGNORECASE)
        if ref_match:
            text = text[:ref_match.start()]

        return text, offset

    async def AnalyzeText(self, request, context):
        """Многоуровневый лингвистический анализ"""
        try:
            logger.info(f"AnalyzeText запрос: текст длиной {len(request.text)} символов")

            # Проверяем максимальную длину
            if len(request.text) > self.config.max_text_length:
                return nlp_pb2.AnalyzeTextResponse(
                    success=False,
                    message=f"Текст слишком длинный (максимум {self.config.max_text_length} символов)"
                )

            # Фильтруем front-matter и References, запоминаем смещение
            analyze_text, char_offset = self._filter_text_for_analysis(request.text)
            if char_offset > 0 or len(analyze_text) < len(request.text):
                logger.info(f"Текст после фильтрации: {len(request.text)} -> {len(analyze_text)} символов (offset={char_offset})")

            # Конвертируем уровни из proto
            levels_map = {
                nlp_pb2.LEVEL_TOKENIZATION: LinguisticLevel.TOKENIZATION,
                nlp_pb2.LEVEL_MORPHOLOGY: LinguisticLevel.MORPHOLOGY,
                nlp_pb2.LEVEL_SYNTAX: LinguisticLevel.SYNTAX,
                nlp_pb2.LEVEL_SEMANTIC_ROLES: LinguisticLevel.SEMANTIC_ROLES,
                nlp_pb2.LEVEL_LEXICAL_SEMANTICS: LinguisticLevel.LEXICAL_SEMANTICS,
                nlp_pb2.LEVEL_DISCOURSE: LinguisticLevel.DISCOURSE,
            }

            levels = [levels_map[l] for l in request.levels] if request.levels else None
            min_agreement = request.min_agreement if request.min_agreement > 0 else self.config.min_agreement

            # Выполняем анализ на отфильтрованном тексте
            start_time = time.time()
            document = self.analyzer.analyze(
                text=analyze_text,
                levels=levels,
                enable_voting=request.enable_voting if request.enable_voting else self.config.enable_voting,
                min_agreement=min_agreement
            )

            # Корректируем offsets: прибавляем char_offset ко всем позициям
            if char_offset > 0:
                for sent in document.sentences:
                    sent.start_char += char_offset
                    sent.end_char += char_offset
                    for token in sent.tokens:
                        token.start_char += char_offset
                        token.end_char += char_offset
                    for entity in sent.entities:
                        if entity.start_char is not None:
                            entity.start_char += char_offset
                        if entity.end_char is not None:
                            entity.end_char += char_offset
                for entity in document.entities:
                    if entity.start_char is not None:
                        entity.start_char += char_offset
                    if entity.end_char is not None:
                        entity.end_char += char_offset

            # Конвертируем UnifiedDocument в proto
            proto_doc = self._convert_document_to_proto(document)

            processing_time = time.time() - start_time
            logger.info(f"AnalyzeText выполнен за {processing_time:.2f}с")

            return nlp_pb2.AnalyzeTextResponse(
                success=True,
                document=proto_doc,
                message="Анализ выполнен успешно",
                processing_time=processing_time
            )

        except Exception as e:
            logger.error(f"Ошибка в AnalyzeText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.AnalyzeTextResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )

    def _convert_document_to_proto(self, document) -> nlp_pb2.UnifiedDocument:
        """Конвертирует UnifiedDocument в proto message"""
        metadata = {k: str(v) for k, v in document.metadata.items()}

        return nlp_pb2.UnifiedDocument(
            text=document.text,
            sentences=[self._convert_sentence_to_proto(s) for s in document.sentences],
            entities=[self._convert_entity_to_proto(e) for e in document.entities],
            metadata=metadata,
            processing_time=document.processing_time,
            processors_used=document.processors_used
        )

    def _convert_sentence_to_proto(self, sentence) -> nlp_pb2.UnifiedSentence:
        """Конвертирует UnifiedSentence в proto message"""
        metadata = {k: str(v) for k, v in getattr(sentence, 'metadata', {}).items()}

        return nlp_pb2.UnifiedSentence(
            idx=sentence.idx,
            text=sentence.text,
            start_char=sentence.start_char,
            end_char=sentence.end_char,
            tokens=[self._convert_token_to_proto(t) for t in sentence.tokens],
            dependencies=[self._convert_dependency_to_proto(d) for d in sentence.dependencies],
            phrases=[self._convert_phrase_to_proto(p) for p in sentence.phrases],
            entities=[self._convert_entity_to_proto(e) for e in sentence.entities],
            confidence=sentence.confidence,
            metadata=metadata
        )

    def _convert_token_to_proto(self, token) -> nlp_pb2.UnifiedToken:
        """Конвертирует UnifiedToken в proto message"""
        morph = {k: str(v) for k, v in token.morph.items()}

        return nlp_pb2.UnifiedToken(
            idx=token.idx,
            text=token.text,
            start_char=token.start_char,
            end_char=token.end_char,
            lemma=token.lemma,
            pos=token.pos,
            pos_fine=token.pos_fine or "",
            morph=morph,
            confidence=token.confidence,
            sources=token.sources,
            is_stop=token.is_stop,
            is_punct=token.is_punct,
            is_space=token.is_space,
            is_scientific_term=token.is_scientific_term,
            scientific_category=token.scientific_category or ""
        )

    def _convert_dependency_to_proto(self, dep) -> nlp_pb2.UnifiedDependency:
        """Конвертирует UnifiedDependency в proto message"""
        metadata = {k: str(v) for k, v in dep.metadata.items()}

        return nlp_pb2.UnifiedDependency(
            head_idx=dep.head_idx,
            dependent_idx=dep.dependent_idx,
            relation=dep.relation,
            confidence=dep.confidence,
            sources=dep.sources,
            metadata=metadata
        )

    def _convert_phrase_to_proto(self, phrase) -> nlp_pb2.UnifiedPhrase:
        """Конвертирует UnifiedPhrase в proto message"""
        return nlp_pb2.UnifiedPhrase(
            phrase_type=phrase.phrase_type,
            start_idx=phrase.start_idx,
            end_idx=phrase.end_idx,
            tokens=[self._convert_token_to_proto(t) for t in phrase.tokens],
            head_idx=phrase.head_idx,
            confidence=phrase.confidence,
            sources=phrase.sources
        )

    def _convert_entity_to_proto(self, entity) -> nlp_pb2.UnifiedEntity:
        """Конвертирует UnifiedEntity в proto message"""
        metadata = {k: str(v) for k, v in getattr(entity, 'metadata', {}).items()}

        # Derive char offsets: prefer stored start_char/end_char,
        # fall back to first/last token char offsets
        start_char = getattr(entity, 'start_char', None)
        end_char = getattr(entity, 'end_char', None)
        if start_char is None and entity.tokens:
            start_char = entity.tokens[0].start_char
        if end_char is None and entity.tokens:
            end_char = entity.tokens[-1].end_char
        start_char = start_char or 0
        end_char = end_char or 0

        return nlp_pb2.UnifiedEntity(
            text=entity.text() if callable(entity.text) else entity.text,
            start_char=start_char,
            end_char=end_char,
            entity_type=entity.entity_type,
            confidence=entity.confidence,
            sources=entity.sources,
            is_scientific=entity.is_scientific,
            scientific_domain=getattr(entity, 'domain', None) or "",
            metadata=metadata
        )

    async def GetSupportedTypes(self, request, context):
        """Получение списка поддерживаемых типов процессоров"""
        try:
            logger.info("GetSupportedTypes запрос")

            # Получаем информацию о процессорах
            processors = []
            for name, processor in self.nlp_manager.processors.items():
                supported_types = processor.get_supported_types()

                processor_info = nlp_pb2.ProcessorInfo(
                    name=name,
                    version="1.0.0",
                    description=f"{name} NLP processor",
                    supported_categories=[],
                    supported_levels=[],
                    available=True
                )
                processors.append(processor_info)

            # Получаем все поддерживаемые типы аннотаций
            annotation_types = set()
            relation_types = set()

            for processor in self.nlp_manager.processors.values():
                types = processor.get_supported_types()
                annotation_types.update(types.get("annotations", []))
                relation_types.update(types.get("relations", []))

            return nlp_pb2.GetSupportedTypesResponse(
                processors=processors,
                annotation_types=list(annotation_types),
                relation_types=list(relation_types)
            )

        except Exception as e:
            logger.error(f"Ошибка в GetSupportedTypes: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.GetSupportedTypesResponse()

    async def ValidateMarkdown(self, request, context):
        """Валидация канонического формата markdown"""
        try:
            from validation.markdown_validator import validate_markdown

            logger.info(f"ValidateMarkdown запрос: длина текста={len(request.markdown)}")

            # Валидировать markdown
            start_time = time.time()
            result = validate_markdown(request.markdown, self.config)
            processing_time = time.time() - start_time

            # Конвертировать ошибки в proto
            proto_errors = []
            for error in result.errors:
                proto_errors.append(self._validation_error_to_proto(error))

            proto_warnings = []
            for warning in result.warnings:
                proto_warnings.append(self._validation_error_to_proto(warning))

            # Применить strict mode - warnings становятся errors
            if request.strict_mode:
                proto_errors.extend(proto_warnings)
                proto_warnings = []
                is_valid = len(proto_errors) == 0
            else:
                is_valid = result.is_valid

            # Конвертировать метаданные
            metadata = {k: str(v) for k, v in result.metadata.items()}
            metadata['processing_time'] = str(processing_time)

            message = "Валидация пройдена" if is_valid else f"Найдено {result.total_errors} ошибок и {result.total_warnings} предупреждений"

            logger.info(f"ValidateMarkdown завершена: is_valid={is_valid}, errors={result.total_errors}, warnings={result.total_warnings}")

            return nlp_pb2.ValidateMarkdownResponse(
                success=True,
                is_valid=is_valid,
                errors=proto_errors,
                warnings=proto_warnings,
                message=message,
                total_errors=result.total_errors,
                total_warnings=result.total_warnings,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Ошибка в ValidateMarkdown: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.ValidateMarkdownResponse(
                success=False,
                is_valid=False,
                message=f"Ошибка валидации: {str(e)}"
            )

    def _validation_error_to_proto(self, error) -> nlp_pb2.ValidationErrorMessage:
        """Конвертировать ValidationError в proto message"""
        severity_map = {
            "error": nlp_pb2.VALIDATION_ERROR_SEVERITY_ERROR,
            "warning": nlp_pb2.VALIDATION_ERROR_SEVERITY_WARNING,
            "info": nlp_pb2.VALIDATION_ERROR_SEVERITY_INFO,
        }

        metadata = {k: str(v) for k, v in error.metadata.items()}

        return nlp_pb2.ValidationErrorMessage(
            error_type=error.error_type.value,
            message=error.message,
            severity=severity_map.get(error.severity.value, nlp_pb2.VALIDATION_ERROR_SEVERITY_UNSPECIFIED),
            line=error.line or 0,
            column=error.column or 0,
            start_offset=error.start_offset or 0,
            end_offset=error.end_offset or 0,
            context=error.context or "",
            suggestion=error.suggestion or "",
            metadata=metadata
        )


async def serve():
    """Запуск gRPC сервера"""
    config = get_config()

    # Проверяем, свободен ли порт
    if not is_port_available(config.port):
        logger.warning(f"Порт {config.port} занят, пытаемся освободить...")
        kill_process_on_port(config.port)

        # Ждём немного и проверяем снова
        await asyncio.sleep(2)
        if not is_port_available(config.port):
            logger.error(f"Не удалось освободить порт {config.port}")
            return

    # Создаём сервер
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=config.max_workers))
    nlp_pb2_grpc.add_NLPServiceServicer_to_server(NLPServicer(), server)

    server.add_insecure_port(f'{config.host}:{config.port}')

    logger.info(f"Запуск NLP gRPC сервера на {config.host}:{config.port}")
    await server.start()
    logger.info(f"NLP gRPC сервер запущен на {config.host}:{config.port}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Остановка сервера...")
        await server.stop(5)


if __name__ == '__main__':
    asyncio.run(serve())
