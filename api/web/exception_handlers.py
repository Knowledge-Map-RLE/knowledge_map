"""
Layer: Interface Adapters — Web
Package: web.exception_handlers
Responsibility: Трансляция доменных исключений в HTTP-ответы.

Принадлежит слою web (Interface Adapters + Frameworks). Это ЕДИНСТВЕННОЕ место,
где доменные исключения получают HTTP-статус коды.
Регистрируется в web/app.py через app.add_exception_handler().

Allowed imports: fastapi, starlette, domain.exceptions
Forbidden imports: neomodel, grpc, application, adapters, infrastructure
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from domain.exceptions import (
    NotFoundError,
    ConflictError,
    DomainValidationError,
    CyclicGraphError,
    DocumentAlreadyExistsError,
    AuthenticationFailed,
    RegistrationFailed,
    AuthorizationFailed,
    ExternalServiceError,
    StorageError,
    ProcessingError,
    BlockNotPinnedError,
    KnowledgeMapError,
)


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def validation_handler(request: Request, exc: DomainValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "field": exc.field, "reason": exc.reason},
    )


async def cyclic_graph_handler(request: Request, exc: CyclicGraphError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def document_exists_handler(
    request: Request, exc: DocumentAlreadyExistsError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "existing_doc_id": exc.existing_doc_id},
    )


async def auth_failed_handler(request: Request, exc: AuthenticationFailed) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


async def registration_failed_handler(
    request: Request, exc: RegistrationFailed
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def authorization_failed_handler(
    request: Request, exc: AuthorizationFailed
) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


async def external_service_handler(
    request: Request, exc: ExternalServiceError
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "service": exc.service},
    )


async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


async def processing_error_handler(request: Request, exc: ProcessingError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "doc_id": exc.doc_id},
    )


async def block_not_pinned_handler(
    request: Request, exc: BlockNotPinnedError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def domain_error_handler(request: Request, exc: KnowledgeMapError) -> JSONResponse:
    """Fallback для всех остальных доменных исключений."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def register_exception_handlers(app) -> None:
    """Регистрирует все обработчики на FastAPI-приложении."""
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(ConflictError, conflict_handler)
    app.add_exception_handler(DomainValidationError, validation_handler)
    app.add_exception_handler(CyclicGraphError, cyclic_graph_handler)
    app.add_exception_handler(DocumentAlreadyExistsError, document_exists_handler)
    app.add_exception_handler(AuthenticationFailed, auth_failed_handler)
    app.add_exception_handler(RegistrationFailed, registration_failed_handler)
    app.add_exception_handler(AuthorizationFailed, authorization_failed_handler)
    app.add_exception_handler(ExternalServiceError, external_service_handler)
    app.add_exception_handler(StorageError, storage_error_handler)
    app.add_exception_handler(ProcessingError, processing_error_handler)
    app.add_exception_handler(BlockNotPinnedError, block_not_pinned_handler)
    app.add_exception_handler(KnowledgeMapError, domain_error_handler)
