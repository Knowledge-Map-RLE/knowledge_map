"""Model Registry Service"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from .models import ModelInfo, ModelStatus, ModelType, ModelPerformance, ModelConfig

try:
    from ..core.config import settings
    from ..core.logger import get_logger
    from ..core.exceptions import ModelNotFoundError, ModelDisabledError
    from ..core.types import ModelInfo as CoreModelInfo, ModelStatus as CoreModelStatus
except ImportError:
    from core.config import settings
    from core.logger import get_logger
    from core.exceptions import ModelNotFoundError, ModelDisabledError
    from core.types import ModelInfo as CoreModelInfo, ModelStatus as CoreModelStatus

logger = get_logger(__name__)

class ModelRegistryService:
    """Service for managing conversion models"""
    
    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._model_info: Dict[str, ModelInfo] = {}
        self._default_model_id: Optional[str] = None
        self._model_performance: Dict[str, ModelPerformance] = {}
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize available models"""
        try:
            # Initialize only default model to reduce memory/time
            # Initialize Docling model (default)
            try:
                # Prefer Docling when available; fallback to PyMuPDF; finally a plain text stub
                import importlib
                docling_spec = importlib.util.find_spec("docling")

                class SimpleDoclingModel:
                    def __init__(self):
                        self.name = "Docling Model"
                        self.version = "1.0.0"
                    
                    async def convert_pdf(self, pdf_path, output_format="markdown"):
                        # Используем ТОЛЬКО Docling. Если не установлен — это ошибка конфигурации.
                        if docling_spec is not None:
                            # Configure HuggingFace cache and optional mirror before loading Docling
                            import os
                            from pathlib import Path as _Path
                            cache_dir = os.getenv("HF_HUB_CACHE") or str((_Path("./model_cache").resolve()))
                            os.makedirs(cache_dir, exist_ok=True)
                            os.environ["HF_HUB_CACHE"] = cache_dir
                            os.environ["HF_HOME"] = cache_dir
                            os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "1")
                            os.environ["TRANSFORMERS_OFFLINE"] = os.getenv("TRANSFORMERS_OFFLINE", "1")
                            os.environ["HF_DATASETS_OFFLINE"] = os.getenv("HF_DATASETS_OFFLINE", "1")
                            # Speed and stability toggles
                            # Disable hf_transfer fast-path to avoid extra dependency
                            os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
                            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
                            # Optional mirror endpoint (set DOC_LING_HF_ENDPOINT to override)
                            hf_endpoint = os.getenv("DOC_LING_HF_ENDPOINT")
                            if hf_endpoint:
                                os.environ["HF_ENDPOINT"] = hf_endpoint
                            logger.info(f"Configured HF cache: {cache_dir}; endpoint: {os.environ.get('HF_ENDPOINT', 'default')}; offline={os.environ.get('HF_HUB_OFFLINE')}")
                            # Common Docling API patterns (support multiple versions)
                            # a) Newer API
                            try:
                                from docling.document_converter import DocumentConverter  # type: ignore
                            except Exception:
                                DocumentConverter = None  # type: ignore
                            if DocumentConverter is not None:
                                converter = DocumentConverter()
                                result = converter.convert(pdf_path)
                                doc_obj = getattr(result, "document", None) or result
                                # Try several markdown exporters
                                for attr in [
                                    "export_to_markdown",
                                    "to_markdown",
                                    "export_markdown",
                                    "to_markdown_string",
                                    "as_markdown",
                                    "markdown",
                                ]:
                                    fn = getattr(doc_obj, attr, None)
                                    if callable(fn):
                                        md = fn()
                                        if md:
                                            return str(md)
                                    # Some libs expose markdown as property
                                    if fn is None:
                                        val = getattr(doc_obj, attr, None)
                                        if isinstance(val, str) and val.strip():
                                            return val
                                # Fallback: generic export method variants
                                for attr in [
                                    "export_to",
                                    "export",
                                    "save_as",
                                ]:
                                    fn = getattr(doc_obj, attr, None)
                                    if callable(fn):
                                        for fmt in ("markdown", "md"):
                                            try:
                                                md = fn(fmt)
                                                if md:
                                                    return str(md)
                                            except Exception:
                                                pass
                                # Attempt page-wise aggregation if structure available
                                parts = []
                                for page_attr in ("pages", "document_pages", "doc_pages"):
                                    pages = getattr(doc_obj, page_attr, None)
                                    if pages:
                                        for page in pages:
                                            for p_attr in (
                                                "to_markdown",
                                                "export_to_markdown",
                                                "to_markdown_string",
                                            ):
                                                pfn = getattr(page, p_attr, None)
                                                if callable(pfn):
                                                    try:
                                                        txt = pfn()
                                                        if isinstance(txt, str) and txt.strip():
                                                            parts.append(txt.strip())
                                                            break
                                                    except Exception:
                                                        pass
                                            # Try blocks/text fallback
                                            blocks = getattr(page, "blocks", None)
                                            if blocks:
                                                for b in blocks:
                                                    text = getattr(b, "text", None)
                                                    if isinstance(text, str) and text.strip():
                                                        parts.append(text.strip())
                                        if parts:
                                            return "\n\n---\n\n".join(parts)
                                # Если дошли сюда — Docling не вернул MD
                                raise RuntimeError("Docling did not produce Markdown output")
                            # b) Alternative API (pipeline based)
                            try:
                                from docling.pipeline import load_default_pipeline  # type: ignore
                            except Exception:
                                load_default_pipeline = None  # type: ignore
                            if load_default_pipeline is not None:
                                pipeline = load_default_pipeline()
                                result = pipeline.run(pdf_path)
                                doc_obj = getattr(result, "document", None) or result
                                for attr in [
                                    "export_to_markdown",
                                    "to_markdown",
                                    "export_markdown",
                                    "to_markdown_string",
                                    "as_markdown",
                                    "markdown",
                                ]:
                                    fn = getattr(doc_obj, attr, None)
                                    if callable(fn):
                                        md = fn()
                                        if md:
                                            return str(md)
                                    if fn is None:
                                        val = getattr(doc_obj, attr, None)
                                        if isinstance(val, str) and val.strip():
                                            return val
                                # Try export(fmt)
                                for attr in ["export_to", "export", "save_as"]:
                                    fn = getattr(doc_obj, attr, None)
                                    if callable(fn):
                                        for fmt in ("markdown", "md"):
                                            try:
                                                md = fn(fmt)
                                                if md:
                                                    return str(md)
                                            except Exception:
                                                pass
                                # Page-wise aggregation
                                parts = []
                                for page_attr in ("pages", "document_pages", "doc_pages"):
                                    pages = getattr(doc_obj, page_attr, None)
                                    if pages:
                                        for page in pages:
                                            for p_attr in (
                                                "to_markdown",
                                                "export_to_markdown",
                                                "to_markdown_string",
                                            ):
                                                pfn = getattr(page, p_attr, None)
                                                if callable(pfn):
                                                    try:
                                                        txt = pfn()
                                                        if isinstance(txt, str) and txt.strip():
                                                            parts.append(txt.strip())
                                                            break
                                                    except Exception:
                                                        pass
                                            blocks = getattr(page, "blocks", None)
                                            if blocks:
                                                for b in blocks:
                                                    text = getattr(b, "text", None)
                                                    if isinstance(text, str) and text.strip():
                                                        parts.append(text.strip())
                                        if parts:
                                            return "\n\n---\n\n".join(parts)
                                raise RuntimeError("Docling pipeline did not produce Markdown output")
                            # Если ни один из API не доступен — Docling установлен, но API не найден
                            raise RuntimeError("Docling module present but API is unavailable")
                        # Docling не установлен — явно сообщаем об ошибке
                        raise RuntimeError("Docling is not installed in the runtime environment")
                
                docling_model = SimpleDoclingModel()
                self._models["docling"] = docling_model
                
                model_info = ModelInfo(
                    model_id="docling",
                    name="Docling Model",
                    model_type=ModelType.DOCLING,
                    status=ModelStatus.AVAILABLE,
                    version="1.0.0",
                    description="Advanced document processing model",
                    is_default=True,
                    is_enabled=True,
                    config={"batch_size": 1, "max_pages": 100}
                )
                self._model_info["docling"] = model_info
                self._default_model_id = "docling"
                logger.info("Docling model initialized as default")
            except Exception as e:
                logger.warning(f"Docling model not available: {e}")
            
            if not self._models:
                logger.error("No models available!")
                raise RuntimeError("No conversion models available")
            
            logger.info(f"Initialized {len(self._models)} models: {list(self._models.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            raise
    
    def get_model(self, model_id: str):
        """Get model instance by ID"""
        if model_id not in self._models:
            raise ModelNotFoundError(f"Model {model_id} not found")
        
        model_info = self._model_info.get(model_id)
        if not model_info or not model_info.is_enabled:
            raise ModelDisabledError(f"Model {model_id} is disabled")
        
        # Update usage statistics
        model_info.last_used = datetime.now()
        model_info.usage_count += 1
        
        return self._models[model_id]
    
    def get_available_models(self) -> Dict[str, Any]:
        """Get list of available models"""
        models_data = []
        available_count = 0
        
        for model_id, model_info in self._model_info.items():
            if model_info.is_enabled and model_info.status == ModelStatus.AVAILABLE:
                available_count += 1
            
            model_data = {
                "model_id": model_id,
                "name": model_info.name,
                "type": model_info.model_type.value,
                "status": model_info.status.value,
                "version": model_info.version,
                "description": model_info.description,
                "is_default": model_info.is_default,
                "is_enabled": model_info.is_enabled,
                "config": model_info.config,
                "usage_count": model_info.usage_count,
                "last_used": model_info.last_used.isoformat() if model_info.last_used else None
            }
            models_data.append(model_data)
        
        return {
            "models": models_data,
            "default_model": self._default_model_id,
            "total_count": len(self._model_info),
            "available_count": available_count
        }
    
    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get model information"""
        return self._model_info.get(model_id)
    
    def is_model_available(self, model_id: str) -> bool:
        """Check if model is available"""
        model_info = self._model_info.get(model_id)
        return model_info is not None and model_info.is_enabled and model_info.status == ModelStatus.AVAILABLE
    
    def get_default_model_id(self) -> Optional[str]:
        """Get default model ID"""
        return self._default_model_id
    
    def set_default_model(self, model_id: str) -> bool:
        """Set default model"""
        if model_id not in self._model_info:
            raise ModelNotFoundError(f"Model {model_id} not found")
        
        model_info = self._model_info[model_id]
        if not model_info.is_enabled:
            raise ModelDisabledError(f"Model {model_id} is disabled")
        
        # Remove default flag from current default
        for info in self._model_info.values():
            info.is_default = False
        
        # Set new default
        model_info.is_default = True
        self._default_model_id = model_id
        
        logger.info(f"Set default model to: {model_id}")
        return True
    
    def enable_model(self, model_id: str) -> bool:
        """Enable model"""
        if model_id not in self._model_info:
            raise ModelNotFoundError(f"Model {model_id} not found")
        
        model_info = self._model_info[model_id]
        model_info.is_enabled = True
        model_info.status = ModelStatus.AVAILABLE
        
        logger.info(f"Enabled model: {model_id}")
        return True
    
    def disable_model(self, model_id: str) -> bool:
        """Disable model"""
        if model_id not in self._model_info:
            raise ModelNotFoundError(f"Model {model_id} not found")
        
        model_info = self._model_info[model_id]
        model_info.is_enabled = False
        model_info.status = ModelStatus.DISABLED
        
        # If this was the default model, set another as default
        if model_info.is_default:
            model_info.is_default = False
            # Find first available model
            for other_id, other_info in self._model_info.items():
                if other_id != model_id and other_info.is_enabled:
                    other_info.is_default = True
                    self._default_model_id = other_id
                    break
            else:
                self._default_model_id = None
        
        logger.info(f"Disabled model: {model_id}")
        return True
    
    def update_model_config(self, model_id: str, config: Dict[str, Any]) -> bool:
        """Update model configuration"""
        if model_id not in self._model_info:
            raise ModelNotFoundError(f"Model {model_id} not found")
        
        model_info = self._model_info[model_id]
        model_info.config = config
        
        logger.info(f"Updated config for model: {model_id}")
        return True
    
    def get_model_performance(self, model_id: str) -> Optional[ModelPerformance]:
        """Get model performance statistics"""
        return self._model_performance.get(model_id)
    
    def update_model_performance(self, model_id: str, processing_time: float, success: bool):
        """Update model performance statistics"""
        if model_id not in self._model_performance:
            self._model_performance[model_id] = ModelPerformance(
                model_id=model_id,
                avg_processing_time=0.0,
                success_rate=0.0,
                total_conversions=0
            )
        
        perf = self._model_performance[model_id]
        perf.total_conversions += 1
        
        # Update average processing time
        total_time = perf.avg_processing_time * (perf.total_conversions - 1) + processing_time
        perf.avg_processing_time = total_time / perf.total_conversions
        
        # Update success rate
        if success:
            success_count = perf.success_rate * (perf.total_conversions - 1) + 1
        else:
            success_count = perf.success_rate * (perf.total_conversions - 1)
        
        perf.success_rate = success_count / perf.total_conversions
        perf.last_performance_check = datetime.now()
    
    def get_all_model_performance(self) -> Dict[str, ModelPerformance]:
        """Get performance statistics for all models"""
        return self._model_performance.copy()
