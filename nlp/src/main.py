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

    # Паттерны для HTML-блоков, которые нужно фильтровать
    _TABLE_RE = re.compile(r'<table\b[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)
    _CAPTION_RE = re.compile(r'<caption\b[^>]*>(.*?)</caption>', re.DOTALL | re.IGNORECASE)
    _FIGURE_RE = re.compile(r'<figure\b[^>]*>.*?</figure>', re.DOTALL | re.IGNORECASE)
    _FIGCAPTION_RE = re.compile(r'<figcaption\b[^>]*>(.*?)</figcaption>', re.DOTALL | re.IGNORECASE)
    _IMG_RE = re.compile(r'<img\b[^>]*/>', re.IGNORECASE)

    @staticmethod
    def _remap_offset(pos: int, offset_map: list) -> int:
        """Преобразует позицию в отфильтрованном тексте в позицию в оригинале."""
        if pos < len(offset_map):
            return offset_map[pos]
        if offset_map:
            return offset_map[-1] + (pos - len(offset_map) + 1)
        return pos

    @classmethod
    def _filter_text_for_analysis(cls, text: str) -> tuple:
        """
        Фильтрует Markdown-текст перед анализом spaCy:
        - Удаляет YAML front-matter (---...---)
        - Удаляет HTML-таблицы (сохраняет текст <caption>)
        - Удаляет HTML-изображения <figure>/<img> (сохраняет текст <figcaption>)
        - Удаляет секцию References и всё после неё

        Возвращает (filtered_text, offset_map) где offset_map[i] — позиция
        символа i отфильтрованного текста в оригинальном тексте.
        """
        orig = text
        result_chars: list = []
        offset_map: list = []

        def append_span(start: int, end: int) -> None:
            for i in range(start, end):
                result_chars.append(orig[i])
                offset_map.append(i)

        def append_replacement(replacement: str, orig_pos: int) -> None:
            for ch in replacement:
                result_chars.append(ch)
                offset_map.append(orig_pos)

        # Собираем диапазоны для удаления/замены.
        # Каждый элемент: (start, end, keep_spans)
        # keep_spans — список (orig_start, orig_end) реальных подстрок оригинала,
        # которые нужно оставить вместо вырезанного блока (с правильным offset_map).
        removals: list = []

        # 1. YAML front-matter в начале файла
        fm_match = re.match(r'^---\r?\n.*?\r?\n---\r?\n', orig, re.DOTALL)
        if fm_match:
            removals.append((fm_match.start(), fm_match.end(), []))

        # 2. HTML-таблицы → оставляем текст <caption> с реальными позициями
        for m in cls._TABLE_RE.finditer(orig):
            keep = []
            cap = cls._CAPTION_RE.search(m.group(0))
            if cap:
                # cap.start(1)/end(1) — позиция группы захвата внутри m.group(0)
                abs_start = m.start() + cap.start(1)
                abs_end = m.start() + cap.end(1)
                # strip() — убираем пробелы по краям, находя реальные границы
                inner = orig[abs_start:abs_end]
                stripped_inner = inner.strip()
                if stripped_inner:
                    lstrip = len(inner) - len(inner.lstrip())
                    keep.append((abs_start + lstrip, abs_start + lstrip + len(stripped_inner)))
            removals.append((m.start(), m.end(), keep))

        # 3. HTML-фигуры → оставляем текст <figcaption> с реальными позициями
        for m in cls._FIGURE_RE.finditer(orig):
            keep = []
            fcap = cls._FIGCAPTION_RE.search(m.group(0))
            if fcap:
                abs_start = m.start() + fcap.start(1)
                abs_end = m.start() + fcap.end(1)
                inner = orig[abs_start:abs_end]
                stripped_inner = inner.strip()
                if stripped_inner:
                    lstrip = len(inner) - len(inner.lstrip())
                    keep.append((abs_start + lstrip, abs_start + lstrip + len(stripped_inner)))
            removals.append((m.start(), m.end(), keep))

        # 4. Одиночные <img /> без <figure>
        for m in cls._IMG_RE.finditer(orig):
            removals.append((m.start(), m.end(), []))

        # 5. Секция References — удаляем всё от начала заголовка до конца
        ref_match = re.search(r'\n#{1,6}\s+References\b', orig, re.IGNORECASE)
        if ref_match:
            removals.append((ref_match.start(), len(orig), []))

        # Сортируем и разрешаем перекрытия (побеждает первый/больший диапазон)
        removals.sort(key=lambda x: x[0])
        merged: list = []
        for start, end, keep_spans in removals:
            if merged and start < merged[-1][1]:
                prev_start, prev_end, prev_keep = merged[-1]
                merged[-1] = (prev_start, max(prev_end, end), prev_keep)
            else:
                merged.append((start, end, keep_spans))

        # Строим отфильтрованный текст с картой смещений
        cursor = 0
        for start, end, keep_spans in merged:
            if cursor < start:
                append_span(cursor, start)
            for ks, ke in keep_spans:
                append_span(ks, ke)
                # разделитель после caption/figcaption
                append_replacement('\n', ke - 1)
            cursor = end
        if cursor < len(orig):
            append_span(cursor, len(orig))

        filtered_text = ''.join(result_chars)
        return filtered_text, offset_map

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

            # Фильтруем front-matter, HTML-блоки и References, строим карту смещений
            analyze_text, offset_map = self._filter_text_for_analysis(request.text)
            if len(analyze_text) < len(request.text):
                logger.info(f"Текст после фильтрации: {len(request.text)} -> {len(analyze_text)} символов")

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

            # Корректируем offsets через карту смещений
            if offset_map:
                for sent in document.sentences:
                    sent.start_char = self._remap_offset(sent.start_char, offset_map)
                    sent.end_char = self._remap_offset(sent.end_char, offset_map)
                    for token in sent.tokens:
                        token.start_char = self._remap_offset(token.start_char, offset_map)
                        token.end_char = self._remap_offset(token.end_char, offset_map)
                    for entity in sent.entities:
                        if entity.start_char is not None:
                            entity.start_char = self._remap_offset(entity.start_char, offset_map)
                        if entity.end_char is not None:
                            entity.end_char = self._remap_offset(entity.end_char, offset_map)
                for entity in document.entities:
                    if entity.start_char is not None:
                        entity.start_char = self._remap_offset(entity.start_char, offset_map)
                    if entity.end_char is not None:
                        entity.end_char = self._remap_offset(entity.end_char, offset_map)

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

    async def ExtractActions(self, request, context):
        """Извлечение действий и причинно-следственных связей из текста"""
        try:
            logger.info(
                "[ExtractActions] doc_id=%s text_len=%d",
                request.doc_id or "<none>", len(request.text)
            )

            # Получаем spaCy процессор
            spacy_processor = self.nlp_manager.processors.get('spacy')
            if spacy_processor is None or spacy_processor.nlp is None:
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("spaCy processor not available")
                return nlp_pb2.ExtractActionsResponse(
                    success=False,
                    message="spaCy processor not available"
                )

            from action_extractor import ActionExtractor
            extractor = ActionExtractor()
            actions, deps = extractor.extract(request.text, spacy_processor.nlp)

            proto_actions = []
            for a in actions:
                # Сериализуем DependencySpan
                proto_spans = []
                for sp in a.spans:
                    proto_spans.append(nlp_pb2.DependencySpanProto(
                        span_type=sp.get("span_type", ""),
                        token_ids=sp.get("token_ids", []),
                        head_token_id=sp.get("head_token_id", 0),
                        text=sp.get("text", ""),
                        lemma_form=sp.get("lemma_form", ""),
                    ))

                # Сериализуем UnifiedToken
                proto_tokens = []
                for tk in a.tokens:
                    proto_tokens.append(nlp_pb2.UnifiedToken(
                        idx=tk.get("idx", 0),
                        text=tk.get("text", ""),
                        start_char=tk.get("start_char", 0),
                        end_char=tk.get("end_char", 0),
                        lemma=tk.get("lemma", ""),
                        pos=tk.get("pos", ""),
                        pos_fine=tk.get("pos_fine", ""),
                        is_stop=tk.get("is_stop", False),
                        is_punct=tk.get("is_punct", False),
                    ))

                proto_actions.append(nlp_pb2.ActionProto(
                    action_id=a.action_id,
                    verb_lemma=a.verb_lemma,
                    verb_text=a.verb_text,
                    object_text=a.object_text,
                    full_phrase=a.full_phrase,
                    sentence_text=a.sentence_text,
                    sentence_idx=a.sentence_idx,
                    char_start=a.char_start,
                    char_end=a.char_end,
                    modifiers=a.modifiers,
                    action_score=a.action_score,
                    subject_text=a.subject_text,
                    spans=proto_spans,
                    tokens=proto_tokens,
                    verb_span_idx=a.verb_span_idx,
                    subject_span_idx=a.subject_span_idx,
                    object_span_idx=a.object_span_idx,
                ))

            proto_deps = [
                nlp_pb2.DependencyProto(
                    source_id=d.source_id,
                    target_id=d.target_id,
                    marker_text=d.marker_text,
                    link_score=d.link_score,
                    relation_subtype=d.relation_subtype,
                    evidence_type=d.evidence_type,
                )
                for d in deps
            ]

            logger.info(
                "[ExtractActions] done: %d actions, %d deps",
                len(proto_actions), len(proto_deps)
            )

            return nlp_pb2.ExtractActionsResponse(
                success=True,
                actions=proto_actions,
                dependencies=proto_deps,
                message=f"Extracted {len(proto_actions)} actions, {len(proto_deps)} dependencies",
            )

        except Exception as e:
            logger.error("[ExtractActions] error: %s", e, exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return nlp_pb2.ExtractActionsResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
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
    # 256MB лимит — ответ с NLP-документом для текста ~65K символов может быть 50-100MB
    _GRPC_OPTIONS = [
        ("grpc.max_send_message_length", 256 * 1024 * 1024),
        ("grpc.max_receive_message_length", 256 * 1024 * 1024),
    ]
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=config.max_workers), options=_GRPC_OPTIONS)
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
