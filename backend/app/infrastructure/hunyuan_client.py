from __future__ import annotations

import base64
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol
from urllib.parse import urljoin

import httpx

from app.core.exceptions import GenerationTimeoutError, ServiceUnavailableError

OPENAPI_PATH = "/gradio_api/openapi.json"
CONFIG_PATH = "/config"
FALLBACK_API_PREFIX = "/gradio_api"
DEFAULT_ENDPOINT = "/run/shape_generation"
LOADING_STATUS_CODES = {425, 429, 502, 503, 504}
FALLBACK_DEFAULTS: dict[str, Any] = {
    "mv_image_front": None,
    "mv_image_back": None,
    "mv_image_left": None,
    "mv_image_right": None,
    "steps": 30,
    "guidance_scale": 5.0,
    "seed": 1234,
    "octree_resolution": 256,
    "check_box_rembg": True,
    "num_chunks": 8000,
    "randomize_seed": False,
}
IMAGE_FIELDS = ("image", "input_image")


@dataclass(frozen=True)
class HunyuanResult:
    data: Any
    request_payload: dict[str, Any]


class HttpClient(Protocol):
    def get(self, url: str, *, timeout: float) -> httpx.Response: ...

    def post(
        self, url: str, *, json: Mapping[str, Any], timeout: float
    ) -> httpx.Response: ...


