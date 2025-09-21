"""API dependencies for dependency injection"""

from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..core.config import settings
from ..core.logger import get_logger
from ..services.conversion_service import ConversionService

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


def get_conversion_service() -> ConversionService:
    """Get conversion service instance"""
    return ConversionService()


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Verify API key (placeholder for future implementation)
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    # For now, we'll allow all requests
    # In production, implement proper API key validation
    if credentials is None:
        # Allow requests without authentication for now
        return "anonymous"
    
    # TODO: Implement proper API key validation
    # if credentials.credentials != settings.api_key:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Invalid API key"
    #     )
    
    return credentials.credentials


def get_current_user(
    api_key: str = Depends(verify_api_key)
) -> dict:
    """
    Get current user information
    
    Args:
        api_key: Validated API key
        
    Returns:
        User information dictionary
    """
    # For now, return basic user info
    # In production, implement proper user management
    return {
        "user_id": "anonymous",
        "api_key": api_key,
        "permissions": ["convert_pdf"]
    }
