"""
Layer: Domain (Entities)
Package: domain.exceptions
Responsibility: Все доменные исключения, которые могут распространяться вверх по слоям.

Принадлежит слою Domain, потому что исключения выражают нарушение бизнес-правил.
Вышестоящие слои (application, adapters, web) перехватывают их и транслируют в
HTTP-ответы или gRPC-статусы. Сами исключения не знают об HTTP.

Allowed imports: только стандартная библиотека Python
Forbidden imports: fastapi, starlette, grpc, neomodel, pydantic
"""


class KnowledgeMapError(Exception):
    """Базовое исключение для всех доменных ошибок."""


class NotFoundError(KnowledgeMapError):
    """Агрегат не найден по идентификатору."""

    def __init__(self, resource: str, identity: str):
        self.resource = resource
        self.identity = identity
        super().__init__(f"{resource} '{identity}' не найден")


class ConflictError(KnowledgeMapError):
    """Операция нарушает ограничение уникальности или состояния."""

    def __init__(self, message: str):
        super().__init__(message)


class DomainValidationError(KnowledgeMapError):
    """Входные данные нарушают доменное правило."""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"Ошибка валидации поля '{field}': {reason}")


class CyclicGraphError(KnowledgeMapError):
    """Создание связи приведёт к циклу в ориентированном графе."""

    def __init__(self, source_id: str, target_id: str):
        self.source_id = source_id
        self.target_id = target_id
        super().__init__(
            f"Создание связи {source_id!r} → {target_id!r} приведёт к циклу в графе"
        )


class DocumentAlreadyExistsError(KnowledgeMapError):
    """PDF с таким MD5-хешем уже существует."""

    def __init__(self, existing_doc_id: str):
        self.existing_doc_id = existing_doc_id
        super().__init__(f"Документ уже существует: id={existing_doc_id}")


class AuthenticationFailed(KnowledgeMapError):
    """Учётные данные неверны или токен недействителен."""

    def __init__(self, message: str = "Аутентификация не удалась"):
        super().__init__(message)


class RegistrationFailed(KnowledgeMapError):
    """Регистрация пользователя не удалась."""

    def __init__(self, message: str):
        super().__init__(message)


class AuthorizationFailed(KnowledgeMapError):
    """Пользователь не имеет прав на запрошенную операцию."""

    def __init__(self, message: str = "Доступ запрещён"):
        super().__init__(message)


class ExternalServiceError(KnowledgeMapError):
    """Внешний микросервис (gRPC, HTTP) вернул ошибку."""

    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"Ошибка внешнего сервиса '{service}': {detail}")


class StorageError(KnowledgeMapError):
    """Операция с файловым хранилищем завершилась ошибкой."""

    def __init__(self, operation: str, detail: str):
        self.operation = operation
        super().__init__(f"Ошибка хранилища при '{operation}': {detail}")


class ProcessingError(KnowledgeMapError):
    """Конвейер обработки документа завершился ошибкой."""

    def __init__(self, doc_id: str, detail: str):
        self.doc_id = doc_id
        super().__init__(f"Ошибка обработки документа '{doc_id}': {detail}")


class BlockNotPinnedError(KnowledgeMapError):
    """Операция требует, чтобы блок был закреплён."""

    def __init__(self, block_id: str):
        self.block_id = block_id
        super().__init__(f"Блок '{block_id}' не закреплён — невозможно выполнить операцию")
