# Протобуф gRPC заглушка для auth_pb2_grpc
# В production должен генерироваться из proto файлов

import grpc
from . import auth_pb2

class AuthServiceStub:
    def __init__(self, channel):
        self.channel = channel
        
    def CreateUser(self, request):
        # Заглушка для создания пользователя
        response = auth_pb2.UserCreateResponse()
        response.success = False
        response.message = "Auth service not available"
        return response
        
    def LoginUser(self, request):
        # Заглушка для логина
        response = auth_pb2.UserLoginResponse()
        response.success = False
        response.message = "Auth service not available"
        return response
        
    def VerifyToken(self, request):
        # Заглушка для верификации токена
        response = auth_pb2.TokenVerifyResponse()
        response.valid = False
        return response
        
    def RecoveryRequest(self, request):
        # Заглушка для восстановления
        response = auth_pb2.RecoveryResponse()
        response.success = False
        response.message = "Auth service not available"
        return response

class AuthServiceServicer:
    def CreateUser(self, request, context):
        response = auth_pb2.UserCreateResponse()
        response.success = False
        response.message = "Not implemented"
        return response
        
    def LoginUser(self, request, context):
        response = auth_pb2.UserLoginResponse()
        response.success = False
        response.message = "Not implemented"
        return response
