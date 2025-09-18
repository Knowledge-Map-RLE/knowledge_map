from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

# Схемы для авторизации
class UserRegisterRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    nickname: str = Field(..., min_length=1, max_length=100)
    captcha: str


class UserLoginRequest(BaseModel):
    login: str
    password: str
    captcha: str
    device_info: Optional[str] = None
    ip_address: Optional[str] = None


class UserRecoveryRequest(BaseModel):
    recovery_key: str
    captcha: str


class UserPasswordResetRequest(BaseModel):
    user_id: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str
    
    @validator('new_password_confirm')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Пароли не совпадают')
        return v


class User2FASetupRequest(BaseModel):
    user_id: str


class User2FAVerifyRequest(BaseModel):
    user_id: str
    code: str = Field(..., min_length=6, max_length=6)


class AuthResponse(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    requires_2fa: Optional[bool] = None
    recovery_keys: Optional[List[str]] = None


class TokenVerifyResponse(BaseModel):
    valid: bool
    message: str
    user: Optional[Dict[str, Any]] = None