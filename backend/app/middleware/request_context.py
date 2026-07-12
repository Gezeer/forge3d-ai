from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.context import request_id_context

logger = logging.getLogger("forge3d.http")


def valid_request_id(value: str) -> bool:
    if not value or len(value) > 128:
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        received = request.headers.get("X-Request-ID", "")
        request_id = received if valid_request_id(received) else str(uuid4())
        token = request_id_context.set(request_id)
        request.state.request_id = request_id
        started = time.monotonic()
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.monotonic() - started
            response_status = locals().get("response")
            status_code = getattr(response_status, "status_code", 500)
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            request.app.state.metrics.observe_http(
                request.method, path, status_code, duration
            )
            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                path,
                status_code,
                duration * 1000,
                extra={"status": status_code, "duration_ms": duration * 1000},
            )
            if response_status is not None:
                response_status.headers["X-Request-ID"] = request_id
            request_id_context.reset(token)
