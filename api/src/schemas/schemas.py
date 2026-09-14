from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator, field_validator

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
    remember_me: Optional[bool] = None


class UserRecoveryRequest(BaseModel):
    recovery_key: str
    captcha: str


class UserLogoutRequest(BaseModel):
    token: str
    logout_all: bool = False


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


class TokenVerifyRequest(BaseModel):
    token: str


class TokenVerifyResponse(BaseModel):
    valid: bool
    message: str
    user: Optional[Dict[str, Any]] = None


# Схемы для серверной аналитики посещаемости
class PageViewRequest(BaseModel):
    route: str = Field(..., min_length=1, max_length=500)
    referrer: Optional[str] = Field(None, max_length=500)

    @field_validator("route", mode="before")
    @classmethod
    def route_not_blank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("route не может быть пустым")
        return v


class PageViewResponse(BaseModel):
    success: bool


class RouteStatsItem(BaseModel):
    route: str
    views: int
    sessions: int


class ReferrerStatsItem(BaseModel):
    referrer_domain: str
    views: int
    sessions: int


class DailyStatsItem(BaseModel):
    date: str
    views: int
    sessions: int
    unique_visitors: int


class AnalyticsSummaryResponse(BaseModel):
    total_views: int
    total_sessions: int
    total_unique_visitors: int
    start_date: str
    end_date: str
    routes: List[RouteStatsItem]
    referrers: List[ReferrerStatsItem]
    daily: List[DailyStatsItem]