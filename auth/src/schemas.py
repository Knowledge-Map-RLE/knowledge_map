from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re


class UserBase(BaseModel):
    login: str = Field(..., min_length=3, max_length=50)
    nickname: str = Field(..., min_length=1, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @validator('login')
    def validate_login(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Логин может содержать только буквы, цифры и подчеркивания')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Пароль должен содержать не менее 8 символов')
        return v


class UserLogin(BaseModel):
    login: str
    password: str
    captcha: str


class UserResponse(UserBase):
    uid: str
    is_active: bool
    is_2fa_enabled: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class RecoveryRequest(BaseModel):
    recovery_key: str
    captcha: str


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str
    
    @validator('new_password_confirm')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Пароли не совпадают')
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class CaptchaResponse(BaseModel):
    captcha_id: str
    captcha_image: str  # base64 encoded image


class RecoveryKeysResponse(BaseModel):
    recovery_keys: List[str]
    message: str = "Сохраните эти ключи в надежном месте. Они потребуются для восстановления доступа."


class TwoFactorSetup(BaseModel):
    secret: str
    qr_code: str  # base64 encoded QR code
    backup_codes: List[str]


class TwoFactorVerify(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class SessionInfo(BaseModel):
    session_id: str
    device_info: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime
    expires_at: datetime


class LogoutRequest(BaseModel):
    session_id: Optional[str] = None  # Если не указан, выходит из всех сессий 