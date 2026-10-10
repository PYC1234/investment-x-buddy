import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger("investment_x_buddy.errors")


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _error_response(
    *, status_code: int, code: str, message: str, request_id: str, details: Any = None
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        safe_details = [
            {"location": list(error["loc"]), "type": error["type"]}
            for error in exc.errors()
        ]
        return _error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed.",
            details=safe_details,
            request_id=request_id,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
        return _error_response(
            status_code=exc.status_code,
            code="http_error",
            message=message,
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        logger.error(
            "Unhandled application error request_id=%s path=%s",
            request_id,
            request.url.path,
        )
        return _error_response(
            status_code=500,
            code="internal_server_error",
            message="An unexpected error occurred.",
            request_id=request_id,
        )

