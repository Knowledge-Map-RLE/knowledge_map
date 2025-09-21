"""Model management service"""

from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    from ..core.config import settings
    from ..core.logger import get_logger
    from ..core.exceptions import ModelNotFoundError, ModelDisabledError
    from ..core.types import ModelInfo, ModelStatus
    from .models.base_model import BaseModel
    from .models.marker_model import MarkerModel
except ImportError:
    # Fallback for direct execution
    from core.config import settings
    from core.logger import get_logger
    from core.exceptions import ModelNotFoundError, ModelDisabledError
    from core.types import ModelInfo, ModelStatus
    from .models.base_model import BaseModel
    from .models.marker_model import MarkerModel

logger = get_logger(__name__)


class ModelService:
    """Service for managing conversion models"""
    
    def __init__(self):
        self._models: Dict[str, BaseModel] = {}
        self._default_model_id = None  # Will be set in _initialize_models
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """Initialize available models"""
        try:
            # Initialize Docling model (default)
            try:
                from .models.docling_model import DoclingModel
                docling_model = DoclingModel()
                self._models["docling"] = docling_model
                self._default_model_id = "docling"
                logger.info("Docling model initialized as default")
            except ImportError as e:
                logger.warning(f"Docling model not available: {e}")
            
            # Initialize Marker model (fallback)
            try:
                marker_model = MarkerModel()
                self._models["marker"] = marker_model
                if "docling" not in self._models:
                    self._default_model_id = "marker"
                logger.info("Marker model initialized")
            except Exception as e:
                logger.warning(f"Marker model not available: {e}")
            
            logger.info(f"Initialized {len(self._models)} models: {list(self._models.keys())}")
            logger.info(f"Default model: {self._default_model_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            raise
    
    def get_model(self, model_id: str) -> Optional[BaseModel]:
        """
        Get model by ID
        
        Args:
            model_id: Model identifier
            
        Returns:
            Model instance or None if not found
        """
        return self._models.get(model_id)
    
    def get_available_models(self) -> Dict[str, ModelInfo]:
        """
        Get list of available models
        
        Returns:
            Dictionary mapping model ID to model info
        """
        models = {}
        for model_id, model in self._models.items():
            models[model_id] = ModelInfo(
                id=model_id,
                name=model.name,
                description=model.description,
                status=ModelStatus.ENABLED if model.is_enabled else ModelStatus.DISABLED,
                is_default=(model_id == self._default_model_id),
                version=model.version,
                capabilities=model.capabilities
            )
        
        return models
    
    def get_default_model(self) -> str:
        """
        Get default model ID
        
        Returns:
            Default model ID
        """
        logger.info(f"get_default_model() returning: {self._default_model_id}")
        return self._default_model_id
    
    def set_default_model(self, model_id: str) -> bool:
        """
        Set default model
        
        Args:
            model_id: Model ID to set as default
            
        Returns:
            True if successful, False otherwise
        """
        if model_id not in self._models:
            logger.error(f"Model {model_id} not found")
            return False
        
        model = self._models[model_id]
        if not model.is_enabled:
            logger.error(f"Model {model_id} is disabled")
            return False
        
        self._default_model_id = model_id
        logger.info(f"Set default model to {model_id}")
        return True
    
    def enable_model(self, model_id: str) -> bool:
        """
        Enable model
        
        Args:
            model_id: Model ID to enable
            
        Returns:
            True if successful, False otherwise
        """
        if model_id not in self._models:
            logger.error(f"Model {model_id} not found")
            return False
        
        model = self._models[model_id]
        model.is_enabled = True
        logger.info(f"Enabled model {model_id}")
        return True
    
    def disable_model(self, model_id: str) -> bool:
        """
        Disable model
        
        Args:
            model_id: Model ID to disable
            
        Returns:
            True if successful, False otherwise
        """
        if model_id not in self._models:
            logger.error(f"Model {model_id} not found")
            return False
        
        # Don't allow disabling default model
        if model_id == self._default_model_id:
            logger.error(f"Cannot disable default model {model_id}")
            return False
        
        model = self._models[model_id]
        model.is_enabled = False
        logger.info(f"Disabled model {model_id}")
        return True
    
    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """
        Get detailed model information
        
        Args:
            model_id: Model ID
            
        Returns:
            Model info or None if not found
        """
        model = self._models.get(model_id)
        if not model:
            return None
        
        return ModelInfo(
            id=model_id,
            name=model.name,
            description=model.description,
            status=ModelStatus.ENABLED if model.is_enabled else ModelStatus.DISABLED,
            is_default=(model_id == self._default_model_id),
            version=model.version,
            capabilities=model.capabilities
        )
    
    def validate_model(self, model_id: str) -> bool:
        """
        Validate that model exists and is enabled
        
        Args:
            model_id: Model ID to validate
            
        Returns:
            True if model is valid and enabled
        """
        model = self._models.get(model_id)
        return model is not None and model.is_enabled
    
    def get_model_capabilities(self, model_id: str) -> List[str]:
        """
        Get model capabilities
        
        Args:
            model_id: Model ID
            
        Returns:
            List of capabilities
        """
        model = self._models.get(model_id)
        if not model:
            return []
        
        return model.capabilities
