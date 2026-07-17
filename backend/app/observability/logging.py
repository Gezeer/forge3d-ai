from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import Settings
from app.observability.context import request_id_context

SAFE_FIELDS = ("job_id", "engine", "status", "duration_ms", "error_code")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        }
        for field in SAFE_FIELDS:
            value = getattr(record, field, None)
            if value not in (None, ""):
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    formatter: logging.Formatter
    if settings.log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s %(message)s"
        )
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        settings.api_log.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(settings.api_log, encoding="utf-8"))
    except OSError as error:
        # Keep stdout operational even when the optional persistent log cannot
        # be opened (read-only filesystem, quota, or permissions).
        print(f"Forge3D file logging unavailable: {error}", file=sys.stderr, flush=True)
    for handler in handlers:
        handler.addFilter(RequestContextFilter())
        handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(settings.log_level)
