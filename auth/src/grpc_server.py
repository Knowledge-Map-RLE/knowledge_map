import grpc
from concurrent import futures
import auth_pb2
import auth_pb2_grpc
from auth.src.user_service import UserService
from auth.src.models import User
from auth.src.schemas import UserCreate, UserLogin, RecoveryRequest, PasswordReset, TwoFactorVerify
from auth.src.config import settings
import json


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self):
        self.user_service = UserService()
    
    def Register(self, request, context):
        try:
            user_data = UserCreate(
                login=request.login,
                password=request.password,
                nickname=request.nickname
            )
            
            user, recovery_keys = self.user_service.create_user(user_data)
            
            return auth_pb2.RegisterResponse(
                success=True,
                message="Пользователь успешно зарегистрирован",
                user=auth_pb2.User(
                    uid=user.uid,
                    login=user.login,
                    nickname=user.nickname,
                    is_active=user.is_active,
                    is_2fa_enabled=user.is_2fa_enabled,
                    created_at=user.created_at.isoformat(),
                    last_login=user.last_login.isoformat() if user.last_login else ""
                ),
                recovery_keys=recovery_keys
            )
        except ValueError as e:
            return auth_pb2.RegisterResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return auth_pb2.RegisterResponse(
                success=False,
                message="Внутренняя ошибка сервера"
            )
    
    def Login(self, request, context):
        try:
            # Проверяем rate limiting
            if not self.user_service.check_rate_limit(request.login):
                return auth_pb2.LoginResponse(
                    success=False,
                    message="Слишком много попыток входа. Попробуйте позже."
                )
            
            user = self.user_service.authenticate_user(request.login, request.password)
            
            if not user:
                self.user_service.increment_rate_limit(request.login)
                return auth_pb2.LoginResponse(
                    success=False,
                    message="Неверный логин или пароль"
                )
            
            # Если включена 2FA, возвращаем флаг
            if user.is_2fa_enabled:
                return auth_pb2.LoginResponse(
                    success=True,
                    message="Требуется двухфакторная аутентификация",
                    user=auth_pb2.User(
                        uid=user.uid,
                        login=user.login,
                        nickname=user.nickname,
                        is_active=user.is_active,
                        is_2fa_enabled=user.is_2fa_enabled,
                        created_at=user.created_at.isoformat(),
                        last_login=user.last_login.isoformat() if user.last_login else ""
                    ),
                    requires_2fa=True
                )
            
            # Создаем сессию
            device_info = json.loads(request.device_info) if request.device_info else {}
            session = self.user_service.create_session(
                user, 
                device_info, 
                request.ip_address
            )
            
            return auth_pb2.LoginResponse(
                success=True,
                message="Успешный вход",
                token=session.token,
                user=auth_pb2.User(
                    uid=user.uid,
                    login=user.login,
                    nickname=user.nickname,
                    is_active=user.is_active,
                    is_2fa_enabled=user.is_2fa_enabled,
                    created_at=user.created_at.isoformat(),
                    last_login=user.last_login.isoformat() if user.last_login else ""
                ),
                requires_2fa=False
            )
        except ValueError as e:
            return auth_pb2.LoginResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return auth_pb2.LoginResponse(
                success=False,
                message="Внутренняя ошибка сервера"
            )
    
    def Logout(self, request, context):
        try:
            if request.logout_all:
                user = self.user_service.get_user_by_token(request.token)
                if user:
                    self.user_service.logout_all_sessions(user.uid)
            else:
                self.user_service.logout_session(request.token)
            
            return auth_pb2.LogoutResponse(
                success=True,
                message="Успешный выход"
            )
        except Exception as e:
            return auth_pb2.LogoutResponse(
                success=False,
                message="Ошибка при выходе"
            )
    
    def VerifyToken(self, request, context):
        try:
            user = self.user_service.get_user_by_token(request.token)
            
            if not user:
                return auth_pb2.VerifyTokenResponse(
                    valid=False,
                    message="Недействительный токен"
                )
            
            return auth_pb2.VerifyTokenResponse(
                valid=True,
                user=auth_pb2.User(
                    uid=user.uid,
                    login=user.login,
                    nickname=user.nickname,
                    is_active=user.is_active,
                    is_2fa_enabled=user.is_2fa_enabled,
                    created_at=user.created_at.isoformat(),
                    last_login=user.last_login.isoformat() if user.last_login else ""
                ),
                message="Токен действителен"
            )
        except Exception as e:
            return auth_pb2.VerifyTokenResponse(
                valid=False,
                message="Ошибка проверки токена"
            )
    
    def GetUser(self, request, context):
        try:
            user = User.nodes.get(uid=request.user_id)
            
            return auth_pb2.GetUserResponse(
                success=True,
                user=auth_pb2.User(
                    uid=user.uid,
                    login=user.login,
                    nickname=user.nickname,
                    is_active=user.is_active,
                    is_2fa_enabled=user.is_2fa_enabled,
                    created_at=user.created_at.isoformat(),
                    last_login=user.last_login.isoformat() if user.last_login else ""
                )
            )
        except Exception as e:
            return auth_pb2.GetUserResponse(
                success=False,
                message="Пользователь не найден"
            )
    
    def RecoveryRequest(self, request, context):
        try:
            user = self.user_service.verify_recovery_key(request.recovery_key)
            
            if not user:
                return auth_pb2.RecoveryResponse(
                    success=False,
                    message="Неверный ключ восстановления"
                )
            
            return auth_pb2.RecoveryResponse(
                success=True,
                message="Ключ восстановления подтвержден",
                user_id=user.uid
            )
        except Exception as e:
            return auth_pb2.RecoveryResponse(
                success=False,
                message="Ошибка проверки ключа восстановления"
            )
    
    def ResetPassword(self, request, context):
        try:
            user = User.nodes.get(uid=request.user_id)
            self.user_service.reset_password(user, request.new_password)
            
            return auth_pb2.ResetPasswordResponse(
                success=True,
                message="Пароль успешно изменен"
            )
        except Exception as e:
            return auth_pb2.ResetPasswordResponse(
                success=False,
                message="Ошибка сброса пароля"
            )
    
    def Setup2FA(self, request, context):
        try:
            user = User.nodes.get(uid=request.user_id)
            secret, qr_code, backup_codes = self.user_service.setup_2fa(user)
            
            return auth_pb2.Setup2FAResponse(
                success=True,
                secret=secret,
                qr_code=qr_code,
                backup_codes=backup_codes,
                message="2FA успешно настроена"
            )
        except Exception as e:
            return auth_pb2.Setup2FAResponse(
                success=False,
                message="Ошибка настройки 2FA"
            )
    
    def Verify2FA(self, request, context):
        try:
            user = User.nodes.get(uid=request.user_id)
            is_valid = self.user_service.verify_2fa(user, request.code)
            
            if is_valid:
                return auth_pb2.Verify2FAResponse(
                    success=True,
                    message="Код 2FA подтвержден"
                )
            else:
                return auth_pb2.Verify2FAResponse(
                    success=False,
                    message="Неверный код 2FA"
                )
        except Exception as e:
            return auth_pb2.Verify2FAResponse(
                success=False,
                message="Ошибка проверки 2FA"
            )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    listen_addr = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_insecure_port(listen_addr)
    server.start()
    print(f"Auth gRPC сервер запущен на {listen_addr}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve() 