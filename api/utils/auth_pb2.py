# Протобуф заглушка для auth_pb2
# В production должен генерироваться из proto файлов

class UserCreateRequest:
    def __init__(self):
        self.login = ""
        self.password = ""
        self.nickname = ""

class UserCreateResponse:
    def __init__(self):
        self.success = False
        self.message = ""
        self.user_uid = ""

class UserLoginRequest:
    def __init__(self):
        self.login = ""
        self.password = ""
        self.device_info = ""
        self.ip_address = ""

class UserLoginResponse:
    def __init__(self):
        self.success = False
        self.message = ""
        self.token = ""
        self.requires_2fa = False

class TokenVerifyRequest:
    def __init__(self):
        self.token = ""

class TokenVerifyResponse:
    def __init__(self):
        self.valid = False
        self.user_uid = ""
        self.login = ""
        self.nickname = ""

class RecoveryRequest:
    def __init__(self):
        self.login = ""

class RecoveryResponse:
    def __init__(self):
        self.success = False
        self.message = ""

# Добавляем другие необходимые классы по мере обнаружения
