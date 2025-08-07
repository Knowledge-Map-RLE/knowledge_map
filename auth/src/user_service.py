from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from auth.src.models import User, Session
from auth.src.schemas import UserCreate, UserLogin, RecoveryRequest, PasswordReset
from auth.src.utils import (
    hash_password, verify_password, generate_recovery_keys,
    generate_2fa_secret, generate_2fa_qr_code, verify_2fa_code,
    create_access_token, verify_token, generate_session_id
)
from auth.src.config import settings
import redis
import json


class UserService:
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL)
    
    def create_user(self, user_data: UserCreate) -> Tuple[User, List[str]]:
        """Создает нового пользователя"""
        # Проверяем, не существует ли уже пользователь с таким логином
        existing_user = User.nodes.filter(login=user_data.login).first()
        if existing_user:
            raise ValueError("Пользователь с таким логином уже существует")
        
        # Генерируем ключи восстановления
        recovery_keys = generate_recovery_keys(
            settings.RECOVERY_KEYS_COUNT,
            settings.RECOVERY_KEY_LENGTH
        )
        
        # Создаем пользователя
        user = User(
            login=user_data.login,
            password_hash=hash_password(user_data.password),
            nickname=user_data.nickname,
            recovery_keys=recovery_keys
        ).save()
        
        return user, recovery_keys
    
    def authenticate_user(self, login: str, password: str) -> Optional[User]:
        """Аутентифицирует пользователя"""
        user = User.nodes.filter(login=login).first()
        if not user:
            return None
        
        if not user.is_active:
            raise ValueError("Аккаунт заблокирован")
        
        if user.locked_until and user.locked_until > datetime.utcnow():
            raise ValueError(f"Аккаунт заблокирован до {user.locked_until}")
        
        if not verify_password(password, user.password_hash):
            # Увеличиваем счетчик неудачных попыток
            user.login_attempts += 1
            
            # Блокируем аккаунт при превышении лимита
            if user.login_attempts >= settings.LOGIN_ATTEMPTS_LIMIT:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                user.save()
                raise ValueError("Аккаунт заблокирован на 30 минут из-за превышения лимита попыток входа")
            
            user.save()
            raise ValueError("Неверный пароль")
        
        # Сбрасываем счетчик неудачных попыток при успешном входе
        user.login_attempts = 0
        user.last_login = datetime.utcnow()
        user.save()
        
        return user
    
    def verify_recovery_key(self, recovery_key: str) -> Optional[User]:
        """Проверяет ключ восстановления"""
        # Ищем пользователя с таким ключом восстановления
        users = User.nodes.all()
        for user in users:
            if recovery_key in user.recovery_keys:
                return user
        return None
    
    def reset_password(self, user: User, new_password: str):
        """Сбрасывает пароль пользователя"""
        user.password_hash = hash_password(new_password)
        user.login_attempts = 0
        user.locked_until = None
        user.save()
    
    def setup_2fa(self, user: User) -> Tuple[str, str, List[str]]:
        """Настраивает 2FA для пользователя"""
        secret = generate_2fa_secret()
        qr_code = generate_2fa_qr_code(secret, user.login)
        backup_codes = generate_recovery_keys(5, 8)  # 5 резервных кодов по 8 символов
        
        user.two_fa_secret = secret
        user.save()
        
        return secret, qr_code, backup_codes
    
    def verify_2fa(self, user: User, code: str) -> bool:
        """Проверяет код 2FA"""
        if not user.two_fa_secret:
            return False
        return verify_2fa_code(user.two_fa_secret, code)
    
    def create_session(self, user: User, device_info: dict = None, ip_address: str = None) -> Session:
        """Создает сессию пользователя"""
        session_id = generate_session_id()
        token = create_access_token({"sub": user.uid, "session_id": session_id})
        
        session = Session(
            user_id=user.uid,
            token=token,
            device_info=device_info or {},
            ip_address=ip_address,
            expires_at=datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        ).save()
        
        return session
    
    def get_user_by_token(self, token: str) -> Optional[User]:
        """Получает пользователя по токену"""
        payload = verify_token(token)
        if not payload:
            return None
        
        session = Session.nodes.filter(token=token, is_active=True).first()
        if not session or session.expires_at < datetime.utcnow():
            return None
        
        return User.nodes.get(uid=payload.get("sub"))
    
    def logout_session(self, token: str):
        """Выходит из сессии"""
        session = Session.nodes.filter(token=token).first()
        if session:
            session.is_active = False
            session.save()
    
    def logout_all_sessions(self, user_id: str):
        """Выходит из всех сессий пользователя"""
        sessions = Session.nodes.filter(user_id=user_id, is_active=True)
        for session in sessions:
            session.is_active = False
            session.save()
    
    def get_user_sessions(self, user_id: str) -> List[Session]:
        """Получает все активные сессии пользователя"""
        return Session.nodes.filter(user_id=user_id, is_active=True)
    
    def cleanup_expired_sessions(self):
        """Очищает истекшие сессии"""
        expired_sessions = Session.nodes.filter(expires_at__lt=datetime.utcnow())
        for session in expired_sessions:
            session.delete()
    
    def get_rate_limit_key(self, login: str) -> str:
        """Получает ключ для rate limiting"""
        return f"login_attempts:{login}"
    
    def check_rate_limit(self, login: str) -> bool:
        """Проверяет rate limiting для входа"""
        key = self.get_rate_limit_key(login)
        attempts = self.redis_client.get(key)
        if attempts and int(attempts) >= settings.LOGIN_ATTEMPTS_LIMIT:
            return False
        return True
    
    def increment_rate_limit(self, login: str):
        """Увеличивает счетчик попыток входа"""
        key = self.get_rate_limit_key(login)
        pipe = self.redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, settings.LOGIN_ATTEMPTS_WINDOW)
        pipe.execute() 