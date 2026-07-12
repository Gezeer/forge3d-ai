from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("forge3d.errors")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _payload(request: Request, code: str, message: str) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(request),
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_payload(request, "validation_error", "Requisição inválida"),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        codes = {
            404: "not_found",
            408: "timeout",
            422: "validation_error",
            503: "service_unavailable",
            504: "generation_timeout",
        }
        code = (error.headers or {}).get(
            "X-Error-Code", codes.get(error.status_code, "request_error")
        )
        message = (
            str(error.detail) if error.status_code < 500 else "Serviço indisponível"
        )
        return JSONResponse(
            status_code=error.status_code,
            content=_payload(request, code, message),
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        logger.exception(
            "unexpected_error error_code=internal_error",
            extra={"error_code": "internal_error"},
        )
        return JSONResponse(
            status_code=500,
            content=_payload(request, "internal_error", "Erro interno inesperado"),
        )
