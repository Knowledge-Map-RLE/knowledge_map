import secrets
import string
import pyotp
import qrcode
import bcrypt
import jwt
import base64
import io
from datetime import datetime, timedelta
from typing import Optional, List
from .config import settings


def hash_password(password: str) -> str:
    """Хеширует пароль с использованием bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Проверяет пароль против хеша"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_recovery_keys(count: int = 10, length: int = 16) -> List[str]:
    """Генерирует ключи восстановления"""
    alphabet = string.ascii_uppercase + string.digits
    return [''.join(secrets.choice(alphabet) for _ in range(length)) for _ in range(count)]


def generate_2fa_secret() -> str:
    """Генерирует секрет для 2FA"""
    return pyotp.random_base32()


def generate_2fa_qr_code(secret: str, username: str) -> str:
    """Генерирует QR код для 2FA"""
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name="Knowledge Map"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Конвертируем в base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def verify_2fa_code(secret: str, code: str) -> bool:
    """Проверяет код 2FA"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создает JWT токен"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Проверяет JWT токен"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def generate_session_id() -> str:
    """Генерирует уникальный ID сессии"""
    return secrets.token_urlsafe(32) 