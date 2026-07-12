from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from app.core.exceptions import GenerationTimeoutError, ServiceUnavailableError

IMAGE_MARKER = "$image"
IMAGE_FORMATS = {"simple", "imagedata", "imageeditor"}


@dataclass(frozen=True)
class HunyuanSignature:
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)


class HunyuanGateway(Protocol):
    def available(self) -> bool: ...

    def predict(
        self,
        image_path: Path,
        signature: HunyuanSignature,
        api_name: str,
        timeout: float,
    ) -> Any: ...


class GradioHunyuanGateway:
    """Lazy Gradio adapter that does not import the client at module import."""

    def __init__(
        self,
        url: str,
        client_factory: Optional[Callable[[str], Any]] = None,
        file_handler: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.url = url
        self._client_factory = client_factory
        self._file_handler = file_handler
        self._client = None

    def _dependencies(self) -> tuple[Callable[[str], Any], Callable[[str], Any]]:
        if self._client_factory is None or self._file_handler is None:
            try:
                from gradio_client import Client, handle_file
            except ImportError as exc:
                raise ServiceUnavailableError(
                    "Cliente Hunyuan não está instalado neste ambiente"
                ) from exc
            self._client_factory = self._client_factory or Client
            self._file_handler = self._file_handler or handle_file
        return self._client_factory, self._file_handler

    def _connect(self) -> Any:
        if self._client is None:
            client_factory, _ = self._dependencies()
            try:
                self._client = client_factory(self.url)
            except Exception as exc:
                raise ServiceUnavailableError(
                    "Hunyuan está indisponível na URL configurada"
                ) from exc
        return self._client

    def available(self) -> bool:
        try:
            self._connect()
            return True
        except ServiceUnavailableError:
            return False

    def _inject_image(self, value: Any, image_path: Path) -> Any:
        _, file_handler = self._dependencies()
        if isinstance(value, dict) and IMAGE_MARKER in value:
            image_format = value[IMAGE_MARKER]
            if image_format is True:
                image_format = "simple"
            if image_format not in IMAGE_FORMATS:
                raise ServiceUnavailableError("Formato de imagem Hunyuan inválido")
            file_data = file_handler(str(image_path))
            if image_format in {"simple", "imagedata"}:
                return file_data
            return {"background": file_data, "layers": [], "composite": None}
        if isinstance(value, list):
            return [self._inject_image(item, image_path) for item in value]
        if isinstance(value, dict):
            return {
                key: self._inject_image(item, image_path) for key, item in value.items()
            }
        return value

    def predict(
        self,
        image_path: Path,
        signature: HunyuanSignature,
        api_name: str,
        timeout: float,
    ) -> Any:
        client = self._connect()
        args = [self._inject_image(item, image_path) for item in signature.args]
        kwargs = {
            key: self._inject_image(value, image_path)
            for key, value in signature.kwargs.items()
        }
        try:
            future = client.submit(*args, api_name=api_name, **kwargs)
            return future.result(timeout=timeout)
        except TimeoutError as exc:
            raise GenerationTimeoutError(
                "A geração Hunyuan excedeu o tempo limite configurado"
            ) from exc
        except Exception as exc:
            raise ServiceUnavailableError("Falha ao executar o Hunyuan") from exc
