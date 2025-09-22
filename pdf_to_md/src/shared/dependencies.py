"""FastAPI dependencies for shared use"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    from ...core.config import settings
    from ...core.logger import get_logger
except ImportError:
    from core.config import settings
    from core.logger import get_logger

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

class CurrentUser:
    """Simple user model for authentication"""
    def __init__(self, user_id: str, username: str = "default_user"):
        self.id = user_id
        self.username = username

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> CurrentUser:
    """
    Get current user from authentication
    
    In a real application, this would validate JWT tokens or session data.
    For now, we'll use a simple implementation.
    """
    try:
        # In development mode, allow requests without authentication
        if settings.debug:
            return CurrentUser(user_id="dev_user", username="development_user")
        
        # In production, validate the token
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # TODO: Implement proper JWT token validation
        # For now, accept any token in production
        token = credentials.credentials
        
        # Simple token validation (replace with proper JWT validation)
        if not token or len(token) < 10:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract user info from token (placeholder)
        user_id = f"user_{hash(token) % 10000}"
        username = f"user_{user_id}"
        
        return CurrentUser(user_id=user_id, username=username)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[CurrentUser]:
    """
    Get current user if authenticated, otherwise return None
    """
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