class HunyuanClient:
    """HTTP/OpenAPI client for the Gradio 5 Hunyuan REST endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        retry_attempts: int = 5,
        retry_base_seconds: float = 0.5,
        http_client: Optional[HttpClient] = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith(FALLBACK_API_PREFIX):
            self.base_url = self.base_url[: -len(FALLBACK_API_PREFIX)]
        self.endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if self.endpoint.startswith(f"{FALLBACK_API_PREFIX}/"):
            self.endpoint = self.endpoint[len(FALLBACK_API_PREFIX) :]
        self.retry_attempts = max(1, retry_attempts)
        self.retry_base_seconds = max(0.0, retry_base_seconds)
        self._http_client = http_client
        self.sleeper = sleeper
        self._openapi: Optional[dict[str, Any]] = None
        self._api_prefix: Optional[str] = None
        self.last_error: Optional[str] = None

    @property
    def http(self) -> HttpClient:
        if self._http_client is None:
            self._http_client = httpx.Client(follow_redirects=True)
        return self._http_client

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _backoff(self, attempt: int) -> None:
        self.sleeper(self.retry_base_seconds * (2**attempt))

    @staticmethod
    def _normalize_api_prefix(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            return FALLBACK_API_PREFIX
        prefix = value.strip().rstrip("/")
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return "" if prefix == "/" else prefix

    def _discover_api_prefix(self, timeout: float) -> str:
        if self._api_prefix is not None:
            return self._api_prefix
        try:
            response = self.http.get(self._url(CONFIG_PATH), timeout=timeout)
            response.raise_for_status()
            config = response.json()
            value = config.get("api_prefix") if isinstance(config, dict) else None
            self._api_prefix = self._normalize_api_prefix(value)
        except (httpx.HTTPError, ValueError):
            self._api_prefix = FALLBACK_API_PREFIX
        return self._api_prefix

    def execution_url(self, timeout: float) -> str:
        prefix = self._discover_api_prefix(timeout)
        root = self.base_url
        if prefix and not root.endswith(prefix):
            root = f"{root}{prefix}"
        logical_endpoint = self.endpoint
        if prefix and logical_endpoint.startswith(f"{prefix}/"):
            logical_endpoint = logical_endpoint[len(prefix) :]
        return f"{root}{logical_endpoint}"

    @staticmethod
    def _loading_response(response: httpx.Response) -> bool:
        if response.status_code in LOADING_STATUS_CODES:
            return True
        content = response.text.lower()
        return response.status_code >= 500 and any(
            marker in content
            for marker in ("loading", "starting", "initializing", "not ready")
        )

    def discover(self, timeout: float, *, refresh: bool = False) -> dict[str, Any]:
        if self._openapi is not None and not refresh:
            return self._openapi
        last_error: Optional[Exception] = None
        for attempt in range(self.retry_attempts):
            try:
                response = self.http.get(self._url(OPENAPI_PATH), timeout=timeout)
                if self._loading_response(response):
                    raise ServiceUnavailableError("Hunyuan ainda está carregando")
                response.raise_for_status()
                schema = response.json()
                if not isinstance(schema, dict):
                    raise ValueError("OpenAPI inválido")
                operation = schema.get("paths", {}).get(self.endpoint, {}).get("post")
                if not isinstance(operation, dict):
                    raise ServiceUnavailableError(
                        f"Endpoint Hunyuan ausente no OpenAPI: {self.endpoint}"
                    )
                self._openapi = schema
                self._discover_api_prefix(timeout)
                self.last_error = None
                return schema
            except (httpx.HTTPError, ValueError, ServiceUnavailableError) as exc:
                last_error = exc
                self.last_error = type(exc).__name__
                if attempt + 1 < self.retry_attempts:
                    self._backoff(attempt)
        raise ServiceUnavailableError(
            "OpenAPI do Hunyuan indisponível ou ainda carregando"
        ) from last_error

    @staticmethod
    def _resolve_schema(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
        seen: set[str] = set()
        schema = dict(schema)
        while "$ref" in schema:
            reference = schema["$ref"]
            if not isinstance(reference, str) or not reference.startswith("#/"):
                raise ServiceUnavailableError("Referência OpenAPI Hunyuan inválida")
            if reference in seen:
                raise ServiceUnavailableError("Referência OpenAPI Hunyuan circular")
            seen.add(reference)
            target: Any = root
            for part in reference[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            if not isinstance(target, dict):
                raise ServiceUnavailableError("Schema OpenAPI Hunyuan inválido")
            siblings = {key: value for key, value in schema.items() if key != "$ref"}
            schema = {**target, **siblings}
        alternatives = schema.get("anyOf") or schema.get("oneOf")
        if isinstance(alternatives, list):
            selected = next(
                (
                    item
                    for item in alternatives
                    if isinstance(item, dict) and item.get("type") != "null"
                ),
                None,
            )
            if selected is not None:
                siblings = {
                    key: value
                    for key, value in schema.items()
                    if key not in {"anyOf", "oneOf"}
                }
                return {
                    **HunyuanClient._resolve_schema(selected, root),
                    **siblings,
                }
        return schema

    def _request_schema(self, openapi: dict[str, Any]) -> dict[str, Any]:
        operation = openapi["paths"][self.endpoint]["post"]
        content = operation.get("requestBody", {}).get("content", {})
        media = content.get("application/json")
        if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
            raise ServiceUnavailableError(
                "O endpoint Hunyuan não publica requestBody application/json"
            )
        return self._resolve_schema(media["schema"], openapi)

    @staticmethod
    def _data_url(image_path: Path) -> str:
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{media_type};base64,{encoded}"

    def _image_value(
        self,
        image_path: Path,
        field_schema: dict[str, Any],
        openapi: dict[str, Any],
    ) -> Any:
        resolved = self._resolve_schema(field_schema, openapi)
        if resolved.get("type") == "string":
            return self._data_url(image_path)
        properties = resolved.get("properties", {})
        if not isinstance(properties, dict):
            return self._data_url(image_path)
        if "background" in properties:
            return {
                "background": self._data_url(image_path),
                "layers": [],
                "composite": None,
            }
        if "path" in properties:
            return {
                "path": str(image_path.resolve()),
                "url": None,
                "orig_name": image_path.name,
                "size": image_path.stat().st_size,
                "mime_type": mimetypes.guess_type(image_path.name)[0] or "image/png",
                "meta": {"_type": "gradio.FileData"},
            }
        if "data" in properties:
            return {"data": self._data_url(image_path)}
        return self._data_url(image_path)

    def build_payload(
        self, image_path: Path, openapi: dict[str, Any]
    ) -> dict[str, Any]:
        schema = self._request_schema(openapi)
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ServiceUnavailableError("Schema JSON do Hunyuan sem propriedades")
        image_field = next((name for name in IMAGE_FIELDS if name in properties), None)
        if image_field is None:
            image_field = next(
                (
                    name
                    for name in properties
                    if "image" in name.lower() and not name.lower().startswith("mv_")
                ),
                None,
            )
        if image_field is None:
            raise ServiceUnavailableError("Campo de imagem ausente no OpenAPI Hunyuan")

        payload: dict[str, Any] = {}
        for name, raw_property in properties.items():
            if not isinstance(raw_property, dict):
                continue
            prop = self._resolve_schema(raw_property, openapi)
            if name == image_field:
                payload[name] = self._image_value(image_path, raw_property, openapi)
            elif "default" in prop:
                payload[name] = prop["default"]
            elif name in FALLBACK_DEFAULTS:
                payload[name] = FALLBACK_DEFAULTS[name]
            elif name in schema.get("required", []):
                payload[name] = None
        return payload

    def build_envelope(
        self, payload: Mapping[str, Any], openapi: dict[str, Any]
    ) -> dict[str, list[Any]]:
        schema = self._request_schema(openapi)
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ServiceUnavailableError("Schema JSON do Hunyuan sem propriedades")
        return {"data": [payload[name] for name in properties if name in payload]}

    def available(self, timeout: float) -> bool:
        try:
            self.discover(timeout)
            return True
        except ServiceUnavailableError:
            return False

    def diagnostics(self) -> dict[str, Any]:
        return {
            "openapi": "available" if self._openapi is not None else "unavailable",
            "endpoint": self.endpoint,
            "api_prefix": self._api_prefix or FALLBACK_API_PREFIX,
            "execution_url": self.execution_url(2.0),
            "error_code": self.last_error,
        }

    def _normalize_result_urls(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._normalize_result_urls(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._normalize_result_urls(item) for item in value]
        if isinstance(value, str) and value.startswith(("/gradio_api/", "/file=")):
            return urljoin(f"{self.base_url}/", value.lstrip("/"))
        return value

    def generate(self, image_path: Path, timeout: float) -> HunyuanResult:
        if not image_path.is_file():
            raise ServiceUnavailableError("Imagem Hunyuan não encontrada")
        openapi = self.discover(min(timeout, 30.0))
        payload = self.build_payload(image_path, openapi)
        envelope = self.build_envelope(payload, openapi)
        last_error: Optional[Exception] = None
        for attempt in range(self.retry_attempts):
            try:
                response = self.http.post(
                    self.execution_url(min(timeout, 30.0)),
                    json=envelope,
                    timeout=timeout,
                )
                if self._loading_response(response):
                    raise ServiceUnavailableError("Hunyuan ainda está carregando")
                response.raise_for_status()
                self.last_error = None
                return HunyuanResult(
                    self._normalize_result_urls(response.json()), payload
                )
            except httpx.ReadTimeout as exc:
                raise GenerationTimeoutError(
                    "A geração Hunyuan excedeu o tempo limite configurado"
                ) from exc
            except (httpx.ConnectError, ServiceUnavailableError) as exc:
                last_error = exc
                self.last_error = type(exc).__name__
                if attempt + 1 < self.retry_attempts:
                    self._backoff(attempt)
            except (httpx.HTTPError, ValueError) as exc:
                self.last_error = type(exc).__name__
                raise ServiceUnavailableError("Resposta inválida do Hunyuan") from exc
        raise ServiceUnavailableError(
            "Hunyuan indisponível após retries"
        ) from last_error
